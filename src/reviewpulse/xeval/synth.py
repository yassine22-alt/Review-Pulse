"""Synthetic requirement corpus with truth by construction, over randomly drawn catalogues.

Each item draws a few concepts (stairs, ducts, lifts, rooms, ...) and building-level facts, builds a
reference rule program over them, and renders it as an English or French sentence. The drafter receives the
item's own catalogue, so nothing about a particular building type is built in. `split="test"` always
includes a concept that dev items never use.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from ..interpreter.schema import Program
from .catalogue import BUILDING_FACTS, Concept, Prop, fact_name, kind_name, pools

# ---- program builders -------------------------------------------------------------------------


def lit(value, unit="1"):
    return {"node": "literal", "value": value, "unit": unit}


def fact(name, entity="$x"):
    return {"node": "fact", "entity": entity, "name": name}


def binary(node, left, right):
    return {"node": node, "left": left, "right": right}


def logic(node, *args):
    return {"node": node, "args": list(args)}


def setop(node, collection, body=None, where=None):
    out = {"node": node, "collection": collection, "variable": "$x"}
    if body:
        out["body"] = body
    if where:
        out["where"] = where
    return out


# ---- wording -------------------------------------------------------------------------------------

CMP_EN = {"ge": ["at least", "not less than"], "gt": ["more than", "greater than"],
          "le": ["at most", "not more than"], "lt": ["less than", "below"]}
CMP_FR = {"ge": "d'au moins", "gt": "de plus de", "le": "d'au plus", "lt": "de moins de"}


def an(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def number(x: float, lang: str) -> str:
    text = f"{x:g}"
    return text.replace(".", ",") if lang == "fr" else text


def fmt(x: float, unit: str, lang: str, style: int, note: str = "") -> str:
    if unit == "m":
        if style == 1:
            return f"{number(round(x * 100, 4), lang)} cm"
        if style == 2:
            return f"{number(round(x * 1000, 4), lang)} mm"
        return f"{number(x, lang)} m"
    if unit == "m2":
        return f"{number(x, lang)} " + ["m²", "m2", "mètres carrés" if lang == "fr" else "square metres"][style % 3]
    if unit == "1":
        return f"{number(round(x * 100, 4), lang)} %"
    unit_word = ("personnes" if lang == "fr" else "persons") if note == "persons" else ""
    return f"{number(x, lang)} {unit_word}".strip()


@dataclass
class Item:
    id: str
    family: str
    lang: str
    text: str
    program: dict
    catalogue: dict
    params: dict = field(default_factory=dict)
    split: str = "dev"


def _pick(rng, options):
    return options[rng.randrange(len(options))]


def _catalogue(concepts: list[Concept], buildings: list) -> dict:
    cat = {"collections": {}, "building": [b.name for b in buildings], "bindings": {}, "kinds": {}, "kind_labels": {}}
    for c in concepts:
        names = []
        for p in c.props:
            name = fact_name(c, p)
            names.append(name)
            cat["bindings"][name] = {"kind": "number", "unit": p.unit,
                                     "description": f"{c.en[0]}: {p.en} ({p.unit})"}
        if c.kinds:
            kn = kind_name(c)
            names.append(kn)
            ids = [k[0] for k in c.kinds]
            cat["bindings"][kn] = {"kind": "string", "unit": "1",
                                   "description": f"{c.en[0]} category, one of: {', '.join(ids)}"}
            cat["kinds"][kn] = ids
            cat["kind_labels"][kn] = {k[0]: [k[1], k[2], k[3], k[4]] for k in c.kinds}
        cat["collections"][c.key] = {"facts": names}
    for b in buildings:
        cat["bindings"][b.name] = {"kind": "number", "unit": b.unit,
                                   "description": f"{b.description} (entity building)"}
    return cat


def sample_item(rng: random.Random, index: int, split: str = "dev", lang: str | None = None,
                family: str | None = None) -> Item:
    lang = lang or _pick(rng, ["en", "fr"])
    en = lang == "en"
    pool = pools(split)
    held = [c for c in pool if c.split == "test"]
    primary = _pick(rng, held) if split == "test" and held else _pick(rng, pool)
    others = rng.sample([c for c in pool if c is not primary], rng.randint(1, 3))
    concepts = [primary, *others]
    rng.shuffle(concepts)
    buildings = rng.sample(list(BUILDING_FACTS), rng.randint(1, 3))
    cat = _catalogue(concepts, buildings)

    numeric = list(primary.props)
    families = ["threshold", "threshold", "conditional", "exemption", "range", "count", "total", "exists"]
    if len(numeric) >= 2:
        families += ["scoped", "alternative"]
    if primary.kinds and any(p.unit in ("m", "m2", "count") for p in numeric):
        families += ["ratio"]
    fam = family or _pick(rng, families)
    sty, v = rng.randrange(3), rng.randrange(2)

    use_kind = bool(primary.kinds) and (fam in ("scoped", "ratio") or rng.random() < 0.6)
    kind = _pick(rng, primary.kinds) if use_kind else None
    if kind:
        subj = (kind[1], kind[2]) if en else (kind[3], kind[4])
    else:
        subj = primary.en if en else primary.fr
    where = binary("eq", fact(kind_name(primary)), lit(kind[0])) if kind else None
    prop: Prop = _pick(rng, numeric)
    val = _pick(rng, prop.grid)
    pf = fact_name(primary, prop)
    pname = prop.en if en else prop.fr
    cmp_key = _pick(rng, ["ge", "ge", "ge", "gt", "le", "lt"]) if fam == "threshold" else "ge"
    cmp_txt = _pick(rng, CMP_EN[cmp_key]) if en else CMP_FR[cmp_key]
    shown = fmt(val, prop.unit, lang, sty, prop.note)
    params = {"concept": primary.key, "prop": prop.name, "kind": kind[0] if kind else None, "value": val}

    def sentence(core: str) -> str:
        return core[0].upper() + core[1:]

    def have(subject, p_name, c_txt, value_txt):
        if en:
            return (f"each {subject} shall have {an(p_name)} {p_name} of {c_txt} {value_txt}" if v == 0
                    else f"the {p_name} of every {subject} must be {c_txt} {value_txt}")
        return f"chaque {subject} doit avoir {p_name} {c_txt} {value_txt}"

    def other_prop():
        return _pick(rng, [p for p in numeric if p is not prop])

    applicability = exemption = None
    if fam == "threshold":
        requirement = setop("forall", primary.key, binary(cmp_key, fact(pf), lit(val, prop.unit)), where)
        text = sentence(have(subj[0], pname, cmp_txt, shown)) + "."
    elif fam in ("conditional", "exemption"):
        bf = _pick(rng, buildings)
        n = _pick(rng, bf.grid)
        n_txt = fmt(n, bf.unit, lang, sty)
        core = have(subj[0], pname, "at least" if en else CMP_FR["ge"], shown)
        requirement = setop("forall", primary.key, binary("ge", fact(pf), lit(val, prop.unit)), where)
        if fam == "conditional":
            applicability = binary("gt", fact(bf.name, "building"), lit(n, bf.unit))
            text = bf.cond[0 if en else 1].format(v=n_txt) + core + "."
        else:
            exemption = binary("le", fact(bf.name, "building"), lit(n, bf.unit))
            text = sentence(core) + ", " + bf.exempt[0 if en else 1].format(v=n_txt) + "."
        params.update(building=bf.name, n=n)
    elif fam == "scoped":
        other = other_prop()
        y = _pick(rng, other.grid)
        yt = fmt(y, other.unit, lang, sty, other.note)
        cond = binary("ge", fact(fact_name(primary, other)), lit(y, other.unit))
        scope = logic("all", where, cond) if where else cond
        requirement = setop("forall", primary.key, binary("ge", fact(pf), lit(val, prop.unit)), scope)
        if en:
            text = f"Each {subj[0]} with {an(other.en)} {other.en} of at least {yt} shall have {an(pname)} {pname} of at least {shown}."
        else:
            text = f"Chaque {subj[0]} ayant {other.fr} d'au moins {yt} doit avoir {pname} d'au moins {shown}."
        params.update(other=other.name, other_value=y)
    elif fam == "range":
        lo, hi = sorted(rng.sample(list(prop.grid), 2))
        lo_t, hi_t = fmt(lo, prop.unit, lang, sty, prop.note), fmt(hi, prop.unit, lang, sty, prop.note)
        body = logic("all", binary("ge", fact(pf), lit(lo, prop.unit)), binary("le", fact(pf), lit(hi, prop.unit)))
        requirement = setop("forall", primary.key, body, where)
        if en:
            text = f"The {pname} of each {subj[0]} shall be between {lo_t} and {hi_t}."
        else:
            text = f"Chaque {subj[0]} doit avoir {pname} comprise entre {lo_t} et {hi_t}."
        params.update(lo=lo, hi=hi)
    elif fam == "alternative":
        other = other_prop()
        y = _pick(rng, other.grid)
        yt = fmt(y, other.unit, lang, sty, other.note)
        body = logic("any", binary("ge", fact(pf), lit(val, prop.unit)),
                     binary("ge", fact(fact_name(primary, other)), lit(y, other.unit)))
        requirement = setop("forall", primary.key, body, where)
        if en:
            text = f"Each {subj[0]} shall have {an(pname)} {pname} of at least {shown} or {an(other.en)} {other.en} of at least {yt}."
        else:
            text = f"Chaque {subj[0]} doit avoir {pname} d'au moins {shown} ou {other.fr} d'au moins {yt}."
        params.update(other=other.name, other_value=y)
    elif fam == "count":
        k = _pick(rng, [1, 2, 3])
        cond = binary("ge", fact(pf), lit(val, prop.unit))
        scope = logic("all", where, cond) if where else cond
        requirement = binary("ge", setop("count", primary.key, None, scope), lit(k, "count"))
        if en:
            text = f"At least {k} {subj[1] if k > 1 else subj[0]} shall have {an(pname)} {pname} of at least {shown}."
        else:
            text = f"Au moins {k} des {subj[1]} doivent avoir {pname} d'au moins {shown}."
        params.update(k=k)
    elif fam == "total":
        cmp_key = _pick(rng, ["ge", "le"])
        total = round(val * _pick(rng, [2, 3, 4]), 6)
        total_txt = fmt(total, prop.unit, lang, sty, prop.note)
        requirement = binary(cmp_key, setop("sum", primary.key, fact(pf), where), lit(total, prop.unit))
        pl = prop.en_pl if en else prop.fr_pl
        c_txt = _pick(rng, CMP_EN[cmp_key]) if en else CMP_FR[cmp_key]
        if en:
            text = f"The sum of the {pl} of all {subj[1]} shall be {c_txt} {total_txt}."
        else:
            text = f"La somme des {pl} de tous les {subj[1]} doit être {c_txt} {total_txt}."
        params.update(total=total, cmp=cmp_key)
    elif fam == "ratio":
        base = _pick(rng, [p for p in numeric if p.unit in ("m", "m2", "count")])
        pct = _pick(rng, [10, 15, 20, 25, 30, 40])
        bf = fact(fact_name(primary, base))
        ratio = binary("div", setop("sum", primary.key, bf, where), setop("sum", primary.key, bf))
        requirement = binary("ge", ratio, lit(round(pct / 100, 6)))
        pct_txt = f"{pct} %" if v == 0 else f"{pct}%"
        pl = base.en_pl if en else base.fr_pl
        if en:
            text = f"The sum of the {pl} of {subj[1]} shall be at least {pct_txt} of the sum of the {pl} of all {primary.en[1]}."
        else:
            text = f"La somme des {pl} des {subj[1]} doit représenter au moins {pct_txt} de la somme des {pl} de tous les {primary.fr[1]}."
        params.update(pct=pct, base=base.name)
    else:  # exists
        requirement = setop("exists", primary.key, binary("ge", fact(pf), lit(val, prop.unit)), where)
        if en:
            text = f"At least one of the {subj[1]} shall have {an(pname)} {pname} of at least {shown}."
        else:
            text = f"Au moins l'un des {subj[1]} doit avoir {pname} d'au moins {shown}."

    item_id = f"s{index:04d}"
    prog = {"id": item_id, "title": item_id, "document": "synth", "requirement": requirement,
            "sources": [{"clause": "Art. 1", "start": 0, "end": 1, "quote": "A"}]}
    if applicability:
        prog["applicability"] = applicability
    if exemption:
        prog["exemption"] = exemption
    Program.model_validate(prog)  # the reference itself must be a valid program
    return Item(id=item_id, family=fam, lang=lang, text=text, program=prog, catalogue=cat, params=params,
                split=split)


def document(item: Item) -> str:
    """The requirement as a one-article document, in the form the clause splitter understands."""
    return f"Art. 1: {item.text}\n"


def build_corpus(n: int, seed: int = 7, split: str = "dev") -> list[Item]:
    rng = random.Random(seed)
    return [sample_item(rng, i, split) for i in range(n)]


def write_corpus(items: list[Item], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(i.__dict__, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")


def read_corpus(path: Path) -> list[Item]:
    return [Item(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
