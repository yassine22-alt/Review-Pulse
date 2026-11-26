"""What a previous comment asks for, read with patterns (no model): a numeric limit ("minimum 0.80 m", "not more than 15 m"),
a presence demand (a quoted text, or "add a note stating ..."), or nothing checkable. And the tests that answer it: numbers
with units in a region, and a ranked search (BM25 only) of the requested words in the passages of a sheet."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..interpreter.drawing_evidence import _tokens, bm25_ranking

NUM = r"(\d{1,4}(?:[.,]\d{1,3})?)"
UNIT = r"(mm|cm|m|metres?|meters?|in(?:ch(?:es)?)?|ft|feet|foot|m2|m²|sq\.?\s*ft|sf|\"|'|”|″)"
TO_SI = {"mm": 0.001, "cm": 0.01, "m": 1.0, "metre": 1.0, "metres": 1.0, "meter": 1.0, "meters": 1.0, "in": 0.0254, "inch": 0.0254,
         "inches": 0.0254, "\"": 0.0254, "”": 0.0254, "″": 0.0254, "ft": 0.3048, "feet": 0.3048, "foot": 0.3048, "'": 0.3048}
AREA_UNITS = {"m2": 1.0, "m²": 1.0, "sf": 0.092903, "sqft": 0.092903}
MIN_WORDS = r"(?:min(?:imum)?\.?|at\s+least|not\s+(?:be\s+)?less\s+than|no\s+less\s+than|greater\s+than\s+or\s+equal\s+to|>=|≥|minimum\s+of)"
MAX_WORDS = r"(?:max(?:imum)?\.?|at\s+most|not\s+(?:be\s+)?(?:more|greater)\s+than|no\s+more\s+than|not\s+exceed(?:ing)?|exceed|less\s+than\s+or\s+equal\s+to|<=|≤|maximum\s+of)"
QUANTITIES = {"width": ("width", "wide", "clear opening", "clear width"), "height": ("height", "tall", "headroom", "high"),
              "area": ("area", "square"), "distance": ("distance", "travel", "length", "depth")}
TRIGGER = re.compile(r"\b(?:add|provide|show|indicate|state|stating|note|label|include|specify|identify|insert|annotate|clarify)\b"
                     r"\s+(?:a\s+|an\s+|the\s+)?(?:note\s+)?(?:that\s+|reading\s+|saying\s+|as\s+|:\s*)?(.{6,200}?)(?:[.;]|$)", re.I)
QUOTED = re.compile(r"[\"“'‘]([^\"”'’]{3,160})[\"”'’]")
COVER = 0.8


@dataclass
class Demand:
    kind: str                   # min, max, presence, none
    limit_si: float | None = None
    dim: str | None = None      # length, area
    quantity: str = ""          # width, height, area, distance
    phrase: str = ""
    raw: str = ""

    def describe(self) -> str:
        if self.kind in ("min", "max"):
            return f"{'minimum' if self.kind == 'min' else 'maximum'} {self.limit_si:g} {'m2' if self.dim == 'area' else 'm'}" \
                   + (f" ({self.quantity})" if self.quantity else "")
        if self.kind == "presence":
            return f"text present: '{self.phrase}'"
        return "nothing a tool can check"


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _to_si(value: float, unit: str) -> tuple[float, str] | None:
    u = unit.lower().replace(" ", "").replace(".", "")
    if u in AREA_UNITS:
        return value * AREA_UNITS[u], "area"
    if u in TO_SI:
        return value * TO_SI[u], "length"
    return None


def numbers_with_units(text: str) -> list[tuple[float, str, str]]:
    """Every figure with a unit in a text: (value in metres or square metres, dimension, as written)."""
    out = []
    for m in re.finditer(NUM + r"\s*" + UNIT + r"(?![a-z0-9])", text, re.I):
        si = _to_si(_num(m.group(1)), m.group(2))
        if si:
            out.append((si[0], si[1], m.group(0).strip()))
    return out


def _quantity(text: str) -> str:
    low = text.lower()
    for q, words in QUANTITIES.items():
        if any(w in low for w in words):
            return q
    return ""


ASKS = re.compile(r"(?<!\w)(?:add|provide|show|indicate|state|stating|note|label|rename|include|specify|read|reading|insert|"
                  r"annotate|clarify|change|revise|replace|use)(?!\w)[^\"“'‘]{0,40}$", re.I)


def parse_demand(text: str) -> Demand:
    q0 = QUOTED.search(text)
    if q0 and ASKS.search(text[:q0.start()]):          # the quoted words are what must be written, whatever figures they hold
        return Demand("presence", phrase=q0.group(1).strip(), raw=text)
    low = text.replace("≥", ">=").replace("≤", "<=")
    for kind, words in (("min", MIN_WORDS), ("max", MAX_WORDS)):
        pats = (words + r"\s*(?:of\s+|than\s+)?" + NUM + r"\s*" + UNIT + r"(?![a-z0-9])",
                NUM + r"\s*" + UNIT + r"(?![a-z0-9])\s*(?:" + words + r"|or\s+(?:more|greater|wider|larger|higher))" if kind == "min" else
                NUM + r"\s*" + UNIT + r"(?![a-z0-9])\s*(?:" + words + r"|or\s+(?:less|fewer|smaller|lower))")
        for pat in pats:
            m = re.search(pat, low, re.I)
            if m:
                si = _to_si(_num(m.group(1)), m.group(2))
                if si:
                    return Demand(kind, si[0], si[1], _quantity(low), raw=text)
    q = QUOTED.search(text)
    if q:
        return Demand("presence", phrase=q.group(1).strip(), raw=text)
    t = TRIGGER.search(text)
    if t and len(_tokens(t.group(1))) >= 2:
        return Demand("presence", phrase=t.group(1).strip(), raw=text)
    return Demand("none", raw=text)


def satisfies(d: Demand, value_si: float, tol: float = 0.005) -> bool:
    if d.kind == "min":
        return value_si >= d.limit_si * (1 - tol) - 1e-9
    if d.kind == "max":
        return value_si <= d.limit_si * (1 + tol) + 1e-9
    return False


def present(texts: list[str], phrase: str) -> tuple[bool, str, float]:
    """Is the requested text on a page: the best ranked text (BM25) and the share of the requested words it holds."""
    want = set(_tokens(phrase))
    if not want or not texts:
        return False, "", 0.0
    best, best_cov = "", 0.0
    for i in bm25_ranking(phrase, texts)[:5]:
        cov = len(want & set(_tokens(texts[i]))) / len(want)
        if cov > best_cov:
            best, best_cov = texts[i], cov
    return best_cov >= COVER, best, round(best_cov, 2)
