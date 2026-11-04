"""R11 - Dimension linking and chains.

- PDF: every text/line pair found by R7 becomes a ``Dimension``; extension lines
  give the measured feature points p1, p2.
- DXF: DIMENSION entities already carry defpoints and the measurement.
- Chains: dimensions on one feature axis; the overall dimension is the one whose
  ends span the others. Ends are linked to wall faces / openings.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from ..core.geometry import angle_diff, seg_angle, seg_len
from ..core.ids import IdFactory
from ..schema import Dimension, Element, Prov, Sheet
from .scale import THIN_MAX_MM, DimPair

EXT_ANGLE_TOL = 5.0
EXT_OVERSHOOT_MM = 2.5
EXT_PASS_TOL_MM = 0.3
CHAIN_ANGLE_TOL = 0.5
CHAIN_OFFSET_M = 0.05
CHAIN_END_M = 0.10
LINK_M = 0.06


def _ext_lines(end, ang, segs, tree, u: float = 1.0) -> list[tuple[float, tuple, str]]:
    """All extension lines at a dimension-line end: perpendicular, passing through the end, with
    one endpoint near it (the overshoot, usually 1-2.5 mm on paper). Lines that merely pass
    through the end (another dimension's longer extension line) are rejected.
    Returns [(overshoot, far end, id)] sorted by overshoot."""
    out = []
    for i in tree.query(Point(end).buffer(EXT_OVERSHOOT_MM * u)):
        p, a, b = segs[i]
        if abs(angle_diff(seg_angle(a, b), ang) - 90) > EXT_ANGLE_TOL:
            continue
        if LineString([a, b]).distance(Point(end)) > EXT_PASS_TOL_MM * u:
            continue
        near, far = (a, b) if math.dist(a, end) <= math.dist(b, end) else (b, a)
        if math.dist(near, end) > EXT_OVERSHOOT_MM * u:
            continue
        out.append((math.dist(near, end), tuple(far), p.id))
    return sorted(out)


def _ext_line(end, ang, segs, tree, u: float = 1.0):
    """(far end, id) of the closest-fitting extension line, or (end, None)."""
    found = _ext_lines(end, ang, segs, tree, u)
    return (found[0][1], found[0][2]) if found else (tuple(end), None)


def _thin_segments(sheet: Sheet):
    paper = sheet.coord_unit == "paper_mm"
    segs = []
    for p in sheet.primitives:
        if p.hidden or p.kind != "line" or (paper and p.width is not None and p.width > THIN_MAX_MM):
            continue
        segs.append((p, tuple(p.pts[0]), tuple(p.pts[1])))
    return segs, (STRtree([LineString([a, b]) for _, a, b in segs]) if segs else None)


def tag_dimension_graphics(sheet: Sheet, pairs: list[DimPair]) -> int:
    """Mark dimension lines, terminators and extension lines (evidence 'dim_graphic') so that
    wall and opening detection ignore them whatever layer they are on."""
    segs, tree = _thin_segments(sheet)
    ids: set[str] = set()
    for pr in pairs:
        ids.add(pr.line_id)
        ids.update(t for t in pr.term_ids if t)
        if tree is not None:
            ang = seg_angle(pr.p1, pr.p2)
            for end in (pr.p1, pr.p2):
                ids.update(eid for _o, _f, eid in _ext_lines(end, ang, segs, tree, pr.u))
    for p in sheet.primitives:
        if p.id in ids:
            p.prov.evidence["dim_graphic"] = True
    return len(ids)


def dimensions_from_pairs(sheet: Sheet, pairs: list[DimPair], mpu: float) -> list[Dimension]:
    ids = IdFactory(sheet.id)
    segs, tree = _thin_segments(sheet)
    out = []
    seen = set()
    for pr in pairs:
        if pr.text_id in seen:
            continue
        seen.add(pr.text_id)
        ang = seg_angle(pr.p1, pr.p2)
        f1 = _ext_line(pr.p1, ang, segs, tree, pr.u)[0] if tree else pr.p1
        f2 = _ext_line(pr.p2, ang, segs, tree, pr.u)[0] if tree else pr.p2
        out.append(Dimension(id=ids("dim", f1, f2), text_id=pr.text_id, value_m=round(pr.stated_mm / 1000, 6),
                             measured_m=round(seg_len(pr.p1, pr.p2) * mpu, 6), p1=f1, p2=f2,
                             line_ids=[pr.line_id],
                             prov=Prov(source="vector", stage="dimensions_v1",
                                       evidence={"line": [pr.p1, pr.p2]})))
    return out


def build_chains(dims: list[Dimension], mpu: float) -> None:
    """Assign chain_id and mark the overall dimension (prov.evidence['overall'])."""
    off_tol = CHAIN_OFFSET_M / mpu
    end_tol = CHAIN_END_M / mpu
    groups: list[list[tuple[Dimension, float, float, float, float]]] = []
    for d in dims:
        if seg_len(d.p1, d.p2) <= 0:
            continue
        ang = seg_angle(d.p1, d.p2)
        u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
        n = np.array([-u[1], u[0]])
        off = float(np.dot(d.p1, n))
        s1, s2 = sorted([float(np.dot(d.p1, u)), float(np.dot(d.p2, u))])
        for g in groups:
            g_ang, g_off = g[0][1], g[0][2]
            if angle_diff(ang, g_ang) <= CHAIN_ANGLE_TOL and abs(off - g_off) <= off_tol:
                g.append((d, ang, off, s1, s2))
                break
        else:
            groups.append([(d, ang, off, s1, s2)])
    k = 0
    for g in groups:
        if len(g) < 2:
            continue
        overall = [x for x in g if sum(1 for y in g if y is not x and y[3] >= x[3] - end_tol
                                       and y[4] <= x[4] + end_tol) >= 2]
        k += 1
        cid = f"chain:{k}"
        for x in g:
            x[0].chain_id = cid
            x[0].prov.evidence["overall"] = False
        if overall:
            top = max(overall, key=lambda x: x[4] - x[3])
            top[0].prov.evidence["overall"] = True
            # nested overalls (sub-totals) stay out of the parts list
            for x in overall:
                if x is not top:
                    x[0].prov.evidence["subtotal"] = True
                    x[0].chain_id = f"{cid}:sub"


def link_ends(dims: list[Dimension], walls: list[Element], openings: list[Element], mpu: float) -> None:
    geoms, gids = [], []
    for w in walls:
        if w.cls == "wall" and w.thickness:
            geoms.append(LineString(w.geom).buffer(w.thickness / 2, cap_style="square").exterior)
            gids.append(w.id)
    for o in openings:
        if len(o.geom) >= 3:
            geoms.append(Polygon(o.geom).exterior)
            gids.append(o.id)
    if not geoms:
        return
    tree = STRtree(geoms)
    tol = LINK_M / mpu
    for d in dims:
        ids = []
        for p in (d.p1, d.p2):
            best = None
            for i in tree.query(Point(p).buffer(tol)):
                dist = geoms[i].distance(Point(p))
                if dist <= tol and (best is None or dist < best[0]):
                    best = (dist, gids[i])
            if best:
                ids.append(best[1])
        d.measured_ids = sorted(set(ids))


def chain_summary(dims: list[Dimension]) -> dict:
    ch = defaultdict(list)
    for d in dims:
        if d.chain_id:
            ch[d.chain_id].append(d.id)
    return dict(ch)
