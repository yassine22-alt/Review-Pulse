"""Primitive normalisation shared by every source (PDF, DXF, later raster vectorisation).

Exporters draw the same thing in many ways. Before perception we reduce the
variety without using layer names:
- chains of short connected segments (or polylines) lying on one circle -> ARC;
- groups of >= 3 parallel, equal, end-aligned short-spaced lines -> glazing
  symbol (tagged so wall pairing ignores them and window detection uses them).
Original primitives are kept (hidden from perception) so nothing is lost.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from ..core.geometry import angle_diff, seg_angle, seg_len
from ..core.ids import IdFactory
from ..schema import Primitive, Prov, Sheet

ARC_MIN_SEGMENTS = 4
ARC_FIT_REL = 0.01          # vertices on the circle within 1% of the radius
ARC_MIN_SWEEP = 30.0
ENDPOINT_TOL_REL = 1e-4     # of the sheet diagonal

GLAZ_MIN_LINES = 3
GLAZ_ANGLE = 1.0
GLAZ_LEN_REL = 0.03
GLAZ_MAX_SPAN_M = 0.60


def _fit_circle(pts: np.ndarray):
    """Algebraic least-squares circle fit (Kasa)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(pts))]
    b = x * x + y * y
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy, c = sol
    r2 = c + cx * cx + cy * cy
    if r2 <= 0:
        return None
    return (cx, cy), math.sqrt(r2)


def _arc_from_points(pts: list) -> tuple | None:
    if len(pts) < ARC_MIN_SEGMENTS + 1:
        return None
    P = np.array(pts, dtype=float)
    fit = _fit_circle(P)
    if fit is None:
        return None
    (cx, cy), r = fit
    d = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
    if np.max(np.abs(d - r)) > ARC_FIT_REL * r:
        return None
    angs = np.degrees(np.arctan2(P[:, 1] - cy, P[:, 0] - cx))
    steps = np.diff(np.unwrap(np.radians(angs)))
    if not (np.all(steps > 0) or np.all(steps < 0)):
        return None
    sweep = abs(math.degrees(float(np.sum(steps))))
    if sweep < ARC_MIN_SWEEP:
        return None
    # chord length must be small relative to the radius (a polygon with few long sides is not an arc)
    if np.max(np.hypot(*np.diff(P, axis=0).T)) > 0.6 * r:
        return None
    a_start, a_end = angs[0] % 360, angs[-1] % 360
    if np.sum(steps) < 0:
        a_start, a_end = a_end, a_start
    return (round(cx, 6), round(cy, 6)), round(r, 6), round(a_start, 4), round(a_end, 4), sweep


def _chains(lines: list[Primitive], tol: float) -> list[list[tuple[Primitive, tuple, tuple]]]:
    """Maximal chains of segments joined end to end where exactly two segments meet."""
    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    ends = defaultdict(list)
    for ln in lines:
        a, b = tuple(ln.pts[0]), tuple(ln.pts[-1])
        ends[key(a)].append((ln, a, b))
        ends[key(b)].append((ln, b, a))
    used = set()
    chains = []
    for ln in lines:
        if ln.id in used:
            continue
        chain = [(ln, tuple(ln.pts[0]), tuple(ln.pts[-1]))]
        used.add(ln.id)
        for direction in (1, 0):
            while True:
                tip = chain[-1][2] if direction else chain[0][1]
                nxt = [e for e in ends[key(tip)] if e[0].id not in used]
                if len(ends[key(tip)]) != 2 or len(nxt) != 1:
                    break
                e, start, end = nxt[0]
                used.add(e.id)
                if direction:
                    chain.append((e, start, end))
                else:
                    chain.insert(0, (e, end, start))
        chains.append(chain)
    return chains


def _smooth_runs(chain):
    """Split a chain where it turns sharply or segment lengths jump (an arc meeting its leaf)."""
    runs, cur = [], [chain[0]]
    for prev, nxt in zip(chain, chain[1:]):
        a = math.degrees(math.atan2(prev[2][1] - prev[1][1], prev[2][0] - prev[1][0]))
        b = math.degrees(math.atan2(nxt[2][1] - nxt[1][1], nxt[2][0] - nxt[1][0]))
        turn = abs((b - a + 180) % 360 - 180)
        l1, l2 = math.dist(prev[1], prev[2]), math.dist(nxt[1], nxt[2])
        if turn > 30 or max(l1, l2) > 2 * min(l1, l2):
            runs.append(cur)
            cur = [nxt]
        else:
            cur.append(nxt)
    runs.append(cur)
    return runs


