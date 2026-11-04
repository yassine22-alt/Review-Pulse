"""Perception scoring on randomised plans (generality test), DXF or PDF input.

Predictions are mapped back to metres with the exact transform stored in the
truth file (DXF units, or the PDF paper transform), then scored:
walls (length-weighted P/R), doors / windows / openings (IoU >= 0.5 on the
footprint buffered by 2 cm), rooms (IoU >= 0.5) and door edges.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from shapely import affinity
from shapely.geometry import LineString, Polygon

from .matching import length_coverage, match_polygons, prf


def sheet_to_metres(truth: dict, fmt: str):
    if fmt == "dxf":
        k = truth.get("dxf_unit_m", 1.0)
        return [k, 0, 0, k, 0, 0]
    tr = truth["pdf_transform"]
    k = 1.0 / tr["k"]
    return [k, 0, 0, k, -tr["ox"] * k, -tr["oy"] * k]


def score_plan(path_by_fmt: dict, truth: dict, fmt: str) -> dict:
    from .cli import _model_from

    m = _model_from(path_by_fmt[fmt])
    M = sheet_to_metres(truth, fmt)

    def tf(g):
        return affinity.affine_transform(g, M)

    unit_m = M[0]
    res = {"config": truth.get("config", {}), "scale_method": m.sheet.scale.method,
           "scale": m.sheet.scale.metres_per_unit}
    # walls
    pred_w = [(tf(LineString(e.geom)), (e.thickness or 0) * unit_m) for e in m.elements if e.cls == "wall"]
    true_w = [(LineString(w["centreline"]), w["thickness"]) for w in truth["walls"]]
    p, r = length_coverage(pred_w, true_w, tol=0.05)
    res["walls"] = (p, r)
    # openings per class
    for cls in ("door", "window", "opening"):
        pp = [tf(Polygon(e.geom)).buffer(0.02) for e in m.elements if e.cls == cls]
        tt = [Polygon(o["polygon"]).buffer(0.02) for o in truth["openings"] if o["cls"] == cls]
        mr = match_polygons(pp, tt, 0.5)
        res[cls] = (mr.tp, mr.n_pred, mr.n_true)
    # rooms and door edges
    tr_names = [r_["id"] for r_ in truth["rooms"]]
    tr_polys = [Polygon(r_["polygon"]) for r_ in truth["rooms"]]
    mr = match_polygons([tf(Polygon(r_.polygon)) for r_ in m.rooms], tr_polys, 0.5)
    res["rooms"] = (mr.tp, mr.n_pred, mr.n_true)
    p2t = {m.rooms[i].id: tr_names[j] for i, j in mr.pred_to_true().items()}
    pe = {(frozenset((p2t.get(e.a, e.a), p2t.get(e.b, e.b))), e.kind) for e in m.edges if e.kind in ("door", "opening")}
    te = {(frozenset((e["a"], e["b"])), e["kind"]) for e in truth["edges"] if e["kind"] in ("door", "opening")}
    res["edges"] = (len(pe & te), len(pe), len(te))
    # room labels -> type
    t_types = {r_["id"]: r_["type"] for r_ in truth["rooms"]}
    ok = sum(1 for rid, tname in p2t.items()
             if next((r_.type for r_ in m.rooms if r_.id == rid), None) == t_types[tname])
    res["room_types"] = (ok, len(p2t))
    return res


def run_random_eval(n: int, fmt: str, out_dir: Path, seed0: int = 5000) -> tuple[dict, list]:
    import tempfile

    from ..synth.random_plan import random_plan

    agg = defaultdict(lambda: [0, 0, 0])
    wall_p = wall_r = 0.0
    by_style = defaultdict(list)
    worst = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            paths = random_plan(td, seed=seed0 + i)
            import json

            truth = json.loads(Path(paths["truth"]).read_text(encoding="utf-8"))
            try:
                res = score_plan(paths, truth, fmt)
            except Exception as e:  # noqa: BLE001 - a crash is a result too
                worst.append((0.0, truth["name"], f"crash: {e!r}"))
                continue
            wall_p += res["walls"][0]
            wall_r += res["walls"][1]
            for k in ("door", "window", "opening", "rooms", "edges", "room_types"):
                a = res[k]
                for j in range(len(a)):
                    agg[k][j] += a[j]
            rf = _f(res["rooms"])
            ef = _f(res["edges"])
            cfg = res["config"]
            for key in ("scheme", "wall_style", "door_style", "units"):
                by_style[f"{key}={cfg.get(key)}"].append(min(rf, ef))
            worst.append((min(rf, ef, prf(*res["walls"])), truth["name"],
                          {k: cfg.get(k) for k in ("scheme", "wall_style", "door_style", "angle", "units")},
                          {k: res[k] for k in ("door", "window", "opening", "rooms", "edges")}))
    out = {"n": n, "format": fmt,
           "walls": {"precision": wall_p / n, "recall": wall_r / n, "f1": prf(wall_p / n, wall_r / n)}}
    for k in ("door", "window", "opening", "rooms", "edges"):
        tp, npred, ntrue = agg[k]
        pr = tp / npred if npred else 1.0
        rc = tp / ntrue if ntrue else 1.0
        out[k] = {"precision": pr, "recall": rc, "f1": prf(pr, rc), "tp": tp, "pred": npred, "true": ntrue}
    out["room_type_accuracy"] = agg["room_types"][0] / agg["room_types"][1] if agg["room_types"][1] else 0.0
    out["min(room F1, edge F1) by style"] = {k: sum(v) / len(v) for k, v in sorted(by_style.items())}
    return out, sorted(worst, key=lambda x: x[0])[:10]


def _f(t):
    tp, npred, ntrue = t
    p = tp / npred if npred else 1.0
    r = tp / ntrue if ntrue else 1.0
    return prf(p, r)
