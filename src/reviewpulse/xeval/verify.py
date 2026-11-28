"""Deterministic checks of a drafted rule against the sentence it came from. No model, no labels.

A rule can be valid (every name exists, units match) and still say something different from the sentence. These
checks catch the ways that actually happened: a category word dropped from the rule (the rule then covers every
member), a number in the rule that the sentence never states, a number in the sentence that the rule ignores, and a
comparison pointing the wrong way. Issues marked `blocking` stop the draft; the others are shown to the reviewer.

Language-agnostic by construction: digits, units and symbols are universal; wording (at least / au moins / mindestens)
lives in `cues.yaml`. When a sentence is in a language with no wording table, the wording check does not run and the
result says so (`unchecked` notice) instead of passing or blocking on a guess.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

import yaml

from ..interpreter.schema import (
    BinaryExpr,
    FactExpr,
    LinkExpr,
    LiteralExpr,
    LogicExpr,
    PathExpr,
    Program,
    SetExpr,
    walk,
)
from .demand import quantities

BARE_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w²])")
FLIP = {"ge": "le", "le": "ge", "gt": "lt", "lt": "gt", "eq": "eq", "ne": "ne"}
CANON = {"mm": 0.001, "cm": 0.01, "m": 1.0, "m2": 1.0, "ratio": 1.0, "%": 0.01, "km": 1000.0}      # fallback only


def si_factor(unit: str) -> float | None:
    """The factor to the coherent SI unit for any unit the table knows; None when the unit is not recognised."""
    from ..interpreter import units as U

    if unit in ("ratio", "1"):
        return 1.0
    if U.is_unit(unit) and not U.parse_unit(unit).offset:
        return U.parse_unit(unit).factor
    return CANON.get(unit)
UNIT_SCALES = (1.0, 0.01, 0.001)       # a number with an unrecognised unit word may be cm or mm of a metre rule
REFERENCE = re.compile(
    r"\b(?:articles?|art\.?|sections?|clauses?|paragraphs?|para\.?|tables?|figures?|annex(?:es?)?|appendix|chapters?|"
    r"parts?|schedules?|regulations?|standards?|en|iso|nf|din|bs|dtu|alin[ée]as?|tableaux?|chapitres?|paragraphes?|"
    r"norme|artikel|abschnitt|tabelle|anhang|artículo|tabla|anexo|articolo|tabella|allegato|artigo|tabela)"
    r"\s+[A-Za-z]?\d+(?:[.\-]\d+)*(?:\s?\([a-z0-9]+\))*", re.I)


@dataclass
class Issue:
    code: str
    message: str
    blocking: bool = True


# ---- language data ---------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def wording() -> dict:
    return yaml.safe_load((Path(__file__).with_name("cues.yaml")).read_text(encoding="utf-8"))


def detect_language(text: str) -> str | None:
    """The language whose function words appear most often; None when the evidence is thin or tied."""
    tokens = set(re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text.lower()))
    scores = {code: len(tokens & set(spec["words"])) for code, spec in wording().items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    # one function word is enough when no other language shares it ("must" is English only): short checklist lines have few
    if not ranked or ranked[0][1] < 1 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
        return None
    return ranked[0][0]


@cache
def _cue_regexes(lang: str) -> list[tuple[re.Pattern, str]]:
    spec = wording()[lang]
    out = []
    for op in ("ge", "le", "gt", "lt"):
        phrases = sorted(spec.get(op, []), key=len, reverse=True)
        if phrases:
            out.append((re.compile("|".join(re.escape(p) for p in phrases)), op))
    return out


@cache
def _after_regexes(lang: str) -> list[tuple[re.Pattern, str]]:
    gap = r"(?:[^\W\d_]+['’]?\s){0,2}"        # up to two words between the number and the cue: "3 storeys or fewer"
    spec = wording()[lang]
    out = []
    for key, op in (("after_le", "le"), ("after_ge", "ge")):
        phrases = sorted(spec.get(key, []), key=len, reverse=True)
        if phrases:
            out.append((re.compile(gap + "(?:" + "|".join(re.escape(p) for p in phrases) + ")"), op))
    return out


# ---- reading the numbers of a sentence -------------------------------------------------------------


def normalise_digits(text: str) -> str:
    """Any script's decimal digits (Arabic-Indic, fullwidth, ...) become 0-9."""
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() and not c.isascii() else c for c in text)