def fit_arcs(sheet: Sheet) -> int:
    """Replace circular chains of short lines/polylines by ARC primitives. Returns the count."""
    diag = math.hypot(sheet.width or 1.0, sheet.height or 1.0)
    tol = max(diag * ENDPOINT_TOL_REL, 1e-6)
    ids = IdFactory(sheet.id + ":arcfit")
    cand = [p for p in sheet.primitives if p.kind == "line" and not p.hidden and not (p.block or "").startswith("dim:")]
    new = []
    n = 0
    for chain in (run for full in _chains(cand, tol) for run in _smooth_runs(full)):
        if len(chain) < ARC_MIN_SEGMENTS:
            continue
        pts = [chain[0][1]] + [c[2] for c in chain]
        arc = _arc_from_points(pts)
        if not arc:
            continue
        (c, r, a0, a1, _sw) = arc
        base = chain[0][0]
        for ln, _, _ in chain:
            ln.hidden = True
            ln.prov.evidence["replaced_by_arc"] = True
        new.append(Primitive(id=ids("arc", c, r, a0), kind="arc", center=c, radius=r, a0=a0, a1=a1,
                             layer=base.layer, width=base.width, block=base.block,
                             prov=Prov(source=base.prov.source, stage="arc_fit",
                                       evidence={"members": [ln.id for ln, _, _ in chain], "layer": base.layer})))
        n += 1
    for p in sheet.primitives:
        if p.kind == "polyline" and not p.hidden and len(p.pts) >= ARC_MIN_SEGMENTS + 1:
            arc = _arc_from_points(p.pts)
            if arc:
                (c, r, a0, a1, _sw) = arc
                p.hidden = True
                new.append(Primitive(id=ids("arc", c, r, a0), kind="arc", center=c, radius=r, a0=a0, a1=a1,
                                     layer=p.layer, width=p.width, block=p.block,
                                     prov=Prov(source=p.prov.source, stage="arc_fit", evidence={"members": [p.id]})))
                n += 1
    sheet.primitives.extend(new)
    return n


def tag_glazing(sheet: Sheet, mpu: float) -> int:
    """Mark window symbols: >= 3 parallel lines of equal length, ends aligned, spanning <= 0.60 m."""
    lines = [p for p in sheet.primitives if p.kind == "line" and not p.hidden
             and not (p.block or "").startswith("dim:")]
    by_len = defaultdict(list)
    for ln in lines:
        L = seg_len(ln.pts[0], ln.pts[1])
        if L * mpu < 0.3 or L * mpu > 4.0:
            continue
        by_len[round(seg_angle(ln.pts[0], ln.pts[1]))].append((ln, L))
    tagged = 0
    max_span = GLAZ_MAX_SPAN_M / mpu
    for _ang, group in by_len.items():
        group.sort(key=lambda x: x[1])
        for ln, L in group:
            if ln.prov.evidence.get("glazing"):
                continue
            a = np.array(ln.pts[0], float)
            b = np.array(ln.pts[1], float)
            u = (b - a) / L
            nrm = np.array([-u[1], u[0]])
            members = [(ln, 0.0)]
            for other, L2 in group:
                if other is ln or abs(L2 - L) > GLAZ_LEN_REL * L:
                    continue
                if angle_diff(seg_angle(ln.pts[0], ln.pts[1]), seg_angle(other.pts[0], other.pts[1])) > GLAZ_ANGLE:
                    continue
                p, q = np.array(other.pts[0], float), np.array(other.pts[1], float)
                off = float(np.dot(p - a, nrm))
                if abs(off) > 3 * max_span or abs(off) < 1e-9:     # look wider to reject stair-like runs
                    continue
                s = sorted([float(np.dot(p - a, u)), float(np.dot(q - a, u))])
                if abs(s[0]) > GLAZ_LEN_REL * L or abs(s[1] - L) > GLAZ_LEN_REL * L:
                    continue
                members.append((other, off))
            offs = sorted({round(o, 6) for _, o in members})
            if len(offs) < GLAZ_MIN_LINES or offs[-1] - offs[0] > max_span:
                continue
            # roughly even spacing (a window symbol, not three random parallels)
            gaps = np.diff(offs)
            if gaps.max() > 3 * gaps.min() + 1e-9:
                continue
            for m, _ in members:
                m.prov.evidence["glazing"] = True
                tagged += 1
    return tagged


