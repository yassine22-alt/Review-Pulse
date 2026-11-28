"""Synthetic requirement documents with a KNOWN reference structure, in English, French, German and Spanish.

A document is a list of clauses; each clause carries a marker (K01, K02, ...) that survives any renumbering or moving, and a list
of planted links (a reference, an exception through a reference, a table, a condition, a defined term, an inline exception, a
reference to another document, a reference that points nowhere, and plain numbers that are not references). `render` writes the
document in a language, with section numbers given by a labelling function, so that the SAME structure can be written with other
numbers or in another order: the graph must follow. `gold` returns the edges the document was built to contain.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

LANG = {
    "en": dict(
        base="The stair must have a handrail on both sides", ref="(see {kw} {l})", exc="except as provided in {kw} {l}",
        table="see Table {l}", cond="Where the conditions of {kw} {l} are met", inline="unless the stair is external",
        ext="as required by Regulation 7 of the Building Regulations 2010", dangling="(see paragraph 99.9)",
        unit="The clear width is at least 2.5 m and the rise at most 1.2 m.", kws=["paragraph", "Section", "clause"],
        term="habitable room", term_def='"{t}" means a room used for living or sleeping.', use="a {t} must have a window",
        table_cap="Table {l} Maximum travel distance", table_ref_kw="Table",
    ),
    "fr": dict(
        base="L'escalier doit comporter une main courante de chaque côté", ref="(voir {kw} {l})", exc="sous réserve du {kw} {l}",
        table="voir le tableau {l}", cond="Lorsque les conditions du {kw} {l} sont remplies", inline="sauf si l'escalier est extérieur",
        ext="conformément à l'article R. 111-18 du code de la construction", dangling="(voir le paragraphe 99.9)",
        unit="La largeur utile est d'au moins 2.5 m et la hauteur d'au plus 1.2 m.", kws=["paragraphe", "paragraphe", "paragraphe"],
        term="pièce habitable", term_def="« {t} » signifie une pièce destinée à l'habitation ou au repos.", use="une {t} doit avoir une fenêtre",
        table_cap="Tableau {l} Distance maximale de parcours", table_ref_kw="Tableau",
    ),
    "de": dict(
        base="Die Treppe muss beidseitig einen Handlauf haben", ref="(siehe {kw} {l})", exc="vorbehaltlich {kw} {l}",
        table="siehe Tabelle {l}", cond="Wenn die Bedingungen nach {kw} {l} erfüllt sind", inline="es sei denn, die Treppe liegt außen",
        ext="gemäß § 5 der Bauordnung", dangling="(siehe Absatz 99.9)",
        unit="Die lichte Breite beträgt mindestens 2.5 m und die Höhe höchstens 1.2 m.", kws=["Absatz", "Abschnitt", "Absatz"],
        term="Aufenthaltsraum", term_def="„{t}“ bedeutet ein Raum, der zum Wohnen oder Schlafen genutzt wird.", use="ein {t} muss ein Fenster haben",
        table_cap="Tabelle {l} Größte Fluchtweglänge", table_ref_kw="Tabelle",
    ),
    "es": dict(
        base="La escalera debe tener pasamanos a ambos lados", ref="(véase el {kw} {l})", exc="salvo lo dispuesto en el {kw} {l}",
        table="véase la tabla {l}", cond="Cuando se cumplan las condiciones del {kw} {l}", inline="a menos que la escalera sea exterior",
        ext="según el artículo 12 del Código Técnico", dangling="(véase el párrafo 99.9)",
        unit="La anchura libre es de al menos 2.5 m y la altura de como máximo 1.2 m.", kws=["párrafo", "sección", "párrafo"],
        term="estancia habitable", term_def="«{t}» significa una estancia destinada a vivir o dormir.", use="una {t} debe tener una ventana",
        table_cap="Tabla {l} Distancia máxima de recorrido", table_ref_kw="Tabla",
    ),
}


# A second wording of every cue, chosen BEFORE the cue file was checked against it: held out, to see how far the cue list reaches.
HELD_OUT = {
    "en": dict(ref="(refer to {kw} {l})", exc="other than in the case covered by {kw} {l}", table="as set out in Table {l}",
               cond="If {kw} {l} applies", inline="save where the stair is external", ext="in line with Section 12 of the Fire Safety Act 2005",
               kws=["paragraph", "Section", "subsection"]),
    "fr": dict(ref="(se reporter au {kw} {l})", exc="à l'exception du cas visé au {kw} {l}", table="telle que prévue au tableau {l}",
               cond="Dans le cas où le {kw} {l} s'applique", inline="hormis lorsque l'escalier est extérieur",
               ext="en application de l'article L. 123-1 du code de l'urbanisme", kws=["paragraphe", "alinéa", "paragraphe"]),
    "de": dict(ref="(vgl. {kw} {l})", exc="mit Ausnahme von {kw} {l}", table="gemäß Tabelle {l}", cond="Falls {kw} {l} gilt",
               inline="ausgenommen bei außenliegenden Treppen", ext="nach § 12 des Brandschutzgesetzes", kws=["Absatz", "Abschnitt", "Absatz"]),
    "es": dict(ref="(véase {kw} {l})", exc="con excepción de lo previsto en el {kw} {l}", table="conforme a la tabla {l}",
               cond="Siempre que se aplique el {kw} {l}", inline="excepto si la escalera es exterior", ext="de acuerdo con el artículo 7 del Reglamento",
               kws=["párrafo", "sección", "párrafo"]),
}


@dataclass
class SClause:
    k: int                                              # marker number: the clause is "K<k>" whatever its label
    section: int
    links: list[tuple] = field(default_factory=list)    # ("ref", k2), ("exc", k2), ("table", k2), ("cond", k2), ("use",), ("inline",), ("ext",), ("dangling",), ("unit",)
    kind: str = "clause"                                # clause | table | definition


def build(n_sections: int = 5, per: int = 5, seed: int = 0) -> list[SClause]:
    """A document: sections of `per` clauses; one definition clause, one table, and planted links that point backward and forward."""
    rng = random.Random(seed)
    cl: list[SClause] = []
    k = 0
    for s in range(1, n_sections + 1):
        for _ in range(per):
            k += 1
            cl.append(SClause(k, s))
    defn = cl[0]
    defn.kind = "definition"
    tables = [c for c in cl if c.k % per == 0 and c.k > 1][:2]
    for t in tables:
        t.kind = "table"
    plain = [c for c in cl if c.kind == "clause"]
    kinds = ["ref", "exc", "table", "cond", "use", "inline", "ext", "dangling", "unit"]
    for i, c in enumerate(plain):
        for kind in rng.sample(kinds, 2):
            others = [o for o in cl if o.k != c.k and o.kind != "definition"]
            if kind in ("ref", "exc", "cond"):
                tgt = rng.choice([o for o in others if o.kind == "clause"])
                c.links.append((kind, tgt.k))
            elif kind == "table":
                c.links.append(("table", rng.choice(tables).k))
            else:
                c.links.append((kind,))
        del i
    return cl


def labels_default(cl: list[SClause]) -> dict[int, str]:
    out, i, cur = {}, 0, 0
    for c in cl:
        if c.section != cur:
            cur, i = c.section, 0
        i += 1
        out[c.k] = f"{c.section}.{i}"
    return out


def render(cl: list[SClause], lang: str = "en", labels: dict[int, str] | None = None, order: list[int] | None = None,
           kw_shift: int = 0, held_out: bool = False) -> str:
    """Write the document. `labels` maps a marker to its section number, `order` is the order of the clauses in the text,
    `kw_shift` rotates the part word used in references (paragraph, Section, clause ...)."""
    L = {**LANG[lang], **(HELD_OUT[lang] if held_out else {})}
    labels = labels or labels_default(cl)
    by_k = {c.k: c for c in cl}
    out = []
    for k in (order or [c.k for c in cl]):
        c = by_k[k]
        lab = labels[k]
        if c.kind == "table":
            out.append(f"{L['table_cap'].format(l=lab)}\n\n| Use K{k:02d} | Distance |\n|---|---|\n| A | 9 m |\n| B | 18 m |")
            continue
        if c.kind == "definition":
            out.append(f"{lab} K{k:02d} {L['term_def'].format(t=L['term'])}")
            continue
        parts = [f"{lab} K{k:02d} {L['base']}"]
        for j, link in enumerate(sorted(c.links, key=lambda x: x[0] == "inline")):       # an inline exception closes the sentence
            kw = L["kws"][(k + j + kw_shift) % 3]
            t = link[0]
            if t == "ref":
                parts.append(L["ref"].format(kw=kw, l=labels[link[1]]))
            elif t == "exc":
                parts.append(", " + L["exc"].format(kw=kw, l=labels[link[1]]))
            elif t == "table":
                parts.append(", " + L["table"].format(l=labels[link[1]]))
            elif t == "cond":
                parts[0] = f"{lab} K{k:02d} {L['cond'].format(kw=kw, l=labels[link[1]])}, " + L["base"][0].lower() + L["base"][1:]
            elif t == "use":
                parts.append(", " + L["use"].format(t=L["term"]))
            elif t == "inline":
                parts.append(", " + L["inline"])
            elif t == "ext":
                parts.append(", " + L["ext"])
            elif t == "dangling":
                parts.append(" " + L["dangling"])
            elif t == "unit":
                parts.append(". " + L["unit"])
        out.append(" ".join(p if not p.startswith(",") else p for p in parts).replace(" ,", ",") + ".")
    return "\n\n".join(out) + "\n"


def gold(cl: list[SClause]) -> set[tuple[str, str, str]]:
    """The edges the document was built to hold, as (consumer marker, provider marker, type); an inline exception is its own node
    and a definition is the clause that defines the term."""
    g: set[tuple[str, str, str]] = set()
    d = next(c for c in cl if c.kind == "definition")
    for c in cl:
        for link in c.links:
            t = link[0]
            me = f"K{c.k:02d}"
            if t == "ref":
                g.add((me, f"K{link[1]:02d}", "reference"))
            elif t == "exc":
                g.add((me, f"K{link[1]:02d}", "exception_of"))
            elif t == "cond":
                g.add((me, f"K{link[1]:02d}", "condition_from"))
            elif t == "table":
                g.add((me, f"K{link[1]:02d}", "table_of"))
            elif t == "use":
                g.add((me, f"K{d.k:02d}", "definition_of"))
            elif t == "inline":
                g.add((me, me + "#exc", "exception_of"))
    return g


def markers(graph) -> dict[str, str]:
    """clause id -> marker, read from the clause text."""
    out = {}
    for c in graph.clauses:
        m = re.search(r"\bK\d\d\b", c.text)
        if m:
            out[c.id] = m.group(0)
    return out


def edges_by_marker(graph) -> set[tuple[str, str, str]]:
    mk = markers(graph)
    got: set[tuple[str, str, str]] = set()
    for e in graph.edges:
        if not e.provider:
            continue
        me = mk.get(e.consumer)
        node = graph.nodes[e.provider]
        pr = mk.get(node.clause)
        if node.ntype == "exception" and node.clause == e.consumer:
            pr = (pr or "") + "#exc"
        if me and pr:
            got.add((me, pr, e.type))
    return got