def prepare(text: str) -> str:
    """The text the checks read: digits normalised, references to other clauses removed, spaces collapsed."""
    text = normalise_digits(text)
    text = REFERENCE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _decimal_comma(lang: str | None, flat: str) -> bool:
    if lang and lang in wording():
        return wording()[lang]["decimal"] == ","
    return bool(re.search(r"\d,\d{1,2}(?!\d)", flat)) and not re.search(r"\d\.\d", flat)


def number_spans(text: str, comma: bool) -> list[tuple[float, int, int, bool]]:
    """Every number the sentence states: (value in rule units, start, end, written without a recognised unit)."""
    flat = prepare(text)
    found = []
    for q in quantities(flat, comma):
        factor = si_factor(q.unit)
        found.append((round(q.value * (factor if factor is not None else 1.0), 9), q.span[0], q.span[1], factor is None))
    for m in BARE_NUMBER.finditer(flat):
        if not any(a <= m.start() < b for _, a, b, _ in found):
            raw = m.group(0)
            value = float(raw.replace(",", ".")) if comma or re.fullmatch(r"\d+,\d{1,2}", raw) \
                else float(raw.replace(",", ""))
            found.append((round(value, 9), m.start(), m.end(), True))
    return sorted(found, key=lambda t: t[1])


def number_words(text: str, lang: str | None) -> list[float]:
    if not lang or lang not in wording():
        return []
    low = text.lower()
    table = wording()[lang]
    if "number_continuations" in table:
        low = "".join("-" if unicodedata.category(char) == "Pd" else char for char in low)
        numbers = {" ".join(re.findall(r"[^\W\d_]+", word.lower())): float(value)
                   for word, value in table.get("numbers", {}).items()}
        pieces = {piece for phrase in numbers for piece in phrase.split()} | set(table["number_continuations"])
        tokens = list(re.finditer(r"[^\W\d_]+", low))
        result, index = [], 0
        while index < len(tokens):
            if tokens[index].group() not in pieces:
                index += 1
                continue
            end = index + 1
            while (end < len(tokens) and tokens[end].group() in pieces and
                   re.fullmatch(r"[\s\-–]+", low[tokens[end - 1].end():tokens[end].start()])):
                end += 1
            phrase = " ".join(token.group() for token in tokens[index:end])
            if phrase in numbers:
                result.append(numbers[phrase])
            index = end
        return result
    return [float(n) for w, n in wording()[lang].get("numbers", {}).items()
            if re.search(rf"(?<![^\W\d_]){re.escape(w)}(?![^\W\d_])", low)]


def program_numbers(program: Program) -> list[float]:
    """Every number the rule uses, in coherent SI, whatever unit the fact it is compared with is declared in."""
    out = []
    for expr in (program.applicability, program.exemption, program.requirement):
        for node in walk(expr):
            if isinstance(node, LiteralExpr) and not isinstance(node.value, (bool, str)):
                factor = si_factor(node.unit) if node.unit not in ("1", "count") else 1.0
                out.append(round(float(node.value) * (factor if factor is not None else 1.0), 9))
    return out


def _match(value: float, pool: list[float], scales: tuple[float, ...] = (1.0,)) -> bool:
    return any(abs(value * s - p) <= 1e-6 * max(1.0, abs(p)) for p in pool for s in scales)


def check_numbers(program: Program, text: str, lang: str | None) -> list[Issue]:
    comma = _decimal_comma(lang, prepare(text))
    spans = number_spans(text, comma)
    used = program_numbers(program)
    allowed = [v for v, *_ in spans] + [v * s for v, _, _, bare in spans if bare for s in UNIT_SCALES] \
        + number_words(text, lang)
    issues = []
    for value in sorted(set(used)):
        if value in (0.0, 1.0) and not _match(value, allowed):
            continue                     # structural constants (zero, one) are allowed
        if not _match(value, allowed):
            issues.append(Issue("number_not_in_sentence", f"the rule uses {value:g}, which the sentence does not state"))
    existential = any(isinstance(n, SetExpr) and n.node in ("exists", "count") for e in (program.applicability, program.exemption,
                                                                                     program.requirement) for n in walk(e))
    for value, _, _, bare in spans:
        if value == 1.0 and existential:
            continue                     # "1 egress door required": the one is the quantifier (exists), not a figure to compare with
        if not _match(value, used, UNIT_SCALES if bare else (1.0,)):
            issues.append(Issue("number_ignored", f"the sentence states {value:g}, but the rule never uses it"))
    return issues


# ---- direction of comparisons ----------------------------------------------------------------------


