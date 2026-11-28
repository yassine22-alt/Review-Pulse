"""Round trip: tree -> plain words -> read again by a parser -> are the two trees equivalent?

The words are written by a program from fixed phrase tables (English, French, German), never by a model, so they cannot flatter the
tree. They are indented lists, so a person reads them next to the sentence and a parser can read them back:

    Obligation 1: must
    For every room r where:
      room type is equal to 'bedroom'
    Applies only when:
      ...
    The requirement:
      at least one of these:
        - floor area is at least 9 m2
        - ...
    Unless (unless):
      ...

`Parser` is the pluggable reader. `TemplateParser` inverts the templates exactly (it proves the writing loses nothing). A model parser
reads the same words and may return a different tree; `roundtrip` then says which node differs (equiv.py localises it).
A reader that cannot read the words, or returns something that does not validate, is a failed round trip, never a pass.
"""

from __future__ import annotations

import re
from typing import Protocol

from .equiv import EquivResult, equivalent
from .schema import Cond, Exc, FactSpec, NormTree, Obligation, Scope

LANGS = {
    "en": {
        "ob": "Obligation", "must": "must", "must_not": "must not", "every": "For every", "exists": "There is at least one", "where": "where",
        "applies": "Applies only when", "req": "The requirement", "unless": "Unless",
        "all": "all of these", "any": "at least one of these", "not": "it is not the case that",
        "true": "is true", "false": "is false", "unresolved": "Not decided",
        "ge": "is at least", "le": "is at most", "gt": "is more than", "lt": "is less than", "eq": "is equal to", "ne": "is not equal to",
    },
    "fr": {
        "ob": "Obligation", "must": "doit", "must_not": "ne doit pas", "every": "Pour chaque", "exists": "Il existe au moins un", "where": "tel que",
        "applies": "S'applique seulement si", "req": "L'exigence", "unless": "Sauf si",
        "all": "toutes ces conditions", "any": "au moins une de ces conditions", "not": "il n'est pas vrai que",
        "true": "est vrai", "false": "est faux", "unresolved": "Non decide",
        "ge": "est au moins", "le": "est au plus", "gt": "est superieur a", "lt": "est inferieur a", "eq": "est egal a",
        "ne": "est different de",
    },
    "de": {
        "ob": "Pflicht", "must": "muss", "must_not": "darf nicht", "every": "Fuer jedes", "exists": "Es gibt mindestens ein", "where": "mit",
        "applies": "Gilt nur wenn", "req": "Die Anforderung", "unless": "Ausser wenn",
        "all": "alle diese Bedingungen", "any": "mindestens eine dieser Bedingungen", "not": "es ist nicht der Fall dass",
        "true": "ist wahr", "false": "ist falsch", "unresolved": "Nicht entschieden",
        "ge": "ist mindestens", "le": "ist hoechstens", "gt": "ist groesser als", "lt": "ist kleiner als", "eq": "ist gleich",
        "ne": "ist ungleich",
    },
}
OPS = ("ge", "le", "gt", "lt", "eq", "ne")


class RoundTripError(ValueError):
    pass


def _num(v) -> str:
    return repr(float(v)) if isinstance(v, float) else str(v)


def labels(facts: list[FactSpec], lang: str) -> dict[str, str]:
    """A distinct wording for every fact: its label, or its name when two facts would read the same."""
    words = {f.name: f.words(lang) for f in facts}
    seen: dict[str, int] = {}
    for w in words.values():
        seen[w] = seen.get(w, 0) + 1
    return {n: (w if seen[w] == 1 else n) for n, w in words.items()}


