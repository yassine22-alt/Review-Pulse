"""Primitive labels for generated plans (synth/random_plan.py), from the generator's truth geometry.

The generator draws many styles (wall outlines, closed polylines, hatched or filled walls; five door
styles; four layer schemes, one of them everything on layer 0), so layer names cannot label lines.
Instead every primitive is mapped to truth metres and labelled by where it lies:

in this order (the first region that holds the primitive wins):

- inside a window's footprint                      -> window
- inside a door's gap in the wall                  -> door
- on the outline of a wall body (faces, end caps)  -> wall  (hatch strokes inside the body are not
  wall faces: the rules tag them as pattern, and FloorPlanCAD labels faces)
- inside a door's swing disc (leaf, arc)           -> door  (after walls: the disc also covers the
  wall faces beside the opening, which are walls; labelling them "door" taught the classifier to
  reject the short wall pieces between doors, and rooms merged)
- anywhere else (furniture, text boxes, clutter)   -> other
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from ...schema import BuildingModel
from .features import CLASSES

TOL_M = 0.03
INSIDE = 0.9                 # share of a primitive's length that must lie in the region


def _to_truth(model: BuildingModel, truth: dict, fmt: str):
    if fmt == "pdf":
        tr = truth["pdf_transform"]
        return lambda x, y: ((x - tr["ox"]) / tr["k"], (y - tr["oy"]) / tr["k"])
    k = truth.get("dxf_unit_m") or 1.0
    return lambda x, y: (x * k, y * k)


def _geom(p, f):
    if p.kind in ("line", "polyline") and len(p.pts) >= 2:
        return LineString([f(*q) for q in p.pts])
    if p.kind == "polygon" and len(p.pts) >= 3:
        pts = [f(*q) for q in p.pts]
        return LineString(pts + pts[:1])
    if p.kind in ("arc", "circle") and p.center and p.radius:
        from ...core.geometry import arc_points

        a0, a1 = (p.a0, p.a1) if p.kind == "arc" else (0.0, 360.0)
        return LineString([f(*q) for q in arc_points(p.center, p.radius, a0, a1)])
    return None


def labels_from_synth_truth(model: BuildingModel, ids: list[str], truth: dict, fmt: str) -> np.ndarray:
    f = _to_truth(model, truth, fmt)
    bodies = unary_union([LineString(w["centreline"]).buffer(w["thickness"] / 2, cap_style="flat",
                                                             join_style="mitre") for w in truth["walls"]])
    walls = bodies.boundary.buffer(TOL_M)
    win = unary_union([Polygon(o["polygon"]).buffer(TOL_M) for o in truth["openings"] if o["cls"] == "window"])
    doors = [o for o in truth["openings"] if o["cls"] == "door"]
    # the gap itself, shrunk so its jambs (wall end caps on its edges) stay walls
    gap = unary_union([Polygon(o["polygon"]).buffer(-TOL_M / 2) for o in doors])
    swing = unary_union([Point(o["midpoint"]).buffer(o["width_m"] * (1.0 if o.get("double") else 1.15))
                         for o in doors])
    by_id = {p.id: p for p in model.sheet.primitives}
    y = np.zeros(len(ids), dtype=np.int32)
    for k, pid in enumerate(ids):
        g = _geom(by_id[pid], f)
        if g is None or g.length <= 0:
            continue
        for name, region in (("window", win), ("door", gap), ("wall", walls), ("door", swing)):
            if not region.is_empty and g.intersection(region).length >= INSIDE * g.length:
                y[k] = CLASSES.index(name)
                break
    return y
