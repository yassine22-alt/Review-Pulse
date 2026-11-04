"""R9 - Openings: doors, windows and plain openings.

A gap is not a door. Evidence is combined:
- door arcs (sweep 75-105 deg) with a leaf line from the hinge,
- DXF door/window blocks by name,
- gaps between collinear wall pieces,
- thin lines parallel to the wall across a gap (glazing).
Confidence: arc + leaf + gap 0.9; arc + gap 0.8; arc only 0.7; gap only 0.5.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from ..core.geometry import angle_diff, arc_sweep, sector_polygon, seg_angle
from ..core.ids import IdFactory
from ..schema import Element, Primitive, Prov, Sheet
from .walls import angle_of, dist_to_axis, wall_axis

DOOR_SWEEP = (75.0, 105.0)
DOOR_RADIUS_M = (0.55, 1.20)
LEAF_TOL = 0.05
GAP_M = (0.50, 3.00)
GLAZED_GAP_MAX_M = 8.0      # wide windows / glazed bays: accepted only when glazing spans the gap
HINGE_TOL_T = 1.5
GAP_RADIUS_TOL = 0.15
WINDOW_COVER = 0.8
DOOR_BLOCK_RE = re.compile(r"(?i)^(door|porte|dr|d)[-_ ]?\d*")
WINDOW_BLOCK_RE = re.compile(r"(?i)^(window|fen|win|w)[-_ ]?\d*")


@dataclass
class DoorArc:
    prim: Primitive
    hinge: np.ndarray
    radius: float
    a0: float
    a1: float
    closed_end: np.ndarray | None = None
    open_end: np.ndarray | None = None
    leaf: Primitive | None = None
    wall: Element | None = None
    used: bool = False


@dataclass
class Gap:
    wall_a: Element
    wall_b: Element
    p: np.ndarray          # jamb on wall_a side (centreline)
    q: np.ndarray          # jamb on wall_b side
    t: float

    @property
    def width(self) -> float:
        return float(np.linalg.norm(self.q - self.p))

    @property
    def mid(self) -> np.ndarray:
        return (self.p + self.q) / 2

    @property
    def u(self) -> np.ndarray:
        return (self.q - self.p) / (self.width or 1.0)


def _arc_end(c, r, a):
    return np.array([c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a))])


def _door_arcs(sheet: Sheet, mpu: float, walls: list[Element], scale_known: bool) -> list[DoorArc]:
    if scale_known:
        rmin, rmax = DOOR_RADIUS_M[0] / mpu, DOOR_RADIUS_M[1] / mpu
    else:
        ts = [w.thickness for w in walls if w.thickness] or [0.2 / mpu]
        t = float(np.median(ts))
        rmin, rmax = 3 * t, 8 * t
    lines = [p for p in sheet.primitives if p.kind == "line" and not p.hidden and not (p.block or "").startswith("dim:")]
    tree = STRtree([LineString(p.pts) for p in lines]) if lines else None
    arcs = []
    for p in sheet.primitives:
        if p.kind != "arc" or p.hidden or (p.block or "").startswith("dim:"):
            continue
        sw = arc_sweep(p.a0, p.a1)
        if not (DOOR_SWEEP[0] <= sw <= DOOR_SWEEP[1]) or not (rmin <= p.radius <= rmax):
            continue
        c = np.array(p.center)
        e0, e1 = _arc_end(c, p.radius, p.a0), _arc_end(c, p.radius, p.a1)
        da = DoorArc(p, c, p.radius, p.a0, p.a1)
        tol = LEAF_TOL * p.radius
        if tree is not None:
            for i in tree.query(Point(c).buffer(tol)):
                ln = lines[i]
                a, b = np.array(ln.pts[0]), np.array(ln.pts[1])
                for h, o in ((a, b), (b, a)):
                    if np.linalg.norm(h - c) > tol or abs(np.linalg.norm(o - h) - p.radius) > tol:
                        continue
                    if np.linalg.norm(o - e0) <= tol:
                        da.leaf, da.open_end, da.closed_end = ln, e0, e1
                    elif np.linalg.norm(o - e1) <= tol:
                        da.leaf, da.open_end, da.closed_end = ln, e1, e0
                if da.leaf:
                    break
        # the wall that carries the hinge and the closed end
        best = None
        for w in walls:
            t = w.thickness or 0
            dh = dist_to_axis(c, w)
            ends = [da.closed_end] if da.closed_end is not None else [e0, e1]
            for e in ends:
                de = dist_to_axis(e, w)
                if dh <= HINGE_TOL_T * t and de <= HINGE_TOL_T * t:
                    # must be near the wall along its axis as well (within 3 m)
                    a_, u_, L_ = wall_axis(w)
                    s = float(np.dot(c - a_, u_))
                    if -3.0 / mpu <= s <= L_ + 3.0 / mpu:
                        score = dh + de
                        if best is None or score < best[0]:
                            best = (score, w, e)
        if best is None:
            continue
        _, da.wall, ce = best
        if da.closed_end is None:
            da.closed_end = ce
            da.open_end = e1 if ce is e0 else e0
        arcs.append(da)
    return arcs


def _jamb_tol(g: Gap) -> float:
    """Hinge and closed end sit on a wall face at a jamb: half a thickness off the axis,
    plus drawing slack."""
    return max(g.t, 0.15 * g.width)


def _span_cost(da: DoorArc, g: Gap):
    """Distance cost of the door symbol spanning this gap (None if it does not)."""
    if da.closed_end is None:
        return None
    tol = _jamb_tol(g)
    best = None
    for j1, j2 in ((g.p, g.q), (g.q, g.p)):
        dh, dc = np.linalg.norm(da.hinge - j1), np.linalg.norm(da.closed_end - j2)
        if dh <= tol and dc <= tol and (best is None or dh + dc < best):
            best = float(dh + dc)
    return best


def _hinge_at_jamb(da: DoorArc, g: Gap) -> bool:
    return min(np.linalg.norm(da.hinge - g.p), np.linalg.norm(da.hinge - g.q)) <= _jamb_tol(g)


def _double_leaves(leaves: list[DoorArc], g: Gap):
    """Two leaves hinged at opposite jambs whose radii add up to the gap width."""
    for i, d1 in enumerate(leaves):
        for d2 in leaves[i + 1:]:
            h1 = np.linalg.norm(d1.hinge - g.p) < np.linalg.norm(d1.hinge - g.q)
            h2 = np.linalg.norm(d2.hinge - g.p) < np.linalg.norm(d2.hinge - g.q)
            if h1 != h2 and abs(d1.radius + d2.radius - g.width) <= GAP_RADIUS_TOL * g.width:
                return d1, d2
    return None


def _gaps(walls: list[Element], mpu: float, barrier_tree, barrier_geoms) -> list[Gap]:
    gmin, gmax = GAP_M[0] / mpu, GLAZED_GAP_MAX_M / mpu
    out = []
    axis_lines = [LineString(w.geom) for w in walls]
    axis_tree = STRtree(axis_lines) if axis_lines else None
    index_of = {id(w): k for k, w in enumerate(walls)}
    for i, w in enumerate(walls):
        a, u, L = wall_axis(w)
        n = np.array([-u[1], u[0]])
        conn = w.attrs.get("connected", [False, False])
        for k_end, end_w in enumerate((a, a + u * L)):
            # a jamb is a free wall end; an end snapped into a junction never borders a gap
            if conn[k_end]:
                continue
            outward = u if k_end == 1 else -u
            best = None
            for j in axis_tree.query(Point(tuple(end_w)).buffer(gmax + w.thickness)):
                o = walls[j]
                if j == i or angle_diff(angle_of(w), angle_of(o)) > 1.0:
                    continue
                t = max(w.thickness, o.thickness)
                if abs(w.thickness - o.thickness) > 0.25 * t:
                    continue
                oa, ou, oL = wall_axis(o)
                if abs(float(np.dot(oa - a, n))) > t / 4:
                    continue
                oconn = o.attrs.get("connected", [False, False])
                for k_o, end_o in enumerate((oa, oa + ou * oL)):
                    if oconn[k_o]:
                        continue
                    d = float(np.dot(end_o - end_w, outward))
                    if gmin <= d <= gmax and (best is None or d < best[0]):
                        best = (d, o, end_o)
            if best is None or i > index_of[id(best[1])]:
                continue          # each gap once
            d, o, end_o = best
            t = (w.thickness + o.thickness) / 2
            # the gap must be empty of other walls
            mid_line = LineString([tuple(end_w + outward * t * 0.6), tuple(end_o - outward * t * 0.6)])
            blocked = False
            for k in barrier_tree.query(mid_line):
                if barrier_geoms[k][1] not in (w.id, o.id) and barrier_geoms[k][0].intersects(mid_line):
                    blocked = True
                    break
            if not blocked:
                out.append(Gap(w, o, end_w.copy(), end_o.copy(), t))
    return out


def _glazing_cover(gap: Gap, sheet: Sheet, mpu: float, line_tree, lines) -> list[str]:
    """Ids of the thin lines parallel to the wall that span >= 80% of the gap (the glazing)."""
    n = np.array([-gap.u[1], gap.u[0]])
    found: list[str] = []
    probe = Polygon([tuple(gap.p + n * gap.t), tuple(gap.q + n * gap.t), tuple(gap.q - n * gap.t),
                     tuple(gap.p - n * gap.t)])
    ang = seg_angle(tuple(gap.p), tuple(gap.q))
    for k in line_tree.query(probe):
        ln = lines[k]
        a, b = np.array(ln.pts[0]), np.array(ln.pts[-1])
        if angle_diff(seg_angle(tuple(a), tuple(b)), ang) > 2:
            continue
        if abs(float(np.dot(a - gap.p, n))) > gap.t * 0.6:
            continue
        s0, s1 = sorted([float(np.dot(a - gap.p, gap.u)), float(np.dot(b - gap.p, gap.u))])
        cover = max(0.0, min(s1, gap.width) - max(s0, 0.0))
        if cover >= WINDOW_COVER * gap.width:
            found.append(ln.id)
    return found


def _block_openings(sheet: Sheet, mpu: float, ids: IdFactory, walls: list[Element],
                    found: list[Element]) -> list[Element]:
    """DXF INSERTs named like doors/windows. A block whose geometry already produced an
    opening only adds its name as evidence; otherwise its extent is projected onto the
    nearest wall to form a footprint (a block far from any wall is ignored)."""
    groups: dict[tuple, list[Primitive]] = {}
    for p in sheet.primitives:
        if not p.block or p.block.startswith("dim:"):
            continue
        handle = p.prov.evidence.get("insert_handle", p.block)
        groups.setdefault((p.block, handle), []).append(p)
    used = {m for e in found for m in e.member_ids}
    out = []
    for (name, _h), prims in groups.items():
        cls = "door" if DOOR_BLOCK_RE.match(name) else "window" if WINDOW_BLOCK_RE.match(name) else None
        if not cls:
            continue
        member_ids = {p.id for p in prims}
        hit = next((e for e in found if member_ids & set(e.member_ids)), None)
        if hit is not None:
            hit.attrs["block"] = name
            hit.prov.confidence = min(1.0, hit.prov.confidence + 0.05)
            continue
        if member_ids & used:
            continue
        pts = np.array([q for p in prims for q in p.pts] + [p.center for p in prims if p.center], float)
        if len(pts) < 2 or not walls:
            continue
        c = pts.mean(axis=0)
        w = min(walls, key=lambda w_: dist_to_axis(c, w_) if _along(c, w_) else 1e18)
        if not _along(c, w) or dist_to_axis(c, w) > 2 * (w.thickness or 0) + 1.2 / mpu:
            continue
        a, u, _L = wall_axis(w)
        s = (pts - a) @ u
        s0, s1 = float(s.min()), float(s.max())
        n = np.array([-u[1], u[0]])
        t = w.thickness
        p0, p1 = a + u * s0, a + u * s1
        foot = [tuple(np.round(p0 - n * t / 2, 4)), tuple(np.round(p1 - n * t / 2, 4)),
                tuple(np.round(p1 + n * t / 2, 4)), tuple(np.round(p0 + n * t / 2, 4))]
        out.append(Element(id=ids(cls, foot), cls=cls, geom=foot, member_ids=sorted(member_ids),
                           attrs={"width_m": round((s1 - s0) * mpu, 4), "block": name, "wall_id": w.id,
                                  "mid": tuple(np.round((p0 + p1) / 2, 4)), "normal": tuple(np.round(n, 6)),
                                  "thickness": t},
                           prov=Prov(source="vector", stage="openings_blocks_v1", confidence=0.75)))
    return out


def _along(p, w: Element, slack: float = 0.0) -> bool:
    a, u, L = wall_axis(w)
    s = float(np.dot(np.asarray(p) - a, u))
    return -slack - (w.thickness or 0) * 4 <= s <= L + slack + (w.thickness or 0) * 4


def detect_openings(sheet: Sheet, walls: list[Element], columns: list[Element], mpu: float,
                    scale_known: bool = True) -> list[Element]:
    ids = IdFactory(sheet.id)
    walls = [w for w in walls if w.cls == "wall"]
    conf_mult = 1.0 if scale_known else 0.7
    barrier_geoms = [(LineString(w.geom).buffer(w.thickness / 2, cap_style="flat"), w.id) for w in walls]
    barrier_geoms += [(Polygon(c.geom), c.id) for c in columns]
    barrier_tree = STRtree([g for g, _ in barrier_geoms]) if barrier_geoms else None
    arcs = _door_arcs(sheet, mpu, walls, scale_known)
    gaps = _gaps(walls, mpu, barrier_tree, barrier_geoms) if barrier_tree is not None else []
    thin = [p for p in sheet.primitives if p.kind == "line" and not p.hidden
            and not (p.block or "").startswith("dim:")]
    line_tree = STRtree([LineString(p.pts) for p in thin]) if thin else None

    # a door symbol spans its gap: hinge at one jamb AND the closed end of the arc at the other.
    # Assign best-first over all (arc, gap) pairs so a neighbouring window never steals a door arc.
    cand = []
    for gi, g in enumerate(gaps):
        for ai, da in enumerate(arcs):
            c = _span_cost(da, g)
            if c is not None and abs(da.radius - g.width) <= GAP_RADIUS_TOL * g.width:
                cand.append((c, gi, ai))
    door_of: dict[int, DoorArc] = {}
    for _c, gi, ai in sorted(cand):
        if gi in door_of or arcs[ai].used:
            continue
        door_of[gi] = arcs[ai]
        arcs[ai].used = True

    out: list[Element] = []
    for gi, g in enumerate(gaps):
        n = np.array([-g.u[1], g.u[0]])
        foot = [tuple(np.round(g.p - n * g.t / 2, 4)), tuple(np.round(g.q - n * g.t / 2, 4)),
                tuple(np.round(g.q + n * g.t / 2, 4)), tuple(np.round(g.p + n * g.t / 2, 4))]
        attrs = {"width_m": round(g.width * mpu, 4), "wall_id": g.wall_a.id, "wall_ids": [g.wall_a.id, g.wall_b.id],
                 "mid": tuple(np.round(g.mid, 4)), "normal": tuple(np.round(n, 6)), "thickness": g.t,
                 "jambs": [tuple(np.round(g.p, 4)), tuple(np.round(g.q, 4))]}
        door = door_of.get(gi)
        leaves = [da for da in arcs if not da.used and _hinge_at_jamb(da, g)]
        if door is None:
            pair = _double_leaves(leaves, g)
            if pair:
                d1, d2 = pair
                d1.used = d2.used = True
                s1 = sector_polygon(tuple(d1.hinge), d1.radius, d1.a0, d1.a1)
                s2 = sector_polygon(tuple(d2.hinge), d2.radius, d2.a0, d2.a1)
                attrs.update(hinge=tuple(np.round(d1.hinge, 4)),
                             hinges=[tuple(np.round(d1.hinge, 4)), tuple(np.round(d2.hinge, 4))],
                             double=True, width_source="arc_radii",
                             swing_polygon=[tuple(np.round(p, 4)) for p in s1.union(s2).convex_hull.exterior.coords[:-1]],
                             leaf_swings=[[tuple(np.round(p, 4)) for p in s.exterior.coords[:-1]] for s in (s1, s2)])
                attrs["width_m"] = round((d1.radius + d2.radius) * mpu, 4)
                members = [d1.prim.id, d2.prim.id] + [d.leaf.id for d in (d1, d2) if d.leaf]
                conf = 0.9 if (d1.leaf and d2.leaf) else 0.8
                out.append(Element(id=ids("door", foot), cls="door", geom=foot, member_ids=members, attrs=attrs,
                                   prov=Prov(source="vector", stage="openings_v1", confidence=conf * conf_mult,
                                             evidence={"arcs": [d1.prim.id, d2.prim.id]})))
                continue
        if door:
            sector = sector_polygon(tuple(door.hinge), door.radius, door.a0, door.a1)
            attrs.update(hinge=tuple(np.round(door.hinge, 4)), radius=door.radius,
                         swing_polygon=[tuple(np.round(p, 4)) for p in sector.exterior.coords[:-1]],
                         swing_side=1 if float(np.dot(door.open_end - g.mid, n)) > 0 else -1,
                         width_source="arc_radius")
            attrs["width_m"] = round(door.radius * mpu, 4)
            conf = 0.9 if door.leaf else 0.8
            members = [door.prim.id] + ([door.leaf.id] if door.leaf else [])
            out.append(Element(id=ids("door", foot), cls="door", geom=foot, member_ids=members, attrs=attrs,
                               prov=Prov(source="vector", stage="openings_v1", confidence=conf * conf_mult,
                                         evidence={"arc": door.prim.id, "leaf": door.leaf.id if door.leaf else None})))
            continue
        glaz = _glazing_cover(g, sheet, mpu, line_tree, thin) if line_tree is not None else []
        n_glaz = len(glaz)
        if n_glaz >= 2:
            cls, conf = "window", 0.85
        elif g.width * mpu > GAP_M[1]:
            continue        # a bare gap this wide is two walls, not an opening
        else:
            cls, conf = "opening", 0.5
        attrs["glazing_lines"] = n_glaz
        out.append(Element(id=ids(cls, foot), cls=cls, geom=foot, attrs=attrs,
                           member_ids=glaz if cls == "window" else [],
                           prov=Prov(source="vector", stage="openings_v1", confidence=conf * conf_mult,
                                     evidence={"gap": True, "glazing_lines": n_glaz})))

    # arcs that matched no gap: a door drawn across a continuous wall (or a missing gap)
    for da in arcs:
        if da.used or da.wall is None:
            continue
        w = da.wall
        a, u, _ = wall_axis(w)
        n = np.array([-u[1], u[0]])
        hp = a + u * float(np.dot(da.hinge - a, u))
        cp = a + u * float(np.dot(da.closed_end - a, u))
        t = w.thickness
        foot = [tuple(np.round(hp - n * t / 2, 4)), tuple(np.round(cp - n * t / 2, 4)),
                tuple(np.round(cp + n * t / 2, 4)), tuple(np.round(hp + n * t / 2, 4))]
        sector = sector_polygon(tuple(da.hinge), da.radius, da.a0, da.a1)
        nn = (cp - hp) / (np.linalg.norm(cp - hp) or 1)
        nrm = np.array([-nn[1], nn[0]])
        out.append(Element(id=ids("door", foot), cls="door", geom=foot,
                           member_ids=[da.prim.id] + ([da.leaf.id] if da.leaf else []),
                           attrs={"width_m": round(da.radius * mpu, 4), "wall_id": w.id, "mid": tuple(np.round((hp + cp) / 2, 4)),
                                  "normal": tuple(np.round(nrm, 6)), "thickness": t, "hinge": tuple(np.round(da.hinge, 4)),
                                  "radius": da.radius, "width_source": "arc_radius",
                                  "swing_polygon": [tuple(np.round(p, 4)) for p in sector.exterior.coords[:-1]],
                                  "no_gap": True},
                           prov=Prov(source="vector", stage="openings_v1", confidence=0.7 * conf_mult,
                                     evidence={"arc": da.prim.id})))
    out += _block_openings(sheet, mpu, ids, walls, out)
    return out


__all__ = ["detect_openings"]


CARRY_REACH_M = 0.10        # an opening's centre may sit this far off a wall's half-thickness


def carry_openings(prev: list[Element], new: list[Element], walls: list[Element], mpu: float) -> list[Element]:
    """Openings of an earlier pass that the new pass missed, re-hosted on the new walls.

    The second (learned) pass rebuilds the walls, and an opening is found from its wall's gap; a door
    whose symbol was matched before keeps that evidence when the new walls still run through it."""
    taken = {m for e in new for m in e.member_ids}
    centres = [np.mean(np.array(e.geom, float), axis=0) for e in new if e.geom]
    hosts = [w for w in walls if w.cls == "wall"]
    out = []
    for e in prev:
        if e.cls not in ("door", "window", "opening") or not e.geom or taken & set(e.member_ids):
            continue
        c = np.mean(np.array(e.geom, float), axis=0)
        width = (e.attrs.get("width_m") or 0.9) / mpu
        if any(np.linalg.norm(c - q) < 0.5 * width for q in centres):
            continue
        best, best_d = None, None
        for w in hosts:
            a, u, L = wall_axis(w)
            s = float(np.dot(c - a, u))
            d = dist_to_axis(c, w)
            if -0.5 * width <= s <= L + 0.5 * width and d <= (w.thickness or 0) / 2 + CARRY_REACH_M / mpu:
                if best_d is None or d < best_d:
                    best, best_d = w, d
        if best is None:
            continue
        attrs = dict(e.attrs, wall_id=best.id, carried=True)
        if "wall_ids" in attrs:
            attrs["wall_ids"] = [best.id]
        out.append(e.model_copy(update={"attrs": attrs}))
    return out
