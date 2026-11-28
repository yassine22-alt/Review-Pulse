"""The quantity written in one table cell: '900', '0.9 m', '3\'-0"', '36"', '2 1/2"', '1-1/2 HR', '900 x 2100', '12.5 sf'.

A value is read as written, with the unit the cell states (or None); the unit is a symbol of interpreter/units.yaml so
that interpreter.units.convert turns it to any other. Feet and inches are returned in inches (exact), not in feet.
"""

from __future__ import annotations

import re

from .vocab import canonical_unit

_FRAC = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"
FEET_INCH = re.compile(rf"^\s*(?P<ft>\d+)\s*(?:'|ft\.?|feet|foot)\s*-?\s*(?:(?P<in>{_FRAC})\s*(?:\"|''|in\.?|inch(?:es)?)?)?\s*$", re.I)
INCH = re.compile(rf"^\s*(?P<in>{_FRAC})\s*(?:\"|''|in\.?|inch(?:es)?)\s*$", re.I)
NUMBER_UNIT = re.compile(r"^\s*(?P<n>[-+]?\d+(?:[.,]\d+)?)\s*(?P<u>[A-Za-z°%\"'][A-Za-z0-9°²³^./\"' ]{0,10}?)?\s*$")
MIXED = re.compile(r"^\s*(?P<a>\d+)\s*-\s*(?P<b>\d+)/(?P<c>\d+)\s*(?P<u>[A-Za-z\"']+)?\s*$")
SPLIT_SIZE = re.compile(r"\s*(?:x|×|\*|\bby\b)\s*", re.I)


def number(text: str) -> float | None:
    """A plain number: 12, 0,9, 0.9, 1,200, 2 1/2, 1/2."""
    s = text.strip()
    m = re.fullmatch(r"(\d+)\s+(\d+)/(\d+)", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.fullmatch(r"(\d+)/(\d+)", s)
    if m and int(m.group(2)):
        return int(m.group(1)) / int(m.group(2))
    if re.fullmatch(r"\d{1,3},\d{3}", s) and not s.startswith("0"):
        return float(s.replace(",", ""))
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", s):
        return float(s.replace(",", "."))
    return None


def quantity(text: str) -> tuple[float, str | None] | None:
    """(value, unit) of one cell, or None when the cell holds no single quantity."""
    s = (text or "").strip()
    if not s:
        return None
    m = FEET_INCH.match(s)
    if m and (m.group("in") is not None or "'" in s or re.search(r"ft|feet|foot", s, re.I)):
        inches = number(m.group("in")) if m.group("in") else 0.0
        if inches is not None:
            return (int(m.group("ft")) * 12 + inches, "in")
    m = INCH.match(s)
    if m:
        v = number(m.group("in"))
        return (v, "in") if v is not None else None
    m = MIXED.match(s)
    if m:
        v = int(m.group("a")) + int(m.group("b")) / int(m.group("c"))
        return (v, canonical_unit(m.group("u")) if m.group("u") else None)
    v = number(s)
    if v is not None:
        return (v, None)
    m = NUMBER_UNIT.match(s)
    if m and m.group("u"):
        u = canonical_unit(m.group("u").strip())
        if u:
            return (float(m.group("n").replace(",", ".")), u)
    return None


def size(text: str) -> list[tuple[float, str | None]] | None:
    """A size written as two quantities: '900 x 2100', '900 x 2100 mm', '3\'-0" x 6\'-8"', '0.9 m x 2.1 m'. Width first."""
    s = (text or "").strip()
    parts = SPLIT_SIZE.split(s)
    if len(parts) != 2:
        return None
    a, b = quantity(parts[0]), quantity(parts[1])
    if a is None or b is None:
        return None
    unit = a[1] or b[1]
    if a[1] and b[1] and a[1] != b[1]:
        unit = None
    return [(a[0], a[1] or unit), (b[0], b[1] or unit)]


def looks_like_tag(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{0,3}[ -]?\d{1,4}[A-Za-z]?(?:[ -]?\d{1,2})?|[A-Za-z]{1,2}", (text or "").strip()))


def has_digit(text: str) -> bool:
    return bool(re.search(r"\d", text or ""))


def entity_key(text: str) -> str:
    """The key of a row: 'D-12', 'd12' and 'D 012' are D12 (annotate.text_classify.tag_key); a bare number loses its leading zeros."""
    from ..annotate.text_classify import tag_key

    k = tag_key(text)
    return str(int(k)) if k.isdigit() else k
