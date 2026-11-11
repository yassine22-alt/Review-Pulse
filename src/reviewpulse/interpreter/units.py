"""Units of measure by dimensional analysis: a factor to the coherent SI unit and a vector of exponents (UCUM, QUDT).

Any unit written in a requirement or declared by a fact is parsed here, so the rule language is not limited to a list of
units a domain happened to need: kPa, L, kg/m3, min, mm2, ft, deg C are all understood, and a comparison between
incompatible quantities (a pressure against a length) is refused before anything runs.

  parse_unit("kg/m3")             a Unit(factor, dims, offset)
  same_unit("cm", "0.01.m")       True: same dimensions and same scale
  convert(90, "cm", "m")          0.9
  combine("m", "m", "mul")        "m2"; combine("m2", "m", "div") gives "m"
  to_si(2.5, "kPa")               2500.0 (the value in the coherent unit)

Grammar (as UCUM): factors joined by `.` or `*` (product) and `/` (quotient), read left to right; a factor is a unit
symbol with an optional SI prefix and an optional integer exponent (`m2`, `s-1`, `m^2`), a number, or a parenthesised
group. An offset unit (degC, degF) converts between its own kinds but cannot be multiplied or divided: use K.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DATA = yaml.safe_load(Path(__file__).with_name("units.yaml").read_text(encoding="utf-8"))
BASE: tuple[str, ...] = tuple(_DATA["base"])
ZERO = (0,) * len(BASE)


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class Unit:
    factor: float
    dims: tuple[int, ...]
    offset: float = 0.0

    def __mul__(self, other: Unit) -> Unit:
        _no_offset(self, other)
        return Unit(self.factor * other.factor, tuple(a + b for a, b in zip(self.dims, other.dims, strict=True)))

    def __truediv__(self, other: Unit) -> Unit:
        _no_offset(self, other)
        return Unit(self.factor / other.factor, tuple(a - b for a, b in zip(self.dims, other.dims, strict=True)))

    def __pow__(self, n: int) -> Unit:
        _no_offset(self)
        return Unit(self.factor ** n, tuple(a * n for a in self.dims))


def _no_offset(*units: Unit) -> None:
    if any(u.offset for u in units):
        raise UnitError("a temperature on an offset scale (degC, degF) cannot be multiplied or divided: use K")


def _vector(dims: dict) -> tuple[int, ...]:
    unknown = set(dims) - set(BASE)
    if unknown:
        raise UnitError(f"unknown dimension {sorted(unknown)}")
    return tuple(int(dims.get(b, 0)) for b in BASE)


UNITS: dict[str, Unit] = {sym: Unit(float(spec.get("factor", 1.0)), _vector(spec["dims"]), float(spec.get("offset", 0.0)))
                          for sym, spec in _DATA["units"].items()}
PREFIXES: dict[str, float] = {k: float(v) for k, v in _DATA["prefixes"].items()}
PREFIXABLE = set(_DATA["prefixable"])
TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(?P<sym>[^\W\d_]+|°[CF]?|%)(?P<exp>\^?-?\d+)?|(?P<op>[./*()^]))")


def _symbol(text: str) -> Unit:
    if text in UNITS:
        return UNITS[text]
    for prefix in sorted(PREFIXES, key=len, reverse=True):          # longest prefix first: "da" before "d"
        rest = text[len(prefix):]
        if text.startswith(prefix) and rest in PREFIXABLE and rest in UNITS:
            u = UNITS[rest]
            return Unit(u.factor * PREFIXES[prefix], u.dims, u.offset)
    raise UnitError(f"unknown unit {text!r}")


class _Parser:
    def __init__(self, text: str):
        self.tokens = []
        pos = 0
        while pos < len(text):
            m = TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise UnitError(f"cannot read the unit {text!r}")
            self.tokens.append(m)
            pos = m.end()
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def expression(self) -> Unit:
        unit = self.factor()
        while (t := self.peek()) is not None and t.group("op") in (".", "*", "/"):
            self.i += 1
            right = self.factor()
            unit = unit / right if t.group("op") == "/" else unit * right
        return unit

    def factor(self) -> Unit:
        t = self.peek()
        if t is None:
            raise UnitError("a unit is missing")
        self.i += 1
        if t.group("op") == "(":
            unit = self.expression()
            close = self.peek()
            if close is None or close.group("op") != ")":
                raise UnitError("a closing bracket is missing")
            self.i += 1
        elif t.group("num") is not None:
            unit = Unit(float(t.group("num")), ZERO)
        elif t.group("sym") is not None:
            unit = _symbol(t.group("sym"))
            if t.group("exp"):
                unit = unit ** int(t.group("exp").lstrip("^"))
        else:
            raise UnitError(f"unexpected {t.group(0).strip()!r}")
        nxt = self.peek()
        if nxt is not None and nxt.group("op") == "^":
            self.i += 1
            power = self.peek()
            if power is None or power.group("num") is None:
                raise UnitError("an exponent is missing after ^")
            self.i += 1
            unit = unit ** int(float(power.group("num")))
        return unit


@lru_cache(maxsize=2048)
def parse_unit(text: str) -> Unit:
    text = (text or "").strip()
    if not text:
        raise UnitError("empty unit")
    parser = _Parser(text.replace("²", "2").replace("³", "3"))
    unit = parser.expression()
    if parser.i != len(parser.tokens):
        raise UnitError(f"cannot read the unit {text!r}")
    return unit


def is_unit(text: str) -> bool:
    try:
        parse_unit(text)
    except UnitError:
        return False
    return True


def same_unit(a: str, b: str) -> bool:
    """Same dimensions AND same scale: values may be compared or added without conversion."""
    if a == b:
        return True
    ua, ub = parse_unit(a), parse_unit(b)
    return ua.dims == ub.dims and math.isclose(ua.factor, ub.factor, rel_tol=1e-9) and ua.offset == ub.offset


def compatible(a: str, b: str) -> bool:
    """Same dimensions: a value of one can be converted to the other."""
    return parse_unit(a).dims == parse_unit(b).dims


def to_si(value: float, unit: str) -> float:
    u = parse_unit(unit)
    return value * u.factor + u.offset


def convert(value: float, source: str, target: str) -> float:
    s, t = parse_unit(source), parse_unit(target)
    if s.dims != t.dims:
        raise UnitError(f"{source} and {target} measure different things")
    return (value * s.factor + s.offset - t.offset) / t.factor


def symbol_of(unit: Unit) -> str:
    """A readable unit string that parses back to the same Unit: "m2", "kg.m-3", or "0.01.m" when the scale is not 1."""
    if unit.dims == ZERO and math.isclose(unit.factor, 1.0, rel_tol=1e-9):
        return "1"
    parts = [f"{b}{e if e != 1 else ''}" for b, e in zip(BASE, unit.dims, strict=True) if e]
    body = ".".join(parts) or "1"
    if body == "count":
        body = "count"
    return body if math.isclose(unit.factor, 1.0, rel_tol=1e-9) else f"{unit.factor:.12g}.{body}"


def combine(a: str, b: str, op: str) -> str:
    """The unit of a product ("mul") or quotient ("div"). A dimensionless factor of scale 1 leaves the other unit as written."""
    ua, ub = parse_unit(a), parse_unit(b)
    one = lambda u: u.dims == ZERO and math.isclose(u.factor, 1.0, rel_tol=1e-9)  # noqa: E731
    if op == "mul":
        if one(ub):
            return a
        if one(ua):
            return b
        return symbol_of(ua * ub)
    if one(ub):
        return a
    result = ua / ub
    return "1" if result.dims == ZERO and math.isclose(result.factor, 1.0, rel_tol=1e-9) else symbol_of(result)
