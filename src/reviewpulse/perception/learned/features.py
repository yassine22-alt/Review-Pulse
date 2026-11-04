"""Per-primitive features for the learned primitive classifier (D8 head-to-head with the rules).

Every feature is identity-free (no layer or colour *names*), in metres where it is a length, and
computed from the drawing itself plus the rule pipeline's own conclusions, so a model trained on one
dataset can be applied to any vector drawing.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np

from ...schema import BuildingModel, Primitive

KINDS = ("line", "polyline", "polygon", "arc", "circle")
CLASSES = ("other", "wall", "door", "window")

FEATURES = (
    ["kind_" + k for k in KINDS]
    + ["length_m", "log_length", "orient_dev", "axis_aligned", "width_mm", "filled", "dashed",
       "arc_sweep", "arc_radius_m",
       "colour_share", "colour_rank", "colour_is_top", "layer_share", "layer_rank",
       "n_parallel", "par_d1_m", "par_d2_m", "par_overlap1", "n_parallel_long",
       "end_deg_min", "end_deg_max", "n_touch_perp", "n_crossings", "density_1m",
       "border_dist_rel",
       "tag_pattern", "tag_glazing", "tag_dim", "tag_door_leaf", "tag_hidden",
       "rule_wall", "rule_wall_thick_m", "rule_wall_conf", "rule_door", "rule_window", "rule_opening",
       "rule_column", "rule_candidate"]
    # text around the primitive (text is a primitive type in recent symbol-spotting work): a door tag
    # or a dimension text next to a line says what the line is. Zero where a drawing has no text.
    + ["txt_dist_m", "txt_dim_1m", "txt_tag_1m", "txt_label_2m", "txt_note_1m", "txt_inside"]
)
TEXT_FAR_M = 5.0


def _segments(p: Primitive) -> list[tuple]:
    if p.kind in ("line", "polyline") and len(p.pts) >= 2:
        return list(zip(p.pts, p.pts[1:]))
    if p.kind == "polygon" and len(p.pts) >= 3:
        return list(zip(p.pts, p.pts[1:] + p.pts[:1]))
    return []


def _length(p: Primitive) -> float:
    segs = _segments(p)
    if segs:
        return sum(math.dist(a, b) for a, b in segs)
    if p.kind == "arc" and p.radius:
        sw = (p.a1 - p.a0) % 360 or 360
        return math.radians(sw) * p.radius
    if p.kind == "circle" and p.radius:
        return 2 * math.pi * p.radius
    return 0.0


def _rank_share(values: list, weights: list[float]) -> tuple[dict, dict]:
    tot: Counter = Counter()
    for v, w in zip(values, weights):
        tot[v] += w
    total = sum(tot.values()) or 1.0
    share = {k: v / total for k, v in tot.items()}
    rank = {k: i for i, (k, _v) in enumerate(tot.most_common())}
    return share, rank


def _text_context(texts, geoms, mpu: float) -> dict[str, np.ndarray]:
    """Per representative segment: distance to the nearest text box (capped), counts of nearby texts
    by kind, and whether the segment lies inside a text box (underlines, text frames)."""
    import shapely
    from shapely.strtree import STRtree

    n = len(geoms)
    out = {"txt_dist_m": np.full(n, TEXT_FAR_M), "txt_dim_1m": np.zeros(n), "txt_tag_1m": np.zeros(n),
           "txt_label_2m": np.zeros(n), "txt_note_1m": np.zeros(n), "txt_inside": np.zeros(n)}
    items = [t for t in texts if t.text.strip() and not t.prov.evidence.get("in_table")]
    if not items or not n:
        return out
    boxes = shapely.box(*np.array([t.bbox for t in items], float).T)
    tree = STRtree(boxes)
    gi, ti = tree.query_nearest(geoms, return_distance=False, all_matches=False)
    d = shapely.distance(geoms[gi], boxes[ti]) * mpu
    out["txt_dist_m"][gi] = np.minimum(d, TEXT_FAR_M)
    kinds = np.array([t.kind for t in items])
    for name, kind_set, reach in (("txt_dim_1m", {"dimension"}, 1.0), ("txt_tag_1m", {"tag"}, 1.0),
                                  ("txt_label_2m", {"room_label", "area"}, 2.0), ("txt_note_1m", {"note"}, 1.0)):
        a, b = tree.query(geoms, predicate="dwithin", distance=reach / mpu)
        hit = np.isin(kinds[b], list(kind_set))
        np.add.at(out[name], a[hit], 1)
    a, b = tree.query(geoms, predicate="within")
    out["txt_inside"][a] = 1
    return out


def sheet_features(model: BuildingModel) -> tuple[list[str], np.ndarray]:
    """(primitive ids, feature matrix) for every visible primitive of the model's sheet."""
    import shapely
    from shapely.strtree import STRtree

    sheet = model.sheet
    mpu = sheet.scale.metres_per_unit or 0.1
    prims = [p for p in sheet.primitives if not p.hidden or p.prov.stage == "arc_fit"]
    prims = [p for p in prims if p.kind in KINDS]
    if not prims:
        return [], np.zeros((0, len(FEATURES)))
    lengths = [_length(p) for p in prims]
    col_share, col_rank = _rank_share([p.color or "" for p in prims], lengths)
    lay_share, lay_rank = _rank_share([p.layer or "" for p in prims], lengths)

    # dominant orientation (length-weighted, modulo 90 deg)
    angs, wts = [], []
    for p in prims:
        for a, b in _segments(p):
            L = math.dist(a, b)
            if L > 0:
                angs.append(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90.0)
                wts.append(L)
    hist, edges = np.histogram(angs or [0.0], bins=90, range=(0, 90), weights=wts or [1.0])
    dom = float(edges[int(np.argmax(hist))] + 0.5)

    # representative straight segment per primitive (longest), for neighbour statistics
    rep = []
    for p in prims:
        segs = _segments(p)
        if segs:
            a, b = max(segs, key=lambda s: math.dist(*s))
        elif p.center and p.radius:
            a, b = (p.center[0] - p.radius, p.center[1]), (p.center[0] + p.radius, p.center[1])
        else:
            a, b = (0.0, 0.0), (0.0, 0.0)
        rep.append((a, b))
    P = np.array([r[0] for r in rep], float)
    Q = np.array([r[1] for r in rep], float)
    D = Q - P
    L = np.hypot(D[:, 0], D[:, 1])
    U = D / np.where(L > 0, L, 1.0)[:, None]
    N = np.stack([-U[:, 1], U[:, 0]], axis=1)
    geoms = shapely.linestrings(np.stack([P, Q], axis=1))
    tree = STRtree(geoms)
    reach = 0.6 / mpu
    lo, hi = np.minimum(P, Q) - reach, np.maximum(P, Q) + reach
    ii, jj = tree.query(shapely.box(lo[:, 0], lo[:, 1], hi[:, 0], hi[:, 1]))
    keep = (ii != jj) & (L[ii] > 0) & (L[jj] > 0)
    ii, jj = ii[keep], jj[keep]
    cosang = np.abs(np.einsum("ij,ij->i", U[ii], U[jj]))
    par = cosang >= math.cos(math.radians(3))
    perp = cosang <= math.cos(math.radians(60))
    off = np.abs(np.einsum("ij,ij->i", (P[jj] + Q[jj]) / 2 - P[ii], N[ii]))
    s_p = np.einsum("ij,ij->i", P[jj] - P[ii], U[ii])
    s_q = np.einsum("ij,ij->i", Q[jj] - P[ii], U[ii])
    ov = np.minimum(L[ii], np.maximum(s_p, s_q)) - np.maximum(0.0, np.minimum(s_p, s_q))
    ovr = ov / np.where(L[ii] > 0, L[ii], 1.0)
    cand = par & (off * mpu >= 0.03) & (off * mpu <= 0.6) & (ovr > 0.3)

    n_par = np.bincount(ii[cand], minlength=len(prims))
    n_par_long = np.bincount(ii[cand & (ovr > 0.8)], minlength=len(prims))
    par_d = [[] for _ in prims]
    par_ov1 = np.zeros(len(prims))
    for i, o, r in zip(ii[cand].tolist(), off[cand].tolist(), ovr[cand].tolist()):
        par_d[i].append((o * mpu, r))
    for i, ds in enumerate(par_d):
        ds.sort()
        par_d[i] = ds
        if ds:
            par_ov1[i] = ds[0][1]
    # endpoint degrees and perpendicular touches
    tol = 0.01 / mpu
    ends: Counter = Counter()
    for a, b in rep:
        for q in (a, b):
            ends[(round(q[0] / tol), round(q[1] / tol))] += 1
    touch_perp = np.zeros(len(prims))
    near_perp = perp & (np.minimum.reduce([
        np.hypot(*(P[jj] - P[ii]).T), np.hypot(*(Q[jj] - P[ii]).T),
        np.hypot(*(P[jj] - Q[ii]).T), np.hypot(*(Q[jj] - Q[ii]).T)]) <= 0.05 / mpu)
    np.add.at(touch_perp, ii[near_perp], 1)
    cr_i, cr_j = tree.query(geoms, predicate="crosses")
    crossings = np.bincount(cr_i[cr_i != cr_j], minlength=len(prims))
    dens = np.bincount(ii[off * mpu <= 1.0], minlength=len(prims))

    xs = np.concatenate([P[:, 0], Q[:, 0]])
    ys = np.concatenate([P[:, 1], Q[:, 1]])
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    span = max(bx1 - bx0, by1 - by0, 1e-9)

    txt = _text_context(sheet.texts, geoms, mpu)

    rule = {}
    for e in model.elements:
        for m in e.member_ids:
            rule.setdefault(m, []).append(e)

    X = np.zeros((len(prims), len(FEATURES)), dtype=np.float32)
    col = {f: k for k, f in enumerate(FEATURES)}
    for i, p in enumerate(prims):
        r = X[i]
        r[col["kind_" + p.kind]] = 1
        r[col["length_m"]] = lengths[i] * mpu
        r[col["log_length"]] = math.log1p(lengths[i] * mpu * 100)
        a = math.degrees(math.atan2(D[i, 1], D[i, 0])) % 90.0 if L[i] > 0 else 0.0
        dev = abs(((a - dom) + 45) % 90 - 45)
        r[col["orient_dev"]] = dev
        r[col["axis_aligned"]] = float(dev < 1.0)
        r[col["width_mm"]] = p.width or 0.0
        r[col["filled"]] = float(p.filled)
        r[col["dashed"]] = float(p.dashed)
        if p.kind == "arc":
            r[col["arc_sweep"]] = (p.a1 - p.a0) % 360 or 360
            r[col["arc_radius_m"]] = (p.radius or 0) * mpu
        if p.kind == "circle":
            r[col["arc_sweep"]] = 360
            r[col["arc_radius_m"]] = (p.radius or 0) * mpu
        r[col["colour_share"]] = col_share.get(p.color or "", 0.0)
        r[col["colour_rank"]] = min(col_rank.get(p.color or "", 9), 9)
        r[col["colour_is_top"]] = float(col_rank.get(p.color or "", 9) == 0)
        r[col["layer_share"]] = lay_share.get(p.layer or "", 0.0)
        r[col["layer_rank"]] = min(lay_rank.get(p.layer or "", 9), 9)
        r[col["n_parallel"]] = n_par[i]
        r[col["n_parallel_long"]] = n_par_long[i]
        r[col["par_d1_m"]] = par_d[i][0][0] if par_d[i] else 1.0
        r[col["par_d2_m"]] = par_d[i][1][0] if len(par_d[i]) > 1 else 1.0
        r[col["par_overlap1"]] = par_ov1[i]
        a_, b_ = rep[i]
        dg = [ends[(round(q[0] / tol), round(q[1] / tol))] - 1 for q in (a_, b_)]
        r[col["end_deg_min"]], r[col["end_deg_max"]] = min(dg), max(dg)
        r[col["n_touch_perp"]] = touch_perp[i]
        r[col["n_crossings"]] = crossings[i]
        r[col["density_1m"]] = dens[i]
        cx, cy = (a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2
        r[col["border_dist_rel"]] = min(cx - bx0, bx1 - cx, cy - by0, by1 - cy) / span
        ev = p.prov.evidence
        r[col["tag_pattern"]] = float(bool(ev.get("pattern")))
        r[col["tag_glazing"]] = float(bool(ev.get("glazing")))
        r[col["tag_dim"]] = float(bool(ev.get("dim_graphic")))
        r[col["tag_door_leaf"]] = float(bool(ev.get("door_leaf")))
        r[col["tag_hidden"]] = float(p.hidden)
        for name, v in txt.items():
            r[col[name]] = v[i]
        for e in rule.get(p.id, []):
            if e.cls == "wall":
                r[col["rule_wall"]] = 1
                r[col["rule_wall_thick_m"]] = (e.thickness or 0) * mpu
                r[col["rule_wall_conf"]] = e.prov.confidence
            elif e.cls in ("door", "window", "opening", "column"):
                r[col["rule_" + e.cls]] = 1
            elif e.cls == "other":
                r[col["rule_candidate"]] = 1
    return [p.id for p in prims], X


def labels_from_gt(model: BuildingModel, ids: list[str], groups: dict[str, set]) -> np.ndarray:
    """FloorPlanCAD-style ground truth (evidence['gt']['semantic']) -> class indices of CLASSES."""
    by_id = {p.id: p for p in model.sheet.primitives}
    gt_of = {}
    for p in model.sheet.primitives:
        g = p.prov.evidence.get("gt")
        if g:
            gt_of[p.id] = g["semantic"]
        if p.prov.stage == "arc_fit":
            for m in p.prov.evidence.get("members", []):
                g = by_id.get(m) and by_id[m].prov.evidence.get("gt")
                if g:
                    gt_of[p.id] = g["semantic"]
                    break
    y = np.zeros(len(ids), dtype=np.int32)
    for k, pid in enumerate(ids):
        s = gt_of.get(pid)
        for ci, name in enumerate(CLASSES):
            if name in groups and s in groups[name]:
                y[k] = ci
    return y