def _expected_operator(flat: str, start: int, end: int, lang: str) -> str | None:
    tail = flat[end:end + 40].lower().lstrip()
    for pattern, op in _after_regexes(lang):
        if pattern.match(tail):
            return op
    window = flat[max(0, start - 40):start].lower()
    best = None
    for pattern, op in _cue_regexes(lang):
        for m in pattern.finditer(window):
            key = (m.end(), m.end() - m.start())
            if best is None or key > best[0]:
                best = (key, op, m.start())
    if not best or best[0][0] < len(window) - 6:
        return None
    op = best[1]
    prefix = window[:best[2]]
    if any(re.search(rf"(?<!\w){re.escape(cue)}(?!\w)", prefix)
           for cue in wording()[lang].get("negation_before_comparison", [])):
        op = {"gt": "le", "ge": "lt", "lt": "ge", "le": "gt"}[op]
    return op


def check_directions(program: Program, text: str, lang: str) -> list[Issue]:
    flat = prepare(text)
    comma = _decimal_comma(lang, flat)
    spans = number_spans(flat, comma)
    issues = []
    for expr in (program.applicability, program.exemption, program.requirement):
        for node in walk(expr):
            if not (isinstance(node, BinaryExpr) and node.node in FLIP and node.node not in ("eq", "ne")):
                continue
            lit, op = None, node.node
            if isinstance(node.right, LiteralExpr) and not isinstance(node.left, LiteralExpr):
                lit = node.right
            elif isinstance(node.left, LiteralExpr):
                lit, op = node.left, FLIP[op]
            if lit is None or isinstance(lit.value, (bool, str)):
                continue
            value = round(float(lit.value), 9)
            hits = [(a, b) for v, a, b, _ in spans if abs(v - value) <= 1e-6 * max(1.0, abs(v))]
            if len(hits) != 1:          # not stated, or stated twice: the sentence does not say which is meant
                continue
            expected = _expected_operator(flat, hits[0][0], hits[0][1], lang)
            if expected and expected != op:
                issues.append(Issue("direction", f"the sentence implies '{expected}' around {lit.value:g} "
                                                 f"but the rule uses '{op}'"))
    return issues


# ---- category (scope) ------------------------------------------------------------------------------


def fold_accents(text: str) -> str:
    """Lower-case text without accents or umlauts ("séjour" -> "sejour", "küche" -> "kuche", "straße" -> "strasse"). The category
    labels of the fact graph are written without them, so a sentence must be folded the same way before they are compared."""
    import unicodedata

    text = text.lower().replace("ß", "ss")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _names(word: str, low: str) -> bool:
    """Does the (folded, lower-case) text name this category word? A whole word, or the word with a short ending, so that the label
    'stair' is named by 'stairways' and 'bedroom' by 'bedrooms'. Short words (under four letters) must match whole."""
    w = re.escape(fold_accents(word.lower()))
    tail = r"[^\W\d_]{0,4}" if len(word) >= 4 else ""
    return re.search(rf"(?<![^\W\d_]){w}{tail}(?![^\W\d_])", low) is not None


@cache
def _label_languages() -> dict[str, frozenset[str]]:
    """Each room word of the curated lexicon -> the languages it belongs to ("scale" is Italian for stairs, not the English word)."""
    path = Path(__file__).resolve().parents[1] / "annotate" / "lexicon" / "curated.yaml"
    out: dict[str, set[str]] = {}
    for entries in yaml.safe_load(path.read_text(encoding="utf-8"))["types"].values():
        for lang, words in (entries or {}).items():
            for word in words:
                out.setdefault(fold_accents(str(word).lower()), set()).add(lang)
    return {w: frozenset(v) for w, v in out.items()}


def _foreign(word: str, lang: str | None) -> bool:
    """A label word that only other languages than the sentence's write: it is not a mention of the category."""
    if lang is None:
        return False
    table = _label_languages()
    w = fold_accents(word.lower())
    langs = table.get(w) or table.get(w[:-1]) if w[-1:] in ("s", "x") else table.get(w)
    return bool(langs) and lang not in langs


def named_categories(text: str, cat: dict, fact: str) -> list[str]:
    """The category values (or group names) of `fact` that the sentence names in words: the candidates the model must confirm."""
    low = fold_accents(prepare(text).lower())
    lang = detect_language(prepare(text))
    labels = cat.get("kind_labels", {}).get(fact, {})
    found = []
    for value in cat.get("kinds", {}).get(fact, []):
        words = set(labels.get(value, [])) | {value.replace("_", " ")}
        if any(_names(w, low) for w in words if w and not _foreign(w, lang)):
            found.append(value)
    for term in (cat.get("groups", {}).get(fact) or {}):
        if re.search(rf"(?<![^\W\d_]){re.escape(term.split()[0])}", low):
            found.append(term)
    return found


