"""Scale lines ("1/4" = 1'-0"", "M 1:100", "SCALE: NTS") read with the patterns of vocab.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .vocab import Vocab, fold, plain

METRES_PER_POINT_PAPER = 0.0254 / 72.0     # one PDF point of paper, in metres


@dataclass
class Scale:
    text: str
    ratio: float | None        # real length per unit of paper; None for "not to scale"
    system: str                # imperial, metric or none
    nts: bool = False

    @property
    def metres_per_point(self) -> float | None:
        """Real metres for one PDF point of paper, the unit of the view's coordinate frame."""
        return None if self.ratio is None else self.ratio * METRES_PER_POINT_PAPER

    def to_dict(self) -> dict:
        return {"text": self.text, "ratio": self.ratio, "system": self.system, "nts": self.nts,
                "metres_per_point": self.metres_per_point}


def _frac(s: str) -> float:
    s = s.strip().replace("-", " ")
    total = Fraction(0)
    for part in s.split():
        total += Fraction(part) if "/" in part else Fraction(part)
    return float(total)


def parse_scale(text: str, vocab: Vocab, labelled: bool = False) -> Scale | None:
    """The scale a line states, or None. `labelled` says a scale word stands in front (allows "1/100")."""
    t = plain(text)
    for _, rx, system in vocab.scale_patterns:
        m = rx.search(t)
        if not m:
            continue
        gd = m.groupdict()
        try:
            if "n" in gd and gd["n"] is not None:       # drawn length = n paper units per d real units
                n, d = _frac(gd["n"]), float(gd["d"])
                if n <= 0 or d <= 0:
                    continue
                return Scale(m.group(0), (d * 12.0) / n, system)
            d = float(gd["d"].replace(",", "."))
            if d > 0:
                return Scale(m.group(0), d, system)
        except (ValueError, ZeroDivisionError):
            continue
    if vocab.no_scale.search(fold(text)):
        return Scale(t, None, "none", nts=True)
    if labelled or vocab.scale_label.search(fold(text)):
        m = vocab.scale_slash.search(t)
        if m:
            return Scale(m.group(0), float(m.group("d")), "metric")
    return None
