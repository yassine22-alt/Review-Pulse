"""Reading the value part of a label-value pair: numbers with units and locale, yes/no, counts in words, category words."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..drawingset.vocab import fold
from .spec import Field, Spec, find_run, tokens

NUM = re.compile(r"\d{1,3}(?:[ '’.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")
FEET_INCHES = re.compile(r"(\d+)\s*(?:'|′|ft\.?)\s*-?\s*(?:(\d+(?:\.\d+)?)\s*(?:\"|″|in\.?)?)?")
LEAD = re.compile(r"^(?:ca\.?|circa|approx\.?|approximately|about|~|≈|min\.?|max\.?)\s*", re.I)


@dataclass
class Parsed:
    status: str                    # value, unstated, reject
    value: float | int | str | bool | None = None
    unit: str = "1"
    note: str = ""
    canonical: bool = True         # a category value found in the vocabulary (or a code pattern) rather than raw words


def parse_number(tok: str, lang: str = "", unit: str = "") -> float | None:
    """A written number: 1,092 / 1.092 / 61,3 / 1 092,5 / 4'586. The language of the label and the unit settle which
    mark is the decimal one; a mark followed by a group of three digits is a thousands mark unless the language writes
    its decimals that way."""
    s = tok.strip().replace(" ", " ").replace("\xa0", " ").replace("’", "'")
    if not re.fullmatch(r"\d[\d .,']*\d|\d", s):
        return None
    marks = [(i, c) for i, c in enumerate(s) if c in ".,' "]
    if not marks:
        return float(s)
    if any(c in "' " for _, c in marks):
        body = re.sub(r"[ ']", "", s)
        return float(body.replace(",", ".")) if body.count(",") + body.count(".") <= 1 else None
    kinds = {c for _, c in marks}
    if len(kinds) == 2:                                    # 1,092.5 or 1.092,5: the last mark is the decimal one
        last = marks[-1][1]
        other = "," if last == "." else "."
        return float(s.replace(other, "").replace(last, "."))
    c = marks[0][1]
    if len(marks) > 1:                                     # 1,092,000: thousands marks
        return float(s.replace(c, ""))
    tail = s[marks[0][0] + 1:]
    if len(tail) != 3:
        return float(s.replace(c, "."))
    imperial = unit in ("ft2", "ft")
    comma_is_decimal = lang in ("de", "fr") and not imperial
    if c == ",":
        return float(s.replace(",", ".")) if comma_is_decimal else float(s.replace(",", ""))
    return float(s.replace(".", "")) if lang in ("de", "fr") and not imperial else float(s)


def _unit_of(text: str, spec: Spec) -> tuple[str | None, str]:
    """A unit symbol read at the start of `text` and the rest after it."""
    t = fold(text).replace("'", " ")
    ms = list(re.finditer(r"[a-z0-9]+", t))
    if ms and not re.search(r"[a-z0-9]", t[:ms[0].start()]):
        for n in (3, 2, 1):
            ws = tuple(m.group() for m in ms[:n])
            if len(ws) == n and ws in spec.unit_words:
                return spec.unit_words[ws], t[ms[n - 1].end():].strip(" .,;:/)]")
    return None, t.strip()


def is_unstated(text: str, spec: Spec) -> bool:
    t = text.strip().strip(".:;")
    if t in ("", "-", "--", "?", "\u2014", "\u2013", "/"):
        return True
    return tokens(t) in spec.unstated


def parse_value(f: Field, text: str, spec: Spec, lang: str = "", unit_hint: str | None = None) -> Parsed:
    text = text.strip().lstrip(":=").strip()
    if not text or is_unstated(text, spec):
        return Parsed("unstated", note=text or "empty")
    if f.kind == "bool":
        return _bool(f, text, spec)
    if f.kind == "number":
        return _number(f, text, spec, lang, unit_hint)
    return _category(f, text, spec)


def _bool(f: Field, text: str, spec: Spec) -> Parsed:
    t = tokens(text)
    for phrases, val in ((f.false_phrases, False), (f.true_phrases, True)):
        for p in phrases:
            if find_run(t, p) >= 0:
                return Parsed("value", val, note="stated phrase")
    if not t:
        return Parsed("reject", note="no words")
    for words, val in ((spec.false_words, False), (spec.true_words, True)):
        for w in sorted(words, key=len, reverse=True):
            if t[:len(w)] == w and (len(t) == len(w) or len(t) <= len(w) + 3):
                return Parsed("value", val)
    return Parsed("reject", note=f"not a yes or no: {text[:40]}")


def _number(f: Field, text: str, spec: Spec, lang: str, unit_hint: str | None) -> Parsed:
    t = LEAD.sub("", text.strip())
    is_len = f.unit == "m"
    if is_len:
        m = FEET_INCHES.match(t)
        if m:
            feet = float(m.group(1)) + (float(m.group(2)) / 12 if m.group(2) else 0.0)
            return Parsed("value", round(feet * spec.length_to_m["ft"], 4), "m", f"{text[:30]} (feet and inches)")
    m = NUM.match(t)
    if not m:
        word = tokens(t)[:1]
        if f.unit == "1" and word:
            for table in ([spec.number_words.get(lang, {})] if lang else []) + list(spec.number_words.values()):
                if word[0] in table:
                    return Parsed("value", table[word[0]], "1", note="number written in words")
        return Parsed("reject", note=f"no number in: {text[:40]}")
    unit, rest = _unit_of(t[m.end():], spec)
    if f.unit == "1":
        n = parse_number(m.group(), lang)
        if n is None or n != int(n) or n < 0:
            return Parsed("reject", note=f"not a count: {text[:40]}")
        words = set(tokens(rest))
        if rest.strip() and not (words & f.storey_words) and not rest.strip().startswith("("):
            return Parsed("reject", note=f"count followed by other words: {text[:40]}")
        return Parsed("value", int(n), "1")
    if re.search(r"[a-z]", rest) and not rest.startswith("("):
        return Parsed("reject", note=f"number followed by other words: {text[:40]}")
    sym = unit or unit_hint
    if sym is None:
        return Parsed("unstated", note=f"number {m.group()} with no unit: {text[:30]}")
    n = parse_number(m.group(), lang, sym)
    if n is None:
        return Parsed("reject", note=f"unreadable number: {text[:40]}")
    table = spec.length_to_m if is_len else spec.area_to_m2
    if sym not in table:
        return Parsed("reject", note=f"unit {sym} is not a {'length' if is_len else 'area'}")
    return Parsed("value", round(n * table[sym], 4), "m" if is_len else "m2", f"{text[:30]}")


def vocab_match(f: Field, text: str) -> tuple[str, int] | None:
    """The canonical value whose words (longest) occur in the text, with how many words matched."""
    t = tokens(text)
    best: tuple[str, int] | None = None
    for canon, phrases in f.values.items():
        for p in phrases:
            if find_run(t, p) >= 0 and (best is None or len(p) > best[1]):
                best = (canon, len(p))
    return best


def _category(f: Field, text: str, spec: Spec) -> Parsed:
    compact = re.sub(r"\s+", "", fold(text)).strip(".,;")
    for rx in f.patterns:
        if rx.match(compact):
            return Parsed("value", text.strip().upper().replace(" ", ""), note="coded value")
    hit = vocab_match(f, text)
    if hit:
        return Parsed("value", hit[0])
    if f.value_patterns:
        if any(rx.search(fold(text)) for rx in f.value_patterns):
            return Parsed("value", re.sub(r"\s+", " ", text.strip()), note="free text")
        return Parsed("reject", note=f"not a code or edition: {text[:40]}")
    if f.free:
        return Parsed("value", re.sub(r"\s+", " ", text.strip()), note="free text")
    return Parsed("value", re.sub(r"\s+", " ", fold(text)), note="words not in the vocabulary", canonical=False)
