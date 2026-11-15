"""J6 - Door swing conflicts (Q-1).

Two swings conflict when their intersection exceeds max(0.01 m2, 2% of the
smaller swing); a swing also conflicts when it overlaps another door's opening.
The verdict is WARNING (rule param ``max_verdict``).
"""

from __future__ import annotations

from shapely.geometry import Polygon
from shapely.strtree import STRtree

from ..rules.schema import Rule
from .context import Context
from .policy import Raw

MIN_OVERLAP_M2 = 0.01
MIN_OVERLAP_REL = 0.02


def fn_swing_conflicts(rule: Rule, ctx: Context) -> list[Raw]:
    mpu = ctx.mpu or 1.0
    doors = [e for e in ctx.model.elements if e.cls == "door" and e.attrs.get("swing_polygon")]
    swings = [Polygon(d.attrs["swing_polygon"]).buffer(0) for d in doors]
    foots = [Polygon(d.geom).buffer(0) for d in doors]
    out = []
    if not doors:
        return out
    tree = STRtree(swings)
    seen = set()
    for i, s in enumerate(swings):
        for j in tree.query(s):
            if j <= i or (i, j) in seen:
                continue
            inter = s.intersection(swings[j])
            area = inter.area * mpu * mpu
            if area > max(MIN_OVERLAP_M2, MIN_OVERLAP_REL * min(s.area, swings[j].area) * mpu * mpu):
                seen.add((i, j))
                a, b = doors[i], doors[j]
                ta, tb = a.tag or a.id[-6:], b.tag or b.id[-6:]
                polys = [a.attrs["swing_polygon"], b.attrs["swing_polygon"]]
                if not inter.is_empty and inter.geom_type == "Polygon":
                    polys.append([(round(x, 4), round(y, 4)) for x, y in inter.exterior.coords[:-1]])
                out.append(Raw([a.id, b.id], True, metric=True, deciding_ids=[a.id, b.id],
                               detected=f"overlap {area:.2f} m²", required="no overlap",
                               vars={"subject": {"tag": f"{ta}/{tb}", "__str__": f"{ta}/{tb}"}},
                               evidence={"polygons": polys, "overlap_m2": round(area, 4)}))
        for j, f in enumerate(foots):
            if j == i:
                continue
            inter = s.intersection(f)
            if inter.area * mpu * mpu > MIN_OVERLAP_M2:
                a, b = doors[i], doors[j]
                out.append(Raw([a.id, b.id], True, metric=True, deciding_ids=[a.id, b.id],
                               detected=f"swing of {a.tag or a.id[-6:]} enters opening of {b.tag or b.id[-6:]}",
                               required="no overlap",
                               vars={"subject": {"tag": a.tag or a.id[-6:], "__str__": a.tag or ''}},
                               evidence={"polygons": [a.attrs["swing_polygon"], b.geom]}))
    if not out:
        out.append(Raw([], False, detected=f"{len(doors)} swings, no overlap", required="no overlap"))
    return out
