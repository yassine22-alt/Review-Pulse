"""Doors and windows straight from the learned primitive classifier.

Rule-based openings are found from wall gaps, so a door is only found where the walls around it were.
The classifier labels door and window primitives directly (leaf, swing arc, frame, glazing lines); a
connected group of primitives with the same label is one opening. It is hosted on the nearest wall
(normal and thickness from that wall, as rule and raster openings carry them), or, with no wall near,
described by its own minimum rotated rectangle.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

from ...core.geometry import arc_points, side_by_side
from ...core.ids import IdFactory
from ...schema import Element, Primitive, Prov, Sheet
from ..walls import dist_to_axis, wall_axis

JOIN_M = 0.05                  # primitives this close belong to one symbol
WINDOW_DEPTH_M = 0.4           # ... and window panes side by side within a wall thickness (they need not
                               # touch: measured on ArchCAD, panes 6 cm apart joined only by jamb lines the
                               # classifier calls wall became single-line groups, and all were dropped)
WIDTH_M = {"door": (0.40, 3.50), "window": (0.30, 8.00)}
HOST_REACH_M = 0.30            # an opening's centre may sit this far beyond a wall face


def _geom(p: Primitive):
    if p.kind in ("line", "polyline") and len(p.pts) >= 2:
        return LineString(p.pts)
    if p.kind == "polygon" and len(p.pts) >= 3:
        return LineString(p.pts + p.pts[:1])
    if p.kind in ("arc", "circle") and p.center and p.radius:
        a0, a1 = (p.a0, p.a1) if p.kind == "arc" else (0.0, 360.0)
        pts = arc_points(p.center, p.radius, a0, a1)
        return LineString(pts) if len(pts) >= 2 else None
    return None


def _straight(p: Primitive):
    return (tuple(p.pts[0]), tuple(p.pts[-1])) if p.kind in ("line", "polyline") and len(p.pts) == 2 else None


def _groups(prims: list[Primitive], join: float, depth: float | None = None) -> list[list[Primitive]]:
    geoms = [_geom(p) for p in prims]
    keep = [i for i, g in enumerate(geoms) if g is not None and not g.is_empty]
    if not keep:
        return []
    gs = [geoms[i] for i in keep]
    tree = STRtree(gs)
    parent = list(range(len(gs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    ii, jj = tree.query(gs, predicate="dwithin", distance=join)
    pairs = list(zip(ii.tolist(), jj.tolist()))
    if depth:
        ii, jj = tree.query(gs, predicate="dwithin", distance=depth)
        for i, j in zip(ii.tolist(), jj.tolist()):
            a, b = _straight(prims[keep[i]]), _straight(prims[keep[j]])
            if i != j and a and b and side_by_side(a, b):
                pairs.append((i, j))
    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    out: dict[int, list[Primitive]] = {}
    for k, i in enumerate(keep):
        out.setdefault(find(k), []).append(prims[i])
    return list(out.values())


def learned_openings(sheet: Sheet, walls: list[Element], existing: list[Element], mpu: float) -> list[Element]:
    """Openings the classifier sees that no existing opening covers."""
    ids = IdFactory(sheet.id + ":learned")
    taken = {m for e in existing for m in e.member_ids}
    hosts = [w for w in walls if w.cls == "wall"]
    out = []
    for cls in ("door", "window"):
        prims = [p for p in sheet.primitives
                 if p.prov.evidence.get("learned_class") == cls and (not p.hidden or p.prov.stage == "arc_fit")]
        lo, hi = (v / mpu for v in WIDTH_M[cls])
        for grp in _groups(prims, JOIN_M / mpu, WINDOW_DEPTH_M / mpu if cls == "window" else None):
            mem = {p.id for p in grp}
            if mem & taken:
                continue
            shape = unary_union([_geom(p) for p in grp])
            mrr = shape.minimum_rotated_rectangle
            if mrr.geom_type != "Polygon":
                continue
            cs = list(mrr.exterior.coords)[:4]
            e0, e1 = np.subtract(cs[1], cs[0]), np.subtract(cs[2], cs[1])
            long_ = e0 if np.linalg.norm(e0) >= np.linalg.norm(e1) else e1
            c = np.array([mrr.centroid.x, mrr.centroid.y])
            host, best = None, None
            for w in hosts:
                a, u, L = wall_axis(w)
                s = float(np.dot(c - a, u))
                d = dist_to_axis(c, w)
                if 0 <= s <= L and d <= (w.thickness or 0) / 2 + HOST_REACH_M / mpu and (best is None or d < best):
                    host, best = w, d
            if host is not None:
                a, u, _L = wall_axis(host)
                proj = np.array([np.dot(np.array(q) - a, u) for q in _coords(shape)])
                s0, s1 = float(proj.min()), float(proj.max())
                width = s1 - s0
                mid = a + u * (s0 + s1) / 2
                nrm = np.array([-u[1], u[0]])
                t = float(host.thickness or 0.0)
                g = [tuple(np.round(mid + u * k * width / 2 + nrm * j * t / 2, 4)) for k, j in
                     ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            else:
                width = float(np.linalg.norm(long_))
                short = e1 if long_ is e0 else e0
                t = float(np.linalg.norm(short))
                nrm = short / (t or 1.0)
                mid = c
                g = [tuple(round(v, 4) for v in q) for q in cs]
            if not lo <= width <= hi:
                continue
            probs = [p.prov.evidence.get("p_" + cls, 0.0) for p in grp]
            conf = float(np.mean(probs)) * (1.0 if host is not None else 0.7)
            attrs = {"mid": (round(float(mid[0]), 4), round(float(mid[1]), 4)),
                     "normal": (float(nrm[0]), float(nrm[1])), "thickness": t,
                     "width_m": round(width * mpu, 4), "source": "learned",
                     "wall_id": host.id if host is not None else None, "needs_confirmation": True}
            out.append(Element(id=ids(cls, g), cls=cls, geom=g, member_ids=sorted(mem), attrs=attrs,
                               prov=Prov(source="vector", stage="learned_openings_v1", confidence=round(conf, 3))))
            taken |= mem
    return out


def _coords(shape) -> list:
    if isinstance(shape, LineString):
        return list(shape.coords)
    if isinstance(shape, MultiLineString):
        return [q for g in shape.geoms for q in g.coords]
    if isinstance(shape, Point):
        return [shape.coords[0]]
    return [q for g in getattr(shape, "geoms", []) for q in _coords(g)]