DOOR_SWEEP = (75.0, 105.0)
LEAF_TOL_REL = 0.05


def tag_door_leaves(sheet: Sheet) -> int:
    """Mark door leaves: a line from the centre of a ~90 deg arc to one of its ends, with the
    arc radius as length. Leaves drawn open lie parallel to nearby walls and must not be
    paired as wall faces; the opening detector still finds them through the arc."""
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    from .geometry import arc_sweep

    lines = [p for p in sheet.primitives if p.kind == "line" and not p.hidden]
    if not lines:
        return 0
    tree = STRtree([LineString(p.pts) for p in lines])
    n = 0
    for arc in sheet.primitives:
        if arc.kind != "arc" or arc.hidden or not (DOOR_SWEEP[0] <= arc_sweep(arc.a0, arc.a1) <= DOOR_SWEEP[1]):
            continue
        c = np.array(arc.center)
        r = arc.radius
        tol = LEAF_TOL_REL * r
        ends = [c + r * np.array([math.cos(math.radians(a)), math.sin(math.radians(a))]) for a in (arc.a0, arc.a1)]
        for i in tree.query(Point(c).buffer(tol)):
            ln = lines[i]
            a, b = np.array(ln.pts[0]), np.array(ln.pts[-1])
            for h, o in ((a, b), (b, a)):
                if np.linalg.norm(h - c) <= tol and any(np.linalg.norm(o - e) <= tol for e in ends):
                    ln.prov.evidence["door_leaf"] = True
                    n += 1
    return n


PATTERN_MIN_LINES = 4
PATTERN_MAX_SPACING_M = 0.60        # up to the thickest wall: hatch inside thick walls
PATTERN_MAX_LEN_PER_SPACING = 10.0  # strokes are short relative to their spacing (faces are not)
PATTERN_SPACING_TOL = 0.2
PATTERN_LEVEL_LEN_RATIO = 3.0