def check_scope(program: Program, text: str, cat: dict) -> list[Issue]:
    """Every category the sentence names must appear in the rule as a condition, or the rule covers everything."""
    low = fold_accents(prepare(text).lower())
    lang = detect_language(prepare(text))
    used = set()                      # (category fact, value) pairs the rule compares, so 'external' on doors is not
    for expr in (program.applicability, program.exemption, program.requirement):     # mistaken for 'external' on stairs
        for node in walk(expr):
            if isinstance(node, BinaryExpr) and node.node in ("eq", "ne"):
                for a, b in ((node.left, node.right), (node.right, node.left)):
                    if isinstance(b, LiteralExpr) and isinstance(b.value, str) and hasattr(a, "name"):
                        used.add((a.name, b.value))
    issues = []
    for fact, values in cat.get("kinds", {}).items():
        labels = cat.get("kind_labels", {}).get(fact, {})
        for value in values:
            words = set(labels.get(value, []))
            if not words or sum(value in vs for vs in cat["kinds"].values()) == 1:
                words.add(value.replace("_", " "))       # a value shared by several facts ("external") is ambiguous
            mentioned = any(_names(w, low) for w in words if w and not _foreign(w, lang))
            for term, members in cat.get("groups", {}).get(fact, {}).items():
                if value in members and re.search(rf"(?<![^\W\d_]){re.escape(term.split()[0])}", low):
                    mentioned = True        # the sentence names a group the document defined, which includes this value
            if mentioned and (fact, value) not in used:
                issues.append(Issue("scope_dropped", f"the sentence names '{value}' but the rule has no condition "
                                                     f"on it, so it applies to every member"))
            if (fact, value) in used and not mentioned:
                issues.append(Issue("scope_invented", f"the rule restricts to '{value}', which the sentence "
                                                      f"does not name"))
    return issues


def _requirement_parts(expr):
    """The nodes of a requirement that say what must hold: everything except the `where` of a quantifier, which only picks the members."""
    yield expr
    if isinstance(expr, SetExpr):
        children = [expr.body] if expr.body is not None else []
    elif isinstance(expr, LogicExpr):
        children = expr.args
    elif isinstance(expr, BinaryExpr):
        children = [expr.left, expr.right]
    else:
        children = []
    for child in children:
        yield from _requirement_parts(child)


def _is_positive_test(node: BinaryExpr, cat: dict) -> bool:
    """`area > 0`, `width >= 0`, `0 < length`: a measured size (an area, a width, a count) compared with zero or less. A size is never
    negative and a drawn element is never empty, so the test passes whatever the plan shows ("Square Footage" became "every room has
    an area above zero")."""
    left, right, op = node.left, node.right, node.node
    if isinstance(left, LiteralExpr) and isinstance(right, FactExpr):
        left, right, op = right, left, {"lt": "gt", "le": "ge", "gt": "lt", "ge": "le"}[op]
    if not (isinstance(left, FactExpr) and isinstance(right, LiteralExpr)):
        return False
    value = right.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    kind = cat.get("bindings", {}).get(left.name, {}).get("kind")
    if kind is not None and kind != "number":
        return False
    return (op == "ge" and value <= 0) or (op == "gt" and value < 0) or (op == "gt" and value == 0)


def check_vacuous(program: Program, cat: dict) -> list[Issue]:
    """A rule that cannot fail says nothing, and an unnoticed rule that always passes is worse than no rule ("true", "every bedroom:
    true", "room type equals room type", "room type is bedroom" for rooms already picked as bedrooms). The requirement must test a
    measured or yes/no fact, a route or a link, and must never compare a thing with itself."""
    kinds = set(cat.get("kinds", {}))
    tested, issues = False, []
    for node in _requirement_parts(program.requirement):
        if isinstance(node, (PathExpr, LinkExpr)) or (isinstance(node, SetExpr) and node.node in ("count", "sum", "min", "max")):
            tested = True
        elif isinstance(node, FactExpr) and node.name not in kinds:
            tested = True
        elif isinstance(node, BinaryExpr) and node.node in ("eq", "ne", "lt", "le", "gt", "ge") \
                and node.left.model_dump() == node.right.model_dump():
            issues.append(Issue("vacuous", "the rule compares a value with itself, so it can never fail or can never pass"))
        elif isinstance(node, BinaryExpr) and node.node in ("lt", "le", "gt", "ge") and _is_positive_test(node, cat):
            issues.append(Issue("vacuous", "the rule only says a measured size is above zero, which every real element satisfies"))
    if not tested:
        issues.append(Issue("vacuous", "the rule tests no measured or yes/no fact and no route, so it would pass whatever the plan shows"))
    return issues