def _cond_lines(c: Cond, tree: NormTree, lang: str, lab: dict[str, str], depth: int, bullet: bool) -> list[str]:
    T = LANGS[lang]
    pad = "  " * depth + ("- " if bullet else "")
    if c.kind == "test":
        spec = tree.fact(c.fact)
        if spec.kind == "boolean":
            phrase = T["true"] if (c.value is True) == (c.op == "eq") else T["false"]
            return [f"{pad}{lab[c.fact]} {phrase}"]
        if spec.kind == "string":
            return [f"{pad}{lab[c.fact]} {T[c.op]} '{c.value}'"]
        unit = f" {c.unit}" if c.unit != "1" else ""
        return [f"{pad}{lab[c.fact]} {T[c.op]} {_num(c.value)}{unit}"]
    head = {"all": T["all"], "any": T["any"], "not": T["not"]}[c.kind]
    out = [f"{pad}{head}:"]
    for a in c.args:
        out += _cond_lines(a, tree, lang, lab, depth + 1, True)
    return out


def to_words(tree: NormTree, lang: str | None = None) -> str:
    lang = lang or tree.language
    if lang not in LANGS:
        raise RoundTripError(f"no phrase table for language {lang!r}")
    T = LANGS[lang]
    lab = labels(tree.facts, lang)
    lines = []
    for i, ob in enumerate(tree.obligations, 1):
        lines.append(f"{T['ob']} {i}: {T['must'] if ob.modality == 'obligation' else T['must_not']}")
        if ob.scope:
            lines.append(f"{T['every'] if ob.scope.quantifier == 'forall' else T['exists']} {ob.scope.collection} {ob.scope.variable.lstrip('$')}" + (f" {T['where']}:" if ob.scope.where else ""))
            if ob.scope.where:
                lines += _cond_lines(ob.scope.where, tree, lang, lab, 1, False)
        if ob.applicability:
            lines.append(f"{T['applies']}:")
            lines += _cond_lines(ob.applicability, tree, lang, lab, 1, False)
        lines.append(f"{T['req']}:")
        lines += _cond_lines(ob.requirement, tree, lang, lab, 1, False)
        for e in ob.exceptions:
            lines.append(f"{T['unless']}:")
            lines += _cond_lines(e.when, tree, lang, lab, 1, False)
        for u in ob.unresolved:
            lines.append(f"{T['unresolved']}: {u}")
    return "\n".join(lines)


class Parser(Protocol):
    """Reads words back into a tree. A model parser sees `words` and the declared facts, and the text of the clause is NOT shown."""

    def parse(self, words: str, facts: list[FactSpec], language: str, tree: NormTree) -> NormTree | None: ...


