"""Per-primitive / per-instance scoring for datasets that label every drawn primitive (FloorPlanCAD,
ArchCAD). Ground truth sits in ``prov.evidence['gt'] = {"semantic": id, "instance": id or -1}``, put
there by the dataset adapter; the pipeline itself never reads it.

- walls: per-primitive precision/recall/F1, by count and by length (symbol-spotting convention);
- doors, windows: per instance - a true instance is found when a predicted element of the class
  contains at least one of its primitives; a predicted element is correct when its primitives
  belong to a true instance of the class.
"""

from __future__ import annotations

from collections import defaultdict

from ...core.geometry import seg_len
from ...schema import BuildingModel

CLASSES = ("wall", "door", "window")


def plength(p) -> float:
    if p.kind in ("line", "polyline", "polygon") and len(p.pts) >= 2:
        pts = p.pts + (p.pts[:1] if p.kind == "polygon" else [])
        return sum(seg_len(a, b) for a, b in zip(pts, pts[1:]))
    if p.kind in ("arc", "circle") and p.radius:
        return p.radius
    return 0.0


def score_model(model: BuildingModel, groups: dict[str, set], learned: bool = False) -> dict:
    """Score one model against the labels on its primitives; ``groups`` maps wall / door / window to
    the dataset's semantic ids."""
    gt = {}
    for p in model.sheet.primitives:
        g = p.prov.evidence.get("gt")
        if g:
            gt[p.id] = g
    # primitives replaced by an arc fit keep their label on the arc
    for p in model.sheet.primitives:
        if p.kind == "arc" and p.prov.stage == "arc_fit":
            labs = [gt[m] for m in p.prov.evidence.get("members", []) if m in gt]
            if labs:
                gt[p.id] = labs[0]
    length = {p.id: plength(p) for p in model.sheet.primitives}
    pred_cls: dict[str, str] = {}
    for e in model.elements:
        if e.cls in CLASSES:
            for m in e.member_ids:
                pred_cls.setdefault(m, e.cls)
    res: dict = {"scale": model.sheet.scale.metres_per_unit, "scale_method": model.sheet.scale.method}

    def tally(is_pred) -> dict:
        w = {"tp": 0, "fp": 0, "fn": 0, "tp_len": 0.0, "fp_len": 0.0, "fn_len": 0.0}
        for pid, L in length.items():
            is_t = gt.get(pid, {}).get("semantic") in groups["wall"]
            is_p = is_pred(pid)
            k = "tp" if is_t and is_p else "fp" if is_p else "fn" if is_t else None
            if k:
                w[k] += 1
                w[k + "_len"] += L
        return w

    res["wall"] = tally(lambda pid: pred_cls.get(pid) == "wall")
    if learned:
        # the classifier's own per-primitive call, before wall pairing rebuilds elements
        ev = {p.id: p.prov.evidence for p in model.sheet.primitives}
        res["wall_direct"] = tally(lambda pid: bool(ev[pid].get("learned_wall")))
    for cls in ("door", "window"):
        inst = defaultdict(set)
        for pid, g in gt.items():
            if g["semantic"] in groups[cls] and g["instance"] not in (-1, None):
                inst[(g["semantic"], g["instance"])].add(pid)
        pred = [set(e.member_ids) for e in model.elements if e.cls == cls and e.member_ids]
        found = sum(1 for prims in inst.values() if any(prims & pr for pr in pred))
        correct = sum(1 for pr in pred if any(gt.get(m, {}).get("semantic") in groups[cls] for m in pr))
        res[cls] = {"true": len(inst), "found": found, "pred": len(pred), "correct": correct}
    return res


def _prf(tp, fp, fn) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def wall_f1(r: dict) -> float:
    w = r["wall"]
    return 2 * w["tp_len"] / (2 * w["tp_len"] + w["fp_len"] + w["fn_len"]) if w["tp_len"] else 0.0


def aggregate(results: list[tuple[str, dict | Exception]], learned: bool) -> tuple[dict, list]:
    """Sum per-drawing results (name, score_model output or the exception it raised); returns the
    metrics and the ten worst drawings by wall F1. A run where every drawing crashed is not a result."""
    crashes = [r for _, r in results if isinstance(r, Exception)]
    if results and len(crashes) == len(results):
        raise RuntimeError(f"all {len(results)} drawings crashed; first: {crashes[0]!r}") from crashes[0]
    agg = {"wall": defaultdict(float), "door": defaultdict(int), "window": defaultdict(int)}
    per, scales = [], []
    for name, r in results:
        if isinstance(r, Exception):
            per.append((0.0, name, f"crash: {r!r}"[:160]))
            continue
        for k, v in r["wall"].items():
            agg["wall"][k] += v
        for c in ("door", "window"):
            for k, v in r[c].items():
                agg[c][k] += v
        for k, v in r.get("wall_direct", {}).items():
            agg.setdefault("wall_direct", defaultdict(float))[k] += v
        if r["scale"]:
            scales.append(r["scale"])
        per.append((round(wall_f1(r), 3), name, {"door": r["door"], "window": r["window"], "scale": r["scale_method"]}))
    W = agg["wall"]
    out = {"files": len(results), "crashed": len(crashes), "method": "rules+learned" if learned else "rules",
           "wall_per_primitive": _prf(W["tp"], W["fp"], W["fn"]),
           "wall_length_weighted": _prf(W["tp_len"], W["fp_len"], W["fn_len"])}
    if "wall_direct" in agg:
        Wd = agg["wall_direct"]
        out["wall_classifier_direct_per_primitive"] = _prf(Wd["tp"], Wd["fp"], Wd["fn"])
        out["wall_classifier_direct_length_weighted"] = _prf(Wd["tp_len"], Wd["fp_len"], Wd["fn_len"])
    for c in ("door", "window"):
        a = agg[c]
        p = a["correct"] / a["pred"] if a["pred"] else 0.0
        r_ = a["found"] / a["true"] if a["true"] else 0.0
        out[f"{c}_instances"] = {"precision": round(p, 4), "recall": round(r_, 4),
                                 "f1": round(2 * p * r_ / (p + r_), 4) if p + r_ else 0.0,
                                 "true": a["true"], "found": a["found"], "pred": a["pred"]}
    out["_scaled"] = len(scales)
    return out, sorted(per, key=lambda x: x[0])[:10]