def tag_patterns(sheet: Sheet, mpu: float) -> int:
    """Mark regular families of parallel lines (exploded hatch patterns, stair treads).

    Families are built from real neighbours - parallel lines closer than 0.35 m that overlap along
    their axis - so lines of different walls never mix. A family of at least four lines whose
    neighbour spacings are mostly equal (within 20% of the median) is drawing texture, never a wall."""
    from shapely.strtree import STRtree

    lines = [p for p in sheet.primitives if p.kind == "line" and not p.hidden
             and not p.prov.evidence.get("glazing") and not p.prov.evidence.get("dim_graphic")]
    if len(lines) < PATTERN_MIN_LINES:
        return 0
    P = np.array([p.pts[0] for p in lines], float)
    Q = np.array([p.pts[1] for p in lines], float)
    D = Q - P
    L = np.hypot(D[:, 0], D[:, 1])
    U = D / np.where(L > 0, L, 1.0)[:, None]
    N = np.stack([-U[:, 1], U[:, 0]], axis=1)
    ang = np.degrees(np.arctan2(D[:, 1], D[:, 0])) % 180.0
    max_sp = PATTERN_MAX_SPACING_M / mpu
    # one bulk query for every neighbour pair within the maximum spacing, then vectorised tests
    import shapely

    # candidate pairs by bounding boxes grown by the maximum spacing (no exact distances here:
    # the vectorised tests below are the exact ones)
    tree = STRtree(shapely.linestrings(np.stack([P, Q], axis=1)))
    lo, hi = np.minimum(P, Q) - max_sp, np.maximum(P, Q) + max_sp
    ii, jj = tree.query(shapely.box(lo[:, 0], lo[:, 1], hi[:, 0], hi[:, 1]))
    keep = (ii != jj) & (L[ii] > 0)
    ii, jj = ii[keep], jj[keep]
    da = np.abs(ang[ii] - ang[jj]) % 180.0
    keep = np.minimum(da, 180.0 - da) <= GLAZ_ANGLE
    ii, jj = ii[keep], jj[keep]
    mid_j = (P[jj] + Q[jj]) / 2
    off = np.abs(np.einsum("ij,ij->i", mid_j - P[ii], N[ii]))
    s_p = np.einsum("ij,ij->i", P[jj] - P[ii], U[ii])
    s_q = np.einsum("ij,ij->i", Q[jj] - P[ii], U[ii])
    s0, s1 = np.minimum(s_p, s_q), np.maximum(s_p, s_q)
    overlap = np.minimum(L[ii], s1) - np.maximum(0.0, s0)
    keep = (off > 1e-9) & (off <= max_sp) & (overlap >= 0.5 * np.minimum(L[ii], s1 - s0))
    ii, jj, off = ii[keep], jj[keep], off[keep]
    parent = list(range(len(lines)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in zip(ii.tolist(), jj.tolist()):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    nearest = np.full(len(lines), np.inf)
    np.minimum.at(nearest, ii, off)
    spacing: dict[int, list[float]] = {i: [float(nearest[i])] for i in range(len(lines)) if np.isfinite(nearest[i])}
    fams: dict[int, list[int]] = defaultdict(list)
    for i in range(len(lines)):
        fams[find(i)].append(i)
    tagged = 0
    for members in fams.values():
        if len(members) < PATTERN_MIN_LINES:
            continue
        # strokes of a texture are short and alike: lines far longer than the family's median stroke
        # (wall faces, edges passing by) are not strokes and are left out of the analysis
        lens = {i: seg_len(lines[i].pts[0], lines[i].pts[1]) for i in members}
        m_len = float(np.median(list(lens.values())))
        members = [i for i in members if lens[i] <= PATTERN_LEVEL_LEN_RATIO * m_len]
        if len(members) < PATTERN_MIN_LINES:
            continue
        # a hatch or a stair is drawn as one thing: its strokes share a layer
        layer_counts: dict[str, int] = defaultdict(int)
        for i in members:
            layer_counts[lines[i].layer or ""] += 1
        if max(layer_counts.values()) < 0.8 * len(members):
            continue
        gaps = [spacing[i][0] for i in members if i in spacing]
        if len(gaps) < PATTERN_MIN_LINES - 1:
            continue
        med = float(np.median(gaps))
        regular = sum(abs(g - med) <= PATTERN_SPACING_TOL * med for g in gaps) / len(gaps)
        if regular < 0.7:
            continue
        # at least four distinct, evenly spaced positions across the family: the two faces of a
        # wall split into many segments are two positions, not a pattern
        a0 = np.array(lines[members[0]].pts[0], float)
        b0 = np.array(lines[members[0]].pts[1], float)
        u0 = (b0 - a0) / (np.linalg.norm(b0 - a0) or 1.0)
        n0 = np.array([-u0[1], u0[0]])
        offs = sorted((float(((np.array(lines[i].pts[0]) + np.array(lines[i].pts[1])) / 2) @ n0),
                       seg_len(lines[i].pts[0], lines[i].pts[1])) for i in members)
        levels, level_len = [offs[0][0]], [[offs[0][1]]]
        for o, ln in offs[1:]:
            if o - levels[-1] > PATTERN_SPACING_TOL * med:
                levels.append(o)
                level_len.append([ln])
            else:
                level_len[-1].append(ln)
        if len(levels) < PATTERN_MIN_LINES:
            continue
        lv_gaps = np.diff(levels)
        if float(np.median([np.median(v) for v in level_len])) > PATTERN_MAX_LEN_PER_SPACING * float(np.median(lv_gaps)):
            continue
        if np.mean(np.abs(lv_gaps - np.median(lv_gaps)) <= PATTERN_SPACING_TOL * np.median(lv_gaps)) < 0.7:
            continue
        # texture is uniform: the strokes of a hatch or the treads of a stair are about as long on
        # every level (robust to clipped corner strokes); a wall face next to axis dashes and a sofa
        # edge is not
        med_len = [float(np.median(v)) for v in level_len]
        lo, hi = np.percentile(med_len, [20, 80])
        if hi > PATTERN_LEVEL_LEN_RATIO * lo:
            continue
        for i in members:
            if not lines[i].prov.evidence.get("pattern"):
                lines[i].prov.evidence["pattern"] = True
                tagged += 1
    return tagged

