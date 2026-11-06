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

from ..interpreter.schema import BinaryExpr, LiteralExpr, Program, walk
from .demand import quantities

BARE_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w²])")
FLIP = {"ge": "le", "le": "ge", "gt": "lt", "lt": "gt", "eq": "eq", "ne": "ne"}
CANON = {"mm": 0.001, "cm": 0.01, "m": 1.0, "m2": 1.0, "ratio": 1.0, "%": 0.01, "km": 1000.0}
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
    if not ranked or ranked[0][1] < 2 or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]):
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
        found.append((round(q.value * CANON.get(q.unit, 1.0), 9), q.span[0], q.span[1], q.unit not in CANON))
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
    return [float(n) for w, n in wording()[lang].get("numbers", {}).items()
            if re.search(rf"(?<![^\W\d_]){re.escape(w)}(?![^\W\d_])", low)]


def program_numbers(program: Program) -> list[float]:
    return [round(float(node.value), 9)
            for expr in (program.applicability, program.exemption, program.requirement) for node in walk(expr)
            if isinstance(node, LiteralExpr) and not isinstance(node.value, (bool, str))]


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
    for value, _, _, bare in spans:
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
                best = (key, op)
    return best[1] if best and best[0][0] >= len(window) - 6 else None


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


def check_scope(program: Program, text: str, cat: dict) -> list[Issue]:
    """Every category the sentence names must appear in the rule as a condition, or the rule covers everything."""
    low = prepare(text).lower()
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
            mentioned = any(re.search(rf"(?<![^\W\d_]){re.escape(w.lower())}(?![^\W\d_])", low) for w in words if w)
            if mentioned and (fact, value) not in used:
                issues.append(Issue("scope_dropped", f"the sentence names '{value}' but the rule has no condition "
                                                     f"on it, so it applies to every member"))
            if (fact, value) in used and not mentioned:
                issues.append(Issue("scope_invented", f"the rule restricts to '{value}', which the sentence "
                                                      f"does not name"))
    return issues


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


# ---- entry point -----------------------------------------------------------------------------------


def verify(program: Program, text: str, cat: dict, lang: str | None = None) -> list[Issue]:
    """All checks. `lang` is a hint; otherwise it is detected. Wording checks run only for languages with a table."""
    flat = prepare(text)
    code = lang if lang in wording() else detect_language(flat)
    from .semantic import check_grounding_words, check_owners, check_values

    issues = check_scope(program, flat, cat) + check_numbers(program, text, code) \
        + check_owners(program, cat) + check_values(program, cat)
    if code:
        issues += check_directions(program, text, code) + check_aggregate(program, text, code)
        if code == "en":
            issues += check_grounding_words(program, text, cat)
    else:
        issues.append(Issue("unchecked", "the comparison wording was not checked: this sentence's language has no "
                                         "wording table, so a person should read the direction", blocking=False))
    return issues


def blocking(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.blocking]