def check_alternatives(program: Program, text: str, lang: str | None) -> list[Issue]:
    """"Bathrooms need a 3 sq ft window or a mechanical exhaust": a rule with no `or` in it demands only the first alternative and would
    fail a plan that meets the second. A sentence with an alternative and a rule without one is not accepted."""
    if not lang or lang not in wording():
        return []
    table = wording()[lang]
    cues = table.get("either", [])
    if not cues:
        return []
    low = text.lower()
    for tail in sorted(table.get("after_le", []) + table.get("after_ge", []), key=len, reverse=True):
        low = low.replace(tail.lower(), " ")            # "3 storeys or fewer" is a comparison, not an alternative
    if not any(re.search(rf"(?<![^\W\d_]){re.escape(c)}(?![^\W\d_])", low) for c in cues):
        return []
    # a route or a link already stands for "door or opening" (its edge kinds); a rule with an `or` of its own has the alternative
    if any((isinstance(n, LogicExpr) and n.node == "any") or isinstance(n, (PathExpr, LinkExpr))
           or (isinstance(n, FactExpr) and n.name.startswith(("links_", "reaches_")))
           for e in (program.applicability, program.exemption, program.requirement) for n in walk(e)):
        return []
    return [Issue("alternative_dropped", "the sentence offers an alternative ('or') but the rule has none, so it demands only one of them")]


def check_aggregate(program: Program, text: str, lang: str) -> list[Issue]:
    """A sentence that speaks of a sum over members needs a sum (or count/min/max) in the rule, not a per-member test."""
    low = prepare(text).lower()
    cues = wording()[lang].get("aggregate", [])
    if not any(re.search(rf"(?<![^\W\d_]){re.escape(c)}(?![^\W\d_])", low) for c in cues):
        return []
    for expr in (program.applicability, program.exemption, program.requirement):
        if any(getattr(n, "node", None) in ("sum", "count", "min", "max") for n in walk(expr)):
            return []
    return [Issue("aggregate_missing", "the sentence speaks of a sum over several members, but the rule tests each "
                                       "member on its own")]


def check_route(program: Program) -> list[Issue]:
    """A route rule ("reaches an exit without passing through ...") cannot be compared with its sentence by any check here:
    who may be passed through is exactly what a model gets wrong. It is allowed, but the reviewer is told to read it."""
    from ..interpreter.schema import LinkExpr, PathExpr

    for expr in (program.applicability, program.exemption, program.requirement):
        if any(isinstance(n, (PathExpr, LinkExpr)) for n in walk(expr)):
            return [Issue("route_unchecked", "this rule is about routes between rooms; no automatic check can confirm which "
                                             "rooms the sentence allows a route to pass through, so read the rule carefully",
                          blocking=False)]
    return []


# ---- entry point -----------------------------------------------------------------------------------


def verify(program: Program, text: str, cat: dict, lang: str | None = None, grounding_words: bool = True) -> list[Issue]:
    """All checks. `lang` is a hint; otherwise it is detected. Wording checks run only for languages with a table.
    `grounding_words`: the English word-overlap test between the sentence and the measured fact. A rule a program wrote from an explicit
    multiple choice of the fact has been grounded more precisely (interpreter/grounding.py), and the overlap test, which cannot know
    that "wide" is the same quantity as "width", would only refuse it; those arms turn it off."""
    flat = prepare(text)
    code = lang if lang in wording() else detect_language(flat)
    from .semantic import check_grounding_words, check_owners, check_values

    # the parts of the sentence the rule declares it does not cover are not held against it: their figures are not "ignored"
    covered = flat
    for part in program.not_checked:
        covered = covered.replace(part, " ")
    issues = check_scope(program, flat, cat) + check_numbers(program, covered, code) \
        + check_owners(program, cat) + check_values(program, cat) + check_route(program) + check_vacuous(program, cat)
    if code:
        issues += check_directions(program, covered, code) + check_aggregate(program, text, code) \
            + check_alternatives(program, covered, code)
        if code == "en" and grounding_words:
            issues += check_grounding_words(program, text, cat)
    else:
        issues.append(Issue("unchecked", "the comparison wording was not checked: this sentence's language has no "
                                         "wording table, so a person should read the direction", blocking=False))
    return issues


def blocking(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.blocking]
