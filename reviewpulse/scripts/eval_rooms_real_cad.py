"""How well are rooms recovered on real CAD drawings? (no public CAD dataset labels rooms)

    python scripts/eval_rooms_real_cad.py --dataset archcad --n 60
    python scripts/eval_rooms_real_cad.py --dataset floorplancad --n 30

Reference: rooms built by our own pipeline from the dataset's TRUE wall, door and window lines (the
labels written in as the per-primitive calls, walls rebuilt from those lines only). Scored against
it: rules only, and the default pass (classifier, fused). This measures how much line-level errors
damage rooms - the input of every area, width and route rule. It is not human-drawn room truth:
where our room building itself is wrong, both sides share the error.

Per drawing and in total: reference rooms, predicted rooms, matched (IoU >= 0.5), and the share of
matched rooms whose area is within 5% of the reference (area rules use exact areas).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
AREA_TOL = 0.05


def gt_annotator(groups):
    """Write the dataset's labels as the second pass's per-primitive calls."""
    from reviewpulse.perception.learned.features import CLASSES, labels_from_gt

    def annotate(model):
        ids = [p.id for p in model.sheet.primitives if not p.hidden]
        y = labels_from_gt(model, ids, groups)
        by = {p.id: p for p in model.sheet.primitives}
        for pid, c in zip(ids, y):
            ev = by[pid].prov.evidence
            name = CLASSES[int(c)]
            for k in ("wall", "door", "window"):
                ev[f"p_{k}"] = 1.0 if name == k else 0.0
            ev["learned_wall"] = name == "wall"
            ev["learned_class"] = name
        return len(ids)

    return annotate


def loader(dataset: str):
    data = ROOT / "data"
    if dataset == "archcad":
        from reviewpulse.eval.adapters import archcad as A

        pool = A.names(data, "test")
        step = max(1, len(pool) // 300)
        items = [nm for nm in pool[::step] if A.has_walls(data, nm)]
        return items, (lambda nm: A.load_sheet(data, nm)), A.GROUPS
    from reviewpulse.annotate.text_classify import classify_items
    from reviewpulse.eval.adapters import floorplancad as F
    from reviewpulse.ingest.svg_reader import extract_svg
    from reviewpulse.schema import Scale

    files = sorted((data / "raw" / "floorplancad" / "FloorPlanCAD" / "test").glob("*.svg"))
    files = files[:: max(1, len(files) // 100)][:100]

    def load(f):
        s = extract_svg(f, f.stem)
        classify_items(s.texts)
        s.scale = Scale(metres_per_unit=F.UNIT_M, method="user", confidence=1.0)
        return s

    return files, load, F.GROUPS


def compare(pred_rooms, ref_rooms) -> dict:
    from shapely.geometry import Polygon

    from reviewpulse.eval.matching import match_polygons

    P = [Polygon(r.polygon, r.holes) for r in pred_rooms]
    R = [Polygon(r.polygon, r.holes) for r in ref_rooms]
    mr = match_polygons(P, R, 0.5)
    close = sum(1 for i, j, _ in mr.pairs if abs(P[i].area - R[j].area) <= AREA_TOL * R[j].area)
    return {"tp": mr.tp, "pred": mr.n_pred, "ref": mr.n_true, "area_within_5pct": close}


def main() -> None:
    from reviewpulse.pipeline import build_model

    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["archcad", "floorplancad"], default="archcad")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--out", default=str(ROOT / "reports" / "rooms_real_cad"))
    a = ap.parse_args()
    items, load, groups = loader(a.dataset)
    items = items[: a.n]
    ann = gt_annotator(groups)
    tot = {k: {"tp": 0, "pred": 0, "ref": 0, "area_within_5pct": 0} for k in ("rules", "default")}
    rows, t0 = [], time.time()
    for it in items:
        name = getattr(it, "name", it)
        try:
            ref = build_model(load(it), learned=True, annotator=ann, learned_mode="rebuild")
            res = {"rules": compare(build_model(load(it), learned=False).rooms, ref.rooms),
                   "default": compare(build_model(load(it), learned=True, learned_mode="fuse").rooms, ref.rooms)}
        except Exception as e:  # noqa: BLE001 - a crash is a result
            rows.append({"item": name, "crash": repr(e)[:160]})
            print(name, "crash", repr(e)[:120], flush=True)
            continue
        for k, v in res.items():
            for m, x in v.items():
                tot[k][m] += x
        rows.append({"item": name, **res})
        print(name, json.dumps(res), flush=True)

    def summary(v):
        p = v["tp"] / v["pred"] if v["pred"] else 0.0
        r = v["tp"] / v["ref"] if v["ref"] else 0.0
        return {**v, "precision": round(p, 4), "recall": round(r, 4),
                "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
                "matched_area_within_5pct": round(v["area_within_5pct"] / v["tp"], 4) if v["tp"] else 0.0}

    out = {"dataset": a.dataset, "drawings": len(items), "crashes": sum("crash" in r for r in rows),
           "reference": "rooms from the dataset's true wall/door/window lines (our room building)",
           "seconds": round(time.time() - t0), **{k: summary(v) for k, v in tot.items()}}
    d = Path(a.out)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{a.dataset}.json").write_text(json.dumps({"summary": out, "per_drawing": rows}, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
