"""Raster path evaluation on CubiCasa5K (R13 done-when).

On the rendered split (scripts/prepare_cubicasa_seg.py, longest side 1024 px) and for each method
(rules, model, fusion, model_scan):
- walls: pixel precision / recall / F1 with a 3 px tolerance (dilated masks), and IoU;
- doors, windows: instance precision / recall (connected components, IoU >= 0.5 and >= 0.3);
- rooms: R10 from the predicted barrier, matched to the SVG room polygons at IoU 0.5; plus the
  oracle run (true walls + openings as barrier) to separate R10 errors from segmentation errors.
``model_scan`` runs the pipeline's own entry (predict_refined) on the full-resolution scan, so the
wall-thickness rescaling is tested too; its class map is resized to the render for scoring.
Room truth merges spaces that touch without a wall between them (open plan), as for ResPlan.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from ..schema import Sheet
from .matching import match_polygons

DATA = Path(__file__).resolve().parents[3] / "data"


def _tol_prf(pred: np.ndarray, true: np.ndarray, tol: int = 3) -> tuple[int, int, int, int]:
    from scipy import ndimage

    st = np.ones((2 * tol + 1, 2 * tol + 1), bool)
    td = ndimage.binary_dilation(true, st)
    pd = ndimage.binary_dilation(pred, st)
    return int((pred & td).sum()), int(pred.sum()), int((true & pd).sum()), int(true.sum())


def _instances(mask: np.ndarray, min_px: int = 8) -> list[np.ndarray]:
    from scipy import ndimage

    lab, n = ndimage.label(mask)
    return [lab == k for k in range(1, n + 1) if (lab == k).sum() >= min_px]


def _inst_match(pred: list[np.ndarray], true: list[np.ndarray], thr: float) -> int:
    from scipy.optimize import linear_sum_assignment

    if not pred or not true:
        return 0
    cost = np.ones((len(pred), len(true)))
    for i, p in enumerate(pred):
        for j, t in enumerate(true):
            inter = (p & t).sum()
            if inter:
                cost[i, j] = 1 - inter / (p | t).sum()
    r, c = linear_sum_assignment(cost)
    return int(sum(1 - cost[i, j] >= thr for i, j in zip(r, c)))


def _rect_match(pred_mask: np.ndarray, true_mask: np.ndarray) -> tuple[int, tuple[int, int]]:
    """(rectangles matching a true instance at IoU >= 0.5, (rectangles, oversized rectangles)).
    Oversized: the rectangle covers more than twice the true opening it overlaps most (or any
    rectangle 3x its own blob when it overlaps none)."""
    from scipy.optimize import linear_sum_assignment
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import unary_union

    from ..perception.raster.vectorize import opening_parts

    rects = [r for _y, _x, r in opening_parts(pred_mask)]
    truths = []
    for t in _instances(true_mask):
        ys, xs = np.nonzero(t)
        truths.append(unary_union(MultiPolygon([Polygon([(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)])
                                                for x, y in zip(xs, ys)]).geoms))
    if not rects:
        return 0, (0, 0)
    over = 0
    cost = np.ones((len(rects), max(len(truths), 1)))
    for i, r in enumerate(rects):
        best = None
        for j, t in enumerate(truths):
            inter = r.intersection(t).area
            if inter:
                cost[i, j] = 1 - inter / r.union(t).area
                if best is None or inter > best[0]:
                    best = (inter, t.area)
        if best and r.area > 2 * best[1]:
            over += 1
    if not truths:
        return 0, (len(rects), over)
    ri, ci = linear_sum_assignment(cost)
    return int(sum(1 - cost[i, j] >= 0.5 for i, j in zip(ri, ci))), (len(rects), over)


def _rooms_from_masks(wall, door, window, mpu):
    from ..perception.raster.vectorize import barrier_from_masks, opening_elements
    from ..perception.rooms import detect_rooms

    affine = [1.0, 0.0, 0.0, 0.0, -1.0, float(wall.shape[0])]       # px -> y-up units
    sheet = Sheet(id="cc", source_file="cc", mode="raster", coord_unit="paper_mm", width=wall.shape[1],
                  height=wall.shape[0])
    ops = opening_elements(door, "door", None, affine, "cc", mpu, "eval") + \
        opening_elements(window, "window", None, affine, "cc", mpu, "eval")
    barrier = barrier_from_masks(wall, door, window, affine)
    rooms, _e, _w = detect_rooms(sheet, [], [], ops, mpu, True, barrier=barrier)
    return rooms


def _truth_spaces(plan, scale: float, H: int, mpu: float):
    """Room polygons of the SVG in render pixels (y up), open-plan neighbours merged."""
    from shapely.affinity import affine_transform
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from .adapters.cubicasa import masks

    polys = []
    for rtype, pts in plan.rooms:
        if rtype == "terrace":
            continue
        p = Polygon(pts * scale).buffer(0)
        if p.area * mpu * mpu >= 1.0:
            polys.append(affine_transform(p, [1, 0, 0, -1, 0, H]))
    walls = _wall_geom(masks(plan, scale) > 0, H)
    parent = list(range(len(polys)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    eps = 2.0
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            shared = polys[i].buffer(eps).intersection(polys[j].buffer(eps))
            if not shared.is_empty and shared.difference(walls.buffer(eps)).area > 8 * eps:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(polys)):
        groups[find(i)].append(polys[i])
    return [unary_union(g).buffer(0) for g in groups.values()]


def _wall_geom(wall_px: np.ndarray, H: int):
    from shapely.affinity import affine_transform

    from ..perception.raster.vectorize import mask_polygons

    g = mask_polygons(wall_px)
    return affine_transform(g, [1, 0, 0, -1, 0, H]) if not g.is_empty else g


def run(n: int = 100, methods=("rules", "model", "fusion"), split: str = "test",
        names: set[str] | None = None) -> tuple[dict, list]:
    """``names``: score only these plans (``<folder parent>_<folder>``) of the evenly spread n."""
    from shapely.geometry import Polygon

    from ..ingest.raster_prep import binarise
    from ..perception.raster.build import fuse
    from ..perception.raster.rules import close_doorways, wall_mask_rules
    from ..perception.raster.segment import model_available, predict, predict_refined
    from .adapters.cubicasa import parse, split_ids

    folders = split_ids(DATA, split)
    step = max(1, len(folders) // n)
    folders = folders[::step][:n]
    if names is not None:
        folders = [f for f in folders if f"{f.parent.name}_{f.name}" in names]
    if not model_available():
        methods = tuple(m for m in methods if m == "rules")
    agg: dict = defaultdict(lambda: defaultdict(int))
    per = []
    proc = DATA / "processed" / "cubicasa_seg" / split
    for f in folders:
        name = f"{f.parent.name}_{f.name}"
        ip = proc / f"{name}.png"
        if not ip.exists():
            continue
        gray = np.asarray(Image.open(ip).convert("L"))
        true = np.asarray(Image.open(proc / f"{name}_mask.png"))
        plan = parse(f)
        scale = gray.shape[1] / plan.size[0]
        H = gray.shape[0]
        from ..perception.raster.segment import estimate_wall_thickness_px

        t_true = estimate_wall_thickness_px(true == 1) or 6.0
        mpu = 0.2 / t_true                       # walls ~0.20 m: room size filter and probe distances
        spaces = _truth_spaces(plan, scale, H, mpu)
        binary = binarise(gray)
        rule_wall, t_rule = wall_mask_rules(binary, gray=gray)
        preds = {}
        if "rules" in methods:
            preds["rules"] = (rule_wall, np.zeros_like(rule_wall), np.zeros_like(rule_wall))
            rule_barrier = close_doorways(rule_wall, t_rule)
        if "model_scan" in methods:
            scan = np.asarray(Image.open(f / "F1_scaled.png").convert("L"))
            _p, cs, _s, _t = predict_refined(scan, binarise(scan))
            cs = np.asarray(Image.fromarray(cs).resize(gray.shape[::-1], Image.NEAREST))
            preds["model_scan"] = (cs == 1, cs == 2, cs == 3)
        if any(m in methods for m in ("model", "fusion")):
            _p, cls, _s = predict(gray, None)        # same resolution as training: no rescale
            if "model" in methods:
                preds["model"] = (cls == 1, cls == 2, cls == 3)
            if "fusion" in methods:
                preds["fusion"] = (fuse(cls == 1, rule_wall & (cls != 2) & (cls != 3)), cls == 2, cls == 3)
        preds["oracle"] = (true == 1, true == 2, true == 3)
        row = {}
        for m, (w, d, wi) in preds.items():
            A = agg[m]
            if m != "oracle":
                tp_p, n_p, tp_t, n_t = _tol_prf(w, true == 1)
                A["w_tp_p"] += tp_p
                A["w_np"] += n_p
                A["w_tp_t"] += tp_t
                A["w_nt"] += n_t
                A["w_inter"] += int((w & (true == 1)).sum())
                A["w_union"] += int((w | (true == 1)).sum())
                for cname, pm, tm in (("door", d, true == 2), ("window", wi, true == 3)):
                    pi, ti = _instances(pm), _instances(tm)
                    A[f"{cname}_pred"] += len(pi)
                    A[f"{cname}_true"] += len(ti)
                    A[f"{cname}_tp50"] += _inst_match(pi, ti, 0.5)
                    A[f"{cname}_tp30"] += _inst_match(pi, ti, 0.3)
                    # the rectangles the pipeline builds from the blobs (what rooms and reports use)
                    rp, rt = _rect_match(pm, tm)
                    A[f"{cname}_rect_tp50"] += rp
                    A[f"{cname}_rect_pred"] += rt[0]
                    A[f"{cname}_rect_oversized"] += rt[1]
            rooms = _rooms_from_masks(rule_barrier if m == "rules" else w, d, wi, mpu)
            mr = match_polygons([Polygon(r.polygon, r.holes) for r in rooms], spaces, 0.5)
            A["room_tp"] += mr.tp
            A["room_pred"] += mr.n_pred
            A["room_true"] += mr.n_true
            row[m] = (mr.tp, mr.n_pred, mr.n_true)
        per.append((row.get("fusion", row.get("rules")), name))

    def prf(tp_p, n_p, tp_t, n_t):
        p = tp_p / n_p if n_p else 0.0
        r = tp_t / n_t if n_t else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}

    res = {"plans": len(per), "split": split}
    for m, A in agg.items():
        out = {}
        if m != "oracle":
            out["walls_3px"] = prf(A["w_tp_p"], A["w_np"], A["w_tp_t"], A["w_nt"])
            out["walls_iou"] = round(A["w_inter"] / max(A["w_union"], 1), 4)
            for c in ("door", "window"):
                out[f"{c}_iou50"] = prf(A[f"{c}_tp50"], A[f"{c}_pred"], A[f"{c}_tp50"], A[f"{c}_true"])
                out[f"{c}_iou30"] = prf(A[f"{c}_tp30"], A[f"{c}_pred"], A[f"{c}_tp30"], A[f"{c}_true"])
                out[f"{c}_rect_iou50"] = prf(A[f"{c}_rect_tp50"], A[f"{c}_rect_pred"], A[f"{c}_rect_tp50"], A[f"{c}_true"])
                out[f"{c}_rect_oversized"] = A[f"{c}_rect_oversized"]
        out["rooms_iou50"] = prf(A["room_tp"], A["room_pred"], A["room_tp"], A["room_true"])
        res[m] = out
    return res, sorted([p for p in per if p[0]], key=lambda x: (x[0][0] / max(x[0][2], 1)))[:10]
