"""R8 - Wall candidates from vector primitives.

A primitive is not a wall: walls are *pairs* of parallel faces (or filled
strips, or thick single strokes) that survive merging, junction snapping and a
score. Columns (small filled blocks on wall layers) are returned as well because
they are barriers for the room step.

All thresholds are in metres and converted to sheet units with ``mpu``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

from ..core.geometry import angle_diff, seg_angle, seg_len
from ..core.ids import IdFactory
from ..schema import Element, Primitive, Prov, Sheet

DROP_LAYER_RE = re.compile(
    r"(?i)dim|cote|cotation|text|txt|annot|hatch|haching|hachur|furn|mobil|equip|axe|grid|axis|cartouche|frame|cadre|"
    r"ttlb|title|tabl|sched|glaz|window|fenetre|fen\b|door|porte|menuis")
WALL_LAYER_RE = re.compile(r"(?i)wall|mur|cloison|struct")

MIN_SEG_M = 0.10
PAIR_MAX_ANGLE = 2.0
T_MIN_M, T_MAX_M = 0.04, 0.60      # 4 cm: glazed and board partitions
MIN_OVERLAP_M = 0.30
SHORT_OVERLAP_M = 0.10      # floor for faces that are part of continuous outlines
LONG_FACE_M = 1.0           # a face this long may carry a short piece (pier) on its other side
MERGE_ANGLE = 1.0
MIN_SCORE = 0.5


@dataclass
class Seg:
    idx: int
    prim: Primitive
    a: tuple[float, float]
    b: tuple[float, float]
    length: float
    angle: float
    covered: dict = field(default_factory=lambda: {1: [], -1: []})   # side -> intervals along the segment
    thick: dict = field(default_factory=dict)                        # side -> [(lo, hi, thickness)]
    group: str = ""                                                  # source outline (polyline / PDF path)


@dataclass
class WallPiece:
    a: np.ndarray
    b: np.ndarray
    t: float
    members: set
    both_faces_len: float
    layer_hit: bool
    source: str = "pairs"
    conn_a: bool = False
    conn_b: bool = False

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.b - self.a))

    @property
    def u(self) -> np.ndarray:
        d = self.b - self.a
        n = np.linalg.norm(d)
        return d / n if n else np.array([1.0, 0.0])


def _line_pool(sheet: Sheet, mpu: float, exclude_boxes: list, allowed_layers: set | None = None) -> list[Seg]:
    has_wall_layer = any(WALL_LAYER_RE.search(p.layer or "") for p in sheet.primitives)
    segs: list[Seg] = []
    min_len = MIN_SEG_M / mpu
    for p in sheet.primitives:
        if p.hidden or (p.block or "").startswith("dim:"):
            continue
        layer = p.layer or ""
        if DROP_LAYER_RE.search(layer):
            continue
        if allowed_layers is not None and layer_key(p) not in allowed_layers:
            continue
        if has_wall_layer and not WALL_LAYER_RE.search(layer) and layer not in ("0", ""):
            # a sheet with wall layers: keep only wall-like layers (and layer 0 leftovers)
            continue
        ev = p.prov.evidence
        if ev.get("glazing") or ev.get("dim_graphic") or ev.get("door_leaf") or ev.get("pattern"):
            continue
        if ev.get("learned_wall") is False:
            continue        # learned classifier (second pass): not a wall line
        if p.kind in ("line", "polyline"):
            chain = [p.pts]
        elif p.kind == "polygon":
            # outlines and the edges of filled regions (walls drawn as solid fill) are face candidates
            chain = [p.pts + p.pts[:1]]
        else:
            continue
        for pts in chain:
            for a, b in zip(pts, pts[1:]):
                L = seg_len(a, b)
                if L < min_len:
                    continue
                if exclude_boxes and any(_in_box(a, bx) and _in_box(b, bx) for bx in exclude_boxes):
                    continue
                segs.append(Seg(len(segs), p, tuple(a), tuple(b), L, seg_angle(a, b), group=_outline_key(p)))
    return segs


def _in_box(p, bx) -> bool:
    return bx[0] <= p[0] <= bx[2] and bx[1] <= p[1] <= bx[3]


def _interval_overlap(iv, ivs) -> float:
    lo, hi = iv
    tot = 0.0
    for a, b in ivs:
        tot += max(0.0, min(hi, b) - max(lo, a))
    return tot


def _outline_key(p: Primitive) -> str:
    ev = p.prov.evidence
    if ev.get("entity"):
        return "e:" + str(ev["entity"])
    if p.kind in ("polygon", "polyline"):
        return "p:" + p.id
    if ev.get("seqno") is not None:
        return "s:" + str(ev["seqno"])
    return "p:" + p.id


SYMBOL_MAX_DIAG_M = 3.0


def _small_closed_loops(segs: list[Seg], mpu: float) -> dict[str, tuple]:
    """Outline groups that close on themselves and are smaller than a room: group -> bbox."""
    by: dict[str, list[Seg]] = {}
    for s in segs:
        by.setdefault(s.group, []).append(s)
    tol = 0.005 / mpu
    out = {}
    for g, ss in by.items():
        if len(ss) < 3:
            continue
        deg: dict[tuple, int] = {}
        for s in ss:
            for q in (s.a, s.b):
                k = (round(q[0] / tol), round(q[1] / tol))
                deg[k] = deg.get(k, 0) + 1
        if any(v != 2 for v in deg.values()):
            continue
        xs = [q[0] for s in ss for q in (s.a, s.b)]
        ys = [q[1] for s in ss for q in (s.a, s.b)]
        bb = (min(xs), min(ys), max(xs), max(ys))
        if np.hypot(bb[2] - bb[0], bb[3] - bb[1]) * mpu < SYMBOL_MAX_DIAG_M:
            out[g] = bb
    return out


def _object_outlines(segs: list[Seg], mpu: float) -> set[str]:
    """Small closed outlines wider than any wall: bathtubs, lift cars, counters, furniture. Width is
    the diameter of the largest circle inside the outline, so a wall body drawn as one closed outline
    (straight, L or T shaped, as thick as the wall) is not an object; an object outline is never a
    wall face."""
    from shapely.geometry import LineString as LS
    from shapely.ops import polygonize, polylabel

    loops = _small_closed_loops(segs, mpu)
    lines: dict[str, list] = {}
    for s in segs:
        if s.group in loops:
            lines.setdefault(s.group, []).append(LS([s.a, s.b]))
    out = set()
    for g, ls in lines.items():
        polys = list(polygonize(ls))
        if not polys:
            continue
        poly = max(polys, key=lambda q: q.area)
        width = 2 * polylabel(poly, tolerance=0.005 / mpu).distance(poly.exterior)
        if width * mpu > T_MAX_M:
            out.add(g)
    return out


def _nested_symbol(g1: str, g2: str, loops: dict[str, tuple]) -> bool:
    """Faces from two different small closed outlines, one inside the other: an object symbol
    (sofa, bathtub, counter with an inner line), never the two faces of a wall."""
    if g1 == g2 or g1 not in loops or g2 not in loops:
        return False
    a, b = loops[g1], loops[g2]

    def inside(x, y):
        return x[0] >= y[0] - 1e-9 and x[1] >= y[1] - 1e-9 and x[2] <= y[2] + 1e-9 and x[3] <= y[3] + 1e-9

    return inside(a, b) or inside(b, a)


def _glued_too_thick(seg: Seg, other_side: int, iv: tuple, d_new: float, ov: float, tmax: float) -> bool:
    for lo, hi, d_old in seg.thick.get(other_side, []):
        if max(0.0, min(iv[1], hi) - max(iv[0], lo)) > 0.5 * ov and d_old + d_new > tmax:
            return True
    return False


def _pairs(segs: list[Seg], mpu: float) -> list[WallPiece]:
    tmin, tmax = T_MIN_M / mpu, T_MAX_M / mpu
    min_ov = MIN_OVERLAP_M / mpu
    tree = STRtree([LineString([s.a, s.b]) for s in segs])
    # outline continuity: a face whose both ends meet other segments belongs to a drawn outline;
    # such faces may pair over a short overlap (short wall pieces between junctions)
    tol = 0.01 / mpu
    deg: dict[tuple, int] = {}
    for s in segs:
        for p in (s.a, s.b):
            k = (round(p[0] / tol), round(p[1] / tol))
            deg[k] = deg.get(k, 0) + 1

    def closed(s: Seg) -> bool:
        return all(deg.get((round(p[0] / tol), round(p[1] / tol)), 0) >= 2 for p in (s.a, s.b))

    loops = _small_closed_loops(segs, mpu)
    objects = _object_outlines(segs, mpu)
    cands = []
    for s in segs:
        A = np.array(s.a)
        B = np.array(s.b)
        u = (B - A) / s.length
        n = np.array([-u[1], u[0]])
        for j in tree.query(LineString([s.a, s.b]).buffer(tmax)):
            if j <= s.idx:
                continue
            o = segs[j]
            if angle_diff(s.angle, o.angle) > PAIR_MAX_ANGLE:
                continue
            P, Q = np.array(o.a), np.array(o.b)
            dp, dq = float(np.dot(P - A, n)), float(np.dot(Q - A, n))
            d = (dp + dq) / 2
            if not (tmin <= abs(d) <= tmax) or abs(dp - dq) > 0.1 * abs(d) + 1e-9:
                continue
            tp, tq = float(np.dot(P - A, u)), float(np.dot(Q - A, u))
            lo, hi = max(0.0, min(tp, tq)), min(s.length, max(tp, tq))
            ov = hi - lo
            need = min_ov
            if ov < min_ov and (closed(s) and closed(o) or max(s.length, o.length) >= LONG_FACE_M / mpu):
                # a short piece (pier, stub) against a continuous outline or a long face
                need = max(SHORT_OVERLAP_M / mpu, abs(d))
            if ov < need or ov < 0.5 * min(s.length, o.length):
                continue
            if _nested_symbol(s.group, o.group, loops) or s.group in objects or o.group in objects:
                continue
            cands.append((ov, s, o, lo, hi, d, u, n, A))
    # walls on one sheet share a few recurring thicknesses; candidates at a dominant thickness are
    # accepted first so a wardrobe or counter front can never displace the wall it stands against
    hist: dict[int, float] = {}
    bin_w = 0.02 / mpu
    for c in cands:
        k = int(round(abs(c[5]) / bin_w))
        hist[k] = hist.get(k, 0.0) + c[0]
    top = sorted(hist.values(), reverse=True)[:3]
    floor = top[-1] if top else 0.0

    def dominant(c) -> bool:
        k = int(round(abs(c[5]) / bin_w))
        return max(hist.get(k - 1, 0), hist.get(k, 0), hist.get(k + 1, 0)) >= floor

    cands.sort(key=lambda c: (not dominant(c), -c[0]))
    pieces = []
    bodies: list = []
    grid: dict[tuple, list[int]] = {}          # spatial hash of accepted bodies
    cell = 2.0 / mpu
    for ov, s, o, lo, hi, d, u, n, A in cands:
        side_s = 1 if d > 0 else -1
        # the same interval on the partner, measured along the partner's own axis
        P = np.array(o.a)
        uo = (np.array(o.b) - P) / o.length
        p_lo = float(np.dot(A + u * lo - P, uo))
        p_hi = float(np.dot(A + u * hi - P, uo))
        p_lo, p_hi = min(p_lo, p_hi), max(p_lo, p_hi)
        no = np.array([-uo[1], uo[0]])
        side_o = 1 if float(np.dot(A - P, no)) > 0 else -1
        if _interval_overlap((lo, hi), s.covered[side_s]) > 0.5 * ov:
            continue
        if _interval_overlap((p_lo, p_hi), o.covered[side_o]) > 0.5 * ov:
            continue
        # a face already bounding a wall on its other side may only take a second body if both
        # together still make one plausible wall (cavity walls drawn as 3-4 lines); a wardrobe or a
        # counter drawn against a wall face would make an impossibly thick wall and is rejected
        if _glued_too_thick(s, -side_s, (lo, hi), abs(d), ov, tmax) or \
                _glued_too_thick(o, -side_o, (p_lo, p_hi), abs(d), ov, tmax):
            continue
        a = A + u * lo + n * d / 2
        b = A + u * hi + n * d / 2
        # two pieces cannot occupy the same material: a block's end caps must not pair
        # across a piece already built from its (longer-overlap) faces
        body = LineString([tuple(a), tuple(b)]).buffer(abs(d) / 2, cap_style="flat")
        bb = body.bounds
        cells = [(cx, cy) for cx in range(int(bb[0] // cell), int(bb[2] // cell) + 1)
                 for cy in range(int(bb[1] // cell), int(bb[3] // cell) + 1)]
        near = {k for c in cells for k in grid.get(c, ())}
        if any(body.intersection(bodies[k]).area > 0.5 * min(body.area, bodies[k].area) for k in near
               if bodies[k].bounds[0] <= bb[2] and bb[0] <= bodies[k].bounds[2]
               and bodies[k].bounds[1] <= bb[3] and bb[1] <= bodies[k].bounds[3]):
            continue
        for c in cells:
            grid.setdefault(c, []).append(len(bodies))
        bodies.append(body)
        s.covered[side_s].append((lo, hi))
        o.covered[side_o].append((p_lo, p_hi))
        s.thick.setdefault(side_s, []).append((lo, hi, abs(d)))
        o.thick.setdefault(side_o, []).append((p_lo, p_hi, abs(d)))
        hit = bool(WALL_LAYER_RE.search(s.prim.layer or "") or WALL_LAYER_RE.search(o.prim.layer or ""))
        pieces.append(WallPiece(a, b, abs(d), {s.prim.id, o.prim.id}, ov, hit))
    return pieces


def _filled_and_columns(sheet: Sheet, mpu: float,
                        allowed_layers: set | None = None) -> tuple[list[WallPiece], list[Polygon], list[set]]:
    pieces, columns, col_members = [], [], []
    tmin, tmax = T_MIN_M / mpu, T_MAX_M / mpu
    for p in sheet.primitives:
        if p.hidden or not p.filled or p.kind != "polygon" or len(p.pts) < 3:
            continue
        layer = p.layer or ""
        if DROP_LAYER_RE.search(layer) or (allowed_layers is not None and layer_key(p) not in allowed_layers):
            continue
        poly = Polygon(p.pts)
        if not poly.is_valid or poly.area <= 0:
            continue
        rect = poly.minimum_rotated_rectangle
        cs = list(rect.exterior.coords)[:4]
        e0, e1 = seg_len(cs[0], cs[1]), seg_len(cs[1], cs[2])
        long_, short = max(e0, e1), min(e0, e1)
        if short <= 0:
            continue
        if long_ / short >= 3 and tmin <= short <= tmax:
            if e0 >= e1:
                a = (np.array(cs[0]) + np.array(cs[3])) / 2
                b = (np.array(cs[1]) + np.array(cs[2])) / 2
            else:
                a = (np.array(cs[0]) + np.array(cs[1])) / 2
                b = (np.array(cs[3]) + np.array(cs[2])) / 2
            pieces.append(WallPiece(a, b, short, {p.id}, long_, bool(WALL_LAYER_RE.search(layer)), "filled"))
        elif short >= tmin and long_ <= 1.2 / mpu and (WALL_LAYER_RE.search(layer) or layer in ("0", "")):
            columns.append(poly)
            col_members.append({p.id})
    return pieces, columns, col_members


def _thick_lines(sheet: Sheet, mpu: float, used: set) -> list[WallPiece]:
    """Lines drawn with a stroke as thick as a wall (top width class, wall-like layer)."""
    widths = [p.width for p in sheet.primitives if p.kind == "line" and p.width]
    if not widths:
        return []
    top = max(widths)
    out = []
    for p in sheet.primitives:
        if p.kind != "line" or not p.width or p.id in used or p.hidden:
            continue
        if not WALL_LAYER_RE.search(p.layer or ""):
            continue
        t = p.width
        if p.width < 0.8 * top or t * mpu < 0.08 or t * mpu > T_MAX_M:
            continue
        a, b = np.array(p.pts[0]), np.array(p.pts[1])
        if np.linalg.norm(b - a) * mpu < 0.5:
            continue
        out.append(WallPiece(a, b, t, {p.id}, float(np.linalg.norm(b - a)), True, "thick_line"))
    return out


def _merge(pieces: list[WallPiece], mpu: float) -> list[WallPiece]:
    """Merge collinear pieces: same axis (angle within 1 deg, offset within a quarter thickness),
    similar thickness (20%), small gap or overlap. Pieces are grouped by line, then swept along it,
    so the cost is O(n log n) whatever the drawing size."""
    if not pieces:
        return pieces
    ang = np.array([seg_angle(tuple(w.a), tuple(w.b)) for w in pieces])
    order = np.argsort(ang)
    # angle clusters (wrapping at 180 deg)
    clusters: list[list[int]] = [[int(order[0])]]
    for k in order[1:]:
        if ang[k] - ang[clusters[-1][-1]] <= MERGE_ANGLE:
            clusters[-1].append(int(k))
        else:
            clusters.append([int(k)])
    if len(clusters) > 1 and ang[clusters[0][0]] + 180.0 - ang[clusters[-1][-1]] <= MERGE_ANGLE:
        clusters[0] = clusters.pop() + clusters[0]
    out: list[WallPiece] = []
    gap_floor = 0.10 / mpu
    for cl in clusters:
        ref = pieces[cl[0]]
        u = ref.u
        n = np.array([-u[1], u[0]])
        # line groups by perpendicular offset
        by_off = sorted(cl, key=lambda i: float(np.dot((pieces[i].a + pieces[i].b) / 2, n)))
        lines: list[list[int]] = []
        for i in by_off:
            o = float(np.dot((pieces[i].a + pieces[i].b) / 2, n))
            if lines:
                j = lines[-1][-1]
                oj = float(np.dot((pieces[j].a + pieces[j].b) / 2, n))
                if o - oj <= max(pieces[i].t, pieces[j].t) / 4:
                    lines[-1].append(i)
                    continue
            lines.append([i])
        for ln in lines:
            items = []
            for i in ln:
                w = pieces[i]
                s0, s1 = sorted([float(np.dot(w.a, u)), float(np.dot(w.b, u))])
                items.append((s0, s1, w))
            items.sort(key=lambda x: x[0])
            cur = None
            for s0, s1, w in items:
                if cur is not None:
                    cs0, cs1, m = cur
                    t_ref = max(m.t, w.t)
                    if s0 - cs1 <= max(t_ref, gap_floor) + 1e-9 and abs(w.t - m.t) <= 0.2 * t_ref:
                        ov = max(0.0, min(cs1, s1) - max(cs0, s0))
                        m.both_faces_len = m.both_faces_len + w.both_faces_len - min(ov, w.both_faces_len)
                        m.t = (m.t * (cs1 - cs0) + w.t * (s1 - s0)) / ((cs1 - cs0) + (s1 - s0))
                        m.members |= w.members
                        m.layer_hit = m.layer_hit or w.layer_hit
                        cur = (cs0, max(cs1, s1), m)
                        continue
                    out.append(_finish_line(cur, u, n))
                cur = (s0, s1, w)
            if cur is not None:
                out.append(_finish_line(cur, u, n))
    return out


def _finish_line(cur, u, n) -> WallPiece:
    s0, s1, m = cur
    off = float(np.dot((m.a + m.b) / 2, n))
    m.a = u * s0 + n * off
    m.b = u * s1 + n * off
    return m



def _drop_glued(pieces: list[WallPiece], mpu: float, p_wall: dict[str, tuple[float, float]] | None = None
                ) -> list[WallPiece]:
    """Two parallel bodies lying side by side (touching along most of the shorter one) whose combined
    thickness exceeds any plausible wall: one of them is an object against a wall (wardrobe, counter,
    sofa). Keep the piece the learned classifier believes more (``p_wall``: line id -> (probability,
    length), second pass only), then the one whose thickness is most common on the sheet, then the
    longer one. Measured: on thickness alone, a true wall lost to a pair of its outer face with a
    parallel outline (FloorPlanCAD 0460-0018, faces at 0.9 dropped, room lost)."""
    tmax = T_MAX_M / mpu
    touch = 0.02 / mpu
    binw = 0.02 / mpu
    lengths: dict[int, float] = {}
    for w in pieces:
        k = int(round(w.t / binw))
        lengths[k] = lengths.get(k, 0.0) + w.length

    def support(w):
        k = int(round(w.t / binw))
        return lengths.get(k - 1, 0) + lengths.get(k, 0) + lengths.get(k + 1, 0)

    def belief(w):
        if not p_wall:
            return 0.0
        pl = [p_wall[m] for m in w.members if m in p_wall]
        tot = sum(L for _, L in pl)
        return round(sum(p * L for p, L in pl) / tot, 2) if tot else 0.0

    bodies = [LineString([tuple(w.a), tuple(w.b)]).buffer(w.t / 2, cap_style="flat") for w in pieces]
    tree = STRtree(bodies) if bodies else None
    drop: set[int] = set()
    for i, w in enumerate(pieces):
        if i in drop or tree is None:
            continue
        for j in tree.query(bodies[i].buffer(touch)):
            if j == i or j in drop:
                continue
            o = pieces[j]
            # a learned face has no drawn thickness (an assumed one, centred on its line): it cannot
            # tell how thick two bodies are together. Measured: its assumed body made true walls next
            # to it "too thick" and both were dropped.
            if w.t + o.t <= tmax or "learned_face" in (w.source, o.source):
                continue
            if angle_diff(seg_angle(tuple(w.a), tuple(w.b)), seg_angle(tuple(o.a), tuple(o.b))) > PAIR_MAX_ANGLE:
                continue
            u = w.u
            nrm = np.array([-u[1], u[0]])
            gap = abs(float(np.dot((o.a + o.b) / 2 - (w.a + w.b) / 2, nrm))) - (w.t + o.t) / 2
            if gap > touch:
                continue
            s_o = sorted([float(np.dot(o.a - w.a, u)), float(np.dot(o.b - w.a, u))])
            ov = min(w.length, s_o[1]) - max(0.0, s_o[0])
            if ov < 0.5 * min(w.length, o.length):
                continue
            loser = j if (belief(w), support(w), w.length) >= (belief(o), support(o), o.length) else i
            drop.add(loser)
            if loser == i:
                break
    return [w for k, w in enumerate(pieces) if k not in drop]


def _drop_isolated_clusters(walls: list[WallPiece], mpu: float, max_diag_m: float = 3.0) -> list[WallPiece]:
    """Walls form one connected network; a small cluster touching nothing else (nested furniture
    outlines, symbols) is an object. Clusters under 3 m across and apart from the main network go."""
    if len(walls) < 2:
        return walls
    bodies = [LineString([tuple(w.a), tuple(w.b)]).buffer(w.t / 2 + 0.03 / mpu, cap_style="square") for w in walls]
    tree = STRtree(bodies)
    parent = list(range(len(walls)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, b in enumerate(bodies):
        for j in tree.query(b):
            if j != i and b.intersects(bodies[j]):
                parent[find(i)] = find(j)
    # pieces on one axis separated by an opening-sized gap belong to the same wall (piers between doors)
    gap_max = 3.0 / mpu
    for i, w in enumerate(walls):
        u = w.u
        nrm = np.array([-u[1], u[0]])
        reach = LineString([tuple(w.a - u * gap_max), tuple(w.b + u * gap_max)]).buffer(w.t / 2)
        for j in tree.query(reach):
            if j == i or find(i) == find(j):
                continue
            o = walls[j]
            if angle_diff(seg_angle(tuple(w.a), tuple(w.b)), seg_angle(tuple(o.a), tuple(o.b))) > MERGE_ANGLE:
                continue
            if abs(w.t - o.t) > 0.2 * max(w.t, o.t):
                continue        # one wall continues across an opening with the same thickness
            if abs(float(np.dot((o.a + o.b) / 2 - w.a, nrm))) <= max(w.t, o.t) / 2:
                parent[find(i)] = find(j)
    comps: dict[int, list[int]] = {}
    for i in range(len(walls)):
        comps.setdefault(find(i), []).append(i)
    main = max(comps.values(), key=lambda c: sum(walls[i].length for i in c))
    keep = []
    for c in comps.values():
        if c is main:
            keep += c
            continue
        pts = np.array([p for i in c for p in (walls[i].a, walls[i].b)])
        diag = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
        if diag * mpu >= max_diag_m:
            keep += c
    return [walls[i] for i in sorted(keep)]


def _line_intersection(p, r, q, s):
    """Intersection of p + t r and q + v s; returns (point, t, v) or None if parallel."""
    rxs = r[0] * s[1] - r[1] * s[0]
    if abs(rxs) < 1e-12:
        return None
    qp = q - p
    t = (qp[0] * s[1] - qp[1] * s[0]) / rxs
    v = (qp[0] * r[1] - qp[1] * r[0]) / rxs
    return p + t * r, t, v


def _wall_index(walls: list[WallPiece]):
    lines = [LineString([tuple(w.a), tuple(w.b)]) for w in walls]
    return lines, (STRtree(lines) if lines else None)


def _snap_junctions(walls: list[WallPiece], mpu: float) -> None:
    if not walls:
        return
    lines, tree = _wall_index(walls)
    tmax = max(w.t for w in walls)
    angles = [seg_angle(tuple(w.a), tuple(w.b)) for w in walls]
    for wi, w in enumerate(walls):
        for end in ("a", "b"):
            E = getattr(w, end)
            best = None
            for oi in tree.query(Point(tuple(E)).buffer(w.t + tmax)):
                o = walls[oi]
                if o is w or angle_diff(angles[wi], angles[oi]) < 30:
                    continue
                hit = _line_intersection(w.a, w.b - w.a, o.a, o.b - o.a)
                if hit is None:
                    continue
                X, _t, v = hit
                tol = max(w.t, o.t)
                d = float(np.linalg.norm(X - E))
                if d > tol or not (-tol / o.length <= v <= 1 + tol / o.length):
                    continue
                if best is None or d < best[0]:
                    best = (d, X, o, v)
            if best is not None:
                _, X, o, v = best
                other = w.b if end == "a" else w.a
                if np.linalg.norm(other - X) < 0.5 * w.length:
                    continue        # snapping must never collapse a wall onto one point
                setattr(w, end, X.copy())
                setattr(w, "conn_" + end, True)
                # an L corner extends the other wall as well
                if v < 0:
                    o.a = X.copy()
                    o.conn_a = True
                elif v > 1:
                    o.b = X.copy()
                    o.conn_b = True
    # second pass: ends touching another wall's segment count as connected
    lines, tree = _wall_index(walls)
    for wi, w in enumerate(walls):
        for end in ("a", "b"):
            E = Point(tuple(getattr(w, end)))
            for oi in tree.query(E.buffer(tmax)):
                if oi != wi and lines[oi].distance(E) <= max(w.t, walls[oi].t) * 0.6:
                    setattr(w, "conn_" + end, True)
                    break


def _drop_spurs(walls: list[WallPiece], mpu: float) -> list[WallPiece]:
    keep = []
    lines, tree = _wall_index(walls)
    for w in walls:
        if w.length >= 2 * w.t:
            keep.append(w)
            continue
        if w.conn_a and w.conn_b:
            keep.append(w)
            continue
        # a short piece whose body touches another wall is attached material (pilaster, pier)
        body = LineString([tuple(w.a), tuple(w.b)]).buffer(w.t / 2, cap_style="flat")
        if any(o is not w and o.length >= 2 * o.t and
               body.distance(LineString([tuple(o.a), tuple(o.b)]).buffer(o.t / 2, cap_style="flat")) <= 0.02 / mpu
               for o in walls):
            keep.append(w)
            continue
        # a short piece survives when every free end faces a collinear wall within 3 m: it is a
        # jamb or a pier between openings, not a stray fragment
        u = w.u
        n = np.array([-u[1], u[0]])
        free_ends = [e for e, c in ((w.a, w.conn_a), (w.b, w.conn_b)) if not c]

        def continues(end, w=w, n=n):
            for oi in tree.query(Point(tuple(end)).buffer(3.0 / mpu)):
                o = walls[oi]
                if o is w or angle_diff(seg_angle(tuple(w.a), tuple(w.b)), seg_angle(tuple(o.a), tuple(o.b))) > MERGE_ANGLE:
                    continue
                if abs(np.dot(o.a - w.a, n)) > w.t / 2:
                    continue
                if min(np.linalg.norm(o.a - end), np.linalg.norm(o.b - end)) <= 3.0 / mpu:
                    return True
            return False

        if all(continues(e) for e in free_ends):
            keep.append(w)
    return keep


LEARNED_LAYER_MIN_USE = 0.5     # share of a layer's lines that are wall faces


def _detect_core(sheet: Sheet, mpu: float, exclude_boxes: list, allowed_layers: set | None):
    segs = _line_pool(sheet, mpu, exclude_boxes, allowed_layers)
    pieces = _pairs(segs, mpu) if segs else []
    filled, columns, col_members = _filled_and_columns(sheet, mpu, allowed_layers)
    pieces += filled
    used = set().union(*[p.members for p in pieces]) if pieces else set()
    pieces += _thick_lines(sheet, mpu, used)
    pieces += _learned_faces(segs, pieces, mpu)
    p_wall = {s.prim.id: (s.prim.prov.evidence["p_wall"], s.length) for s in segs
              if "p_wall" in s.prim.prov.evidence}
    pieces = _drop_glued(pieces, mpu, p_wall)
    walls = _merge(pieces, mpu)
    _snap_junctions(walls, mpu)
    walls = _drop_spurs(walls, mpu)
    walls = _drop_isolated_clusters(walls, mpu)
    return walls, columns, col_members


def _learned_faces(segs: list[Seg], pieces: list[WallPiece], mpu: float) -> list[WallPiece]:
    """Second pass only: a line the learned classifier calls a wall but that found no partner face
    (partner too short, broken into pieces, or drawn as a single line) still becomes a wall piece,
    centred on the line, at the sheet's dominant paired thickness."""
    if not any("learned_wall" in s.prim.prov.evidence for s in segs):
        return []
    ts = sorted(p.t for p in pieces if p.source == "pairs")
    t = ts[len(ts) // 2] if ts else 0.2 / mpu
    # a line of an object outline (bathtub, lift car, counter) is never a wall face: a classifier
    # call alone does not make it one
    objects = _object_outlines(segs, mpu)
    out = []
    for s in segs:
        if s.covered[1] or s.covered[-1] or s.length < MIN_OVERLAP_M / mpu or s.group in objects:
            continue
        hit = bool(WALL_LAYER_RE.search(s.prim.layer or ""))
        out.append(WallPiece(np.array(s.a, float), np.array(s.b, float), t, {s.prim.id}, 0.0, hit,
                             source="learned_face"))
    return out


def layer_key(p: Primitive) -> str:
    """Layer identity used by layer learning: the layer name. (Stroke colour as a fallback identity
    was measured on FloorPlanCAD: +8 pts wall precision but -7 pts wall recall and -14 pts door
    recall, so it is not used; colour is still kept on primitives as evidence.)"""
    return p.layer or ""


def _learned_wall_layers(sheet: Sheet, walls: list[WallPiece], mpu: float, exclude_boxes: list) -> set | None:
    """Layers whose drawn lines are mostly wall faces. On a wall layer nearly every line ends up as a
    face; on a furniture or fixture layer only the odd edge does. Usage = face length / pool length
    per layer. None when there is nothing to learn (one layer, or every layer qualifies)."""
    pool: dict[str, float] = {}
    for s in _line_pool(sheet, mpu, exclude_boxes):
        pool[layer_key(s.prim)] = pool.get(layer_key(s.prim), 0.0) + s.length
    seg_len_by_prim: dict[str, float] = {}
    for s in _line_pool(sheet, mpu, exclude_boxes):
        seg_len_by_prim[s.prim.id] = seg_len_by_prim.get(s.prim.id, 0.0) + s.length
    layer_of = {p.id: layer_key(p) for p in sheet.primitives}
    used: dict[str, float] = {}
    for m in {m for w in walls for m in w.members}:
        ly = layer_of.get(m, "")
        used[ly] = used.get(ly, 0.0) + seg_len_by_prim.get(m, 0.0)
    if len(pool) < 2:
        return None
    keep = {ly for ly, tot in pool.items() if tot > 0 and used.get(ly, 0.0) / tot >= LEARNED_LAYER_MIN_USE}
    return keep if keep and keep != set(pool) else None


def detect_walls(sheet: Sheet, mpu: float, assumed_scale: bool = False,
                 exclude_boxes: list | None = None) -> tuple[list[Element], list[Element]]:
    """Return (wall elements incl. low-score candidates as cls 'other', column elements)."""
    ids = IdFactory(sheet.id)
    any_wall_layer = any(WALL_LAYER_RE.search(p.layer or "") for p in sheet.primitives)
    walls, columns, col_members = _detect_core(sheet, mpu, exclude_boxes or [], None)
    learned_pass = any("learned_wall" in p.prov.evidence for p in sheet.primitives)
    if not any_wall_layer and not learned_pass:
        # (the learned classifier already reads layer usage; this re-run only applies to rules alone)
        # no layer *names* to trust, but layer *identity* is still evidence: walls live on a few
        # layers; if pass 1 also drew on minor layers (furniture, fixtures), re-run on the wall layers
        learned = _learned_wall_layers(sheet, walls, mpu, exclude_boxes or [])
        if learned:
            walls, columns, col_members = _detect_core(sheet, mpu, exclude_boxes or [], learned)

    elements = []
    conf_mult = 0.7 if assumed_scale else 1.0
    for w in walls:
        L = w.length
        if L <= 0:
            continue
        faces = min(1.0, w.both_faces_len / L) if w.source == "pairs" else 1.0
        layer = (1.0 if w.layer_hit else 0.0) if any_wall_layer else 0.5
        ends = 0.5 * w.conn_a + 0.5 * w.conn_b
        length_f = min(1.0, L * mpu / 1.0)
        score = 0.4 * faces + 0.3 * layer + 0.2 * ends + 0.1 * length_f
        cl = [(round(float(w.a[0]), 4), round(float(w.a[1]), 4)), (round(float(w.b[0]), 4), round(float(w.b[1]), 4))]
        is_wall = score >= MIN_SCORE
        elements.append(Element(
            id=ids("wall" if is_wall else "cand", cl), cls="wall" if is_wall else "other", geom=cl,
            thickness=round(float(w.t), 4), member_ids=sorted(w.members),
            attrs={"candidate": not is_wall, "source": w.source, "thickness_m": round(float(w.t) * mpu, 4),
                   "connected": [w.conn_a, w.conn_b]},
            prov=Prov(source="vector", stage="walls_pairs_v1", confidence=round(score * conf_mult, 3),
                      evidence={"faces_share": round(faces, 3), "layer": layer, "ends": ends}),
        ))
    col_elems = []
    for poly, mem in zip(columns, col_members):
        pts = [(round(x, 4), round(y, 4)) for x, y in list(poly.exterior.coords)[:-1]]
        col_elems.append(Element(id=ids("column", pts), cls="column", geom=pts, member_ids=sorted(mem),
                                 prov=Prov(source="vector", stage="columns_v1", confidence=0.8 * conf_mult)))
    return elements, col_elems


def wall_axis(e: Element) -> tuple[np.ndarray, np.ndarray, float]:
    a, b = np.array(e.geom[0]), np.array(e.geom[1])
    L = float(np.linalg.norm(b - a))
    return a, (b - a) / L if L else np.array([1.0, 0.0]), L


def angle_of(e: Element) -> float:
    return seg_angle(e.geom[0], e.geom[1])


def dist_to_axis(p, e: Element) -> float:
    a, u, _ = wall_axis(e)
    d = np.array(p) - a
    return abs(float(d[0] * u[1] - d[1] * u[0]))


__all__ = ["detect_walls", "wall_axis", "dist_to_axis", "angle_of"]