class TemplateParser:
    """The exact inverse of `to_words`. It needs only the words and the fact list."""

    def parse(self, words: str, facts: list[FactSpec], language: str, tree: NormTree) -> NormTree | None:
        T = LANGS[language]
        lab = labels(facts, language)
        by_label = {w: n for n, w in lab.items()}
        spec = {f.name: f for f in facts}
        lines = [ln for ln in words.split("\n") if ln.strip()]
        pos = 0

        def indent(ln: str) -> int:
            return (len(ln) - len(ln.lstrip(" "))) // 2

        def parse_cond(depth: int) -> Cond:
            nonlocal pos
            ln = lines[pos]
            if indent(ln) != depth:
                raise RoundTripError(f"bad indentation at: {ln.strip()}")
            body = ln.strip()
            body = body[2:] if body.startswith("- ") else body
            pos += 1
            for kind, key in (("all", "all"), ("any", "any"), ("not", "not")):
                if body == T[key] + ":":
                    kids = []
                    while pos < len(lines) and indent(lines[pos]) == depth + 1 and lines[pos].strip().startswith("- "):
                        kids.append(parse_cond(depth + 1))
                    return Cond(kind=kind, args=kids)
            for name_words in sorted(by_label, key=len, reverse=True):
                if body.startswith(name_words + " "):
                    rest = body[len(name_words) + 1:]
                    f = spec[by_label[name_words]]
                    if f.kind == "boolean":
                        if rest not in (T["true"], T["false"]):
                            continue
                        return Cond(kind="test", fact=f.name, op="eq", value=rest == T["true"])
                    for op in sorted(OPS, key=lambda o: -len(T[o])):
                        if rest.startswith(T[op] + " "):
                            val = rest[len(T[op]) + 1:]
                            if f.kind == "string":
                                if len(val) < 2 or val[0] != "'" or val[-1] != "'":
                                    continue
                                return Cond(kind="test", fact=f.name, op=op, value=val[1:-1])
                            m = re.fullmatch(r"(-?[\d.]+(?:e[+-]?\d+)?)(?: (\S+))?", val)
                            if not m:
                                continue
                            num = float(m.group(1))
                            num = int(num) if num.is_integer() and "." not in m.group(1) and "e" not in m.group(1) else num
                            return Cond(kind="test", fact=f.name, op=op, value=num, unit=m.group(2) or "1")
            raise RoundTripError(f"cannot read: {body}")

        obs: list[Obligation] = []
        head = re.compile(rf"^{re.escape(T['ob'])} \d+: ({re.escape(T['must_not'])}|{re.escape(T['must'])})$")
        every = re.compile(rf"^({re.escape(T['every'])}|{re.escape(T['exists'])}) (\S+) (\S+)( {re.escape(T['where'])}:)?$")
        while pos < len(lines):
            m = head.match(lines[pos])
            if not m:
                raise RoundTripError(f"expected an obligation header at: {lines[pos].strip()}")
            pos += 1
            kw: dict = {"id": f"o{len(obs) + 1}", "modality": "prohibition" if m.group(1) == T["must_not"] else "obligation",
                        "exceptions": [], "unresolved": []}
            while pos < len(lines) and not head.match(lines[pos]):
                ln = lines[pos]
                em = every.match(ln)
                if em:
                    pos += 1
                    where = parse_cond(1) if em.group(4) else None
                    kw["scope"] = Scope(quantifier="forall" if em.group(1) == T["every"] else "exists",
                                        collection=em.group(2), variable="$" + em.group(3), where=where)
                elif ln == T["applies"] + ":":
                    pos += 1
                    kw["applicability"] = parse_cond(1)
                elif ln == T["req"] + ":":
                    pos += 1
                    kw["requirement"] = parse_cond(1)
                elif ln == T["unless"] + ":":
                    pos += 1
                    kw["exceptions"].append(Exc(when=parse_cond(1), cue=T["unless"].lower()))
                elif ln.startswith(T["unresolved"] + ": "):
                    pos += 1
                    kw["unresolved"].append(ln[len(T["unresolved"]) + 2:])
                else:
                    raise RoundTripError(f"cannot read: {ln.strip()}")
            if "requirement" not in kw:
                raise RoundTripError("an obligation without a requirement")
            obs.append(Obligation(**kw))
        return NormTree(clause_id=tree.clause_id, text=tree.text, language=language, document=tree.document, facts=facts, obligations=obs)


class RoundTrip:
    def __init__(self, ok: bool, words: str, reread: NormTree | None, equiv: EquivResult | None, error: str = ""):
        self.ok, self.words, self.reread, self.equiv, self.error = ok, words, reread, equiv, error

    @property
    def repair(self) -> list[str]:
        return self.equiv.repair if self.equiv is not None else []


def roundtrip(tree: NormTree, parser: Parser | None = None, lang: str | None = None, n_worlds: int = 128) -> RoundTrip:
    """tree -> words -> parser -> equivalence with the tree. A mismatch names the nodes to repair (`.repair`)."""
    lang = lang or tree.language
    words = to_words(tree, lang)
    parser = parser or TemplateParser()
    try:
        again = parser.parse(words, tree.facts, lang, tree)
    except (RoundTripError, ValueError) as exc:
        return RoundTrip(False, words, None, None, f"the words could not be read back: {exc}")
    if again is None:
        return RoundTrip(False, words, None, None, "the parser returned nothing")
    res = equivalent(tree, again, n_worlds=n_worlds)
    return RoundTrip(res.equivalent, words, again, res, "" if res.equivalent else res.reason)
