"""Synthetic stairs with exact truth, in many drawing styles, for measuring the stair finder's accuracy.

FloorPlanCAD says WHERE the stairs are but not how deep the treads are. Here the tread depth, width and step count are
chosen, so the error of every reported number can be measured, and so can the false-alarm rate on drawings with no
stair. Every case draws a random mixture of styles; nothing is tied to one CAD convention.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ..schema import Primitive, Prov, Sheet


@dataclass
class Case:
    sheet: Sheet
    mpu: float
    has_stair: bool
    pitch: float = 0.0
    width: float = 0.0
    treads: int = 0
    styles: list[str] = field(default_factory=list)
    stair_from: int = 0                     # primitives from this index on belong to the stair


class _Draw:
    def __init__(self, mpu: float):
        self.mpu, self.prims = mpu, []

    def line(self, a, b):
        pts = [(a[0] / self.mpu, a[1] / self.mpu), (b[0] / self.mpu, b[1] / self.mpu)]
        self.prims.append(Primitive(id=f"p{len(self.prims)}", kind="line", pts=pts,
                                    prov=Prov(source="vector", stage="stairgen")))


def _flight(d: _Draw, rng: random.Random, origin, theta, pitch, width, treads, styles: list[str], jitter: float):
    u = (math.cos(theta), math.sin(theta))            # along the tread
    n = (-math.sin(theta), math.cos(theta))           # along the run

    def at(s, t):
        return (origin[0] + s * u[0] + t * n[0] + rng.gauss(0, jitter), origin[1] + s * u[1] + t * n[1] + rng.gauss(0, jitter))

    for i in range(treads):
        t = i * pitch
        pieces = [(0.0, width)]
        if "broken" in styles:
            cut = rng.uniform(0.3, 0.7) * width
            pieces = [(0.0, cut - 0.01), (cut + 0.01, width)]
        for s0, s1 in pieces:
            d.line(at(s0, t), at(s1, t))
            if "nosing" in styles:
                d.line(at(s0, t + 0.035), at(s1, t + 0.035))
    if "stringers" in styles:
        end = (treads - 1) * pitch
        d.line(at(0, 0), at(0, end))
        d.line(at(width, 0), at(width, end))
    if "arrow" in styles:
        mid = width / 2
        d.line(at(mid, 0), at(mid, (treads - 1) * pitch))


def _clutter(d: _Draw, rng: random.Random, span: float, kinds: list[str]):
    if "walls" in kinds:
        for _ in range(rng.randint(6, 30)):
            x, y = rng.uniform(0, span), rng.uniform(0, span)
            th = rng.choice([0, math.pi / 2, rng.uniform(0, math.pi)])
            ln = rng.uniform(1.0, 8.0)
            d.line((x, y), (x + ln * math.cos(th), y + ln * math.sin(th)))
            d.line((x + 0.2 * math.sin(th), y - 0.2 * math.cos(th)),
                   (x + ln * math.cos(th) + 0.2 * math.sin(th), y + ln * math.sin(th) - 0.2 * math.cos(th)))
    if "hatch" in kinds:
        x, y, th = rng.uniform(0, span), rng.uniform(0, span), rng.uniform(0, math.pi)
        for i in range(rng.randint(8, 40)):
            a = (x + i * 0.1 * -math.sin(th), y + i * 0.1 * math.cos(th))
            d.line(a, (a[0] + 1.2 * math.cos(th), a[1] + 1.2 * math.sin(th)))
    if "grid" in kinds:                                # tiles, a ceiling grid, a bench slat pattern: periodic, not stairs
        x, y, th = rng.uniform(0, span), rng.uniform(0, span), rng.uniform(0, math.pi)
        pitch = rng.uniform(0.6, 1.2)
        for i in range(rng.randint(5, 20)):
            a = (x + i * pitch * -math.sin(th), y + i * pitch * math.cos(th))
            d.line(a, (a[0] + 4.0 * math.cos(th), a[1] + 4.0 * math.sin(th)))
    if "random_parallel" in kinds:                     # parallel strokes at uneven spacing
        x, y, th = rng.uniform(0, span), rng.uniform(0, span), rng.uniform(0, math.pi)
        t = 0.0
        for _ in range(rng.randint(5, 15)):
            t += rng.uniform(0.1, 0.9)
            a = (x + t * -math.sin(th), y + t * math.cos(th))
            d.line(a, (a[0] + 1.0 * math.cos(th), a[1] + 1.0 * math.sin(th)))


def make_case(seed: int, with_stair: bool = True) -> Case:
    rng = random.Random(seed)
    mpu = rng.choice([0.1, 0.05, 0.01, 0.001, 0.0254])
    d = _Draw(mpu)
    span = 25.0
    clutter = [k for k in ("walls", "hatch", "grid", "random_parallel") if rng.random() < 0.6]
    _clutter(d, rng, span, clutter)
    case = Case(sheet=None, mpu=mpu, has_stair=with_stair, styles=list(clutter))   # type: ignore[arg-type]
    case.stair_from = len(d.prims)
    if with_stair:
        styles = [s for s in ("nosing", "broken", "stringers", "arrow") if rng.random() < 0.35]
        pitch, width, treads = rng.uniform(0.2, 0.34), rng.uniform(0.8, 2.4), rng.randint(5, 20)
        theta = rng.choice([0.0, math.pi / 2, rng.uniform(0, math.pi)])
        origin = (rng.uniform(2, span - 8), rng.uniform(2, span - 8))
        _flight(d, rng, origin, theta, pitch, width, treads, styles, jitter=rng.choice([0.0, 0.002, 0.005]))
        if rng.random() < 0.25:                        # a second flight beside the first, as in a U-shaped stair
            n = (-math.sin(theta), math.cos(theta))
            u = (math.cos(theta), math.sin(theta))
            o2 = (origin[0] + (width + 0.3) * u[0] + (treads - 1) * pitch * n[0] * 0,
                  origin[1] + (width + 0.3) * u[1])
            _flight(d, rng, o2, theta, pitch, width, treads, styles, jitter=0.0)
            styles.append("second_flight")
        case.pitch, case.width, case.treads, case.styles = pitch, width, treads, styles + clutter
    case.sheet = Sheet(id=f"g{seed}", source_file="synthetic", mode="vector", coord_unit="drawing_unit",
                       width=span / mpu, height=span / mpu, primitives=d.prims)
    return case
