"""Baseline 0 (A1): score the original pipeline's captures with ReviewPulse's own metrics.

Runs in the ReviewPulse venv (reads what scripts/baseline_run.py wrote; no TensorFlow needed):

    python scripts/baseline_score.py cubicasa --runs runs/baseline/out_cubicasa
    python scripts/baseline_score.py synth    --runs runs/baseline/out_synth
    python scripts/baseline_score.py rp-synth            # ReviewPulse on the same synthetic inputs

``cubicasa`` uses the scoring of eval/raster_eval.py unchanged (walls F1 at 3 px and IoU, door /
window instances at IoU 0.5 and 0.3, rooms matched at IoU 0.5 against the open-plan-merged truth).
``synth`` checks the planted errors the original's four rules can express (room too small, room
without a door) on the room that contains the planted room, and counts its violations on clean plans.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
# which original violation type expresses which planted error (the other planted errors have no
# counterpart among the original's four rules)
PLANTED_TO_OLD = {"metric_room_small": "MIN_ROOM_AREA", "topo_isolated_room": "ROOM_WITHOUT_DOOR"}


def _polys(geoms: list):
    from shapely.geometry import shape

    out = []
    for g in geoms:
        s = shape(g)
        if s.geom_type == "Polygon" and s.area > 0:
            out.append(s)
        elif s.geom_type == "MultiPolygon":
            out += [p for p in s.geoms if p.area > 0]
    return out


def _list_names(inputs: Path) -> set[str]:
    return {Path(x.strip()).stem for x in inputs.read_text(encoding="utf-8").splitlines() if x.strip()}


def score_cubicasa(runs: Path, inputs: Path) -> dict:
    from shapely.affinity import affine_transform

    from reviewpulse.eval.adapters.cubicasa import parse, split_ids
    from reviewpulse.eval.matching import match_polygons
    from reviewpulse.eval.raster_eval import _inst_match, _instances, _tol_prf, _truth_spaces
    from reviewpulse.perception.raster.segment import estimate_wall_thickness_px

    folders = split_ids(DATA, "test")
    folders = folders[:: max(1, len(folders) // 100)][:100]
    names = _list_names(inputs)
    folders = [f for f in folders if f"{f.parent.name}_{f.name}" in names]
    proc = DATA / "processed" / "cubicasa_seg" / "test"
    A: Counter = Counter()
    crashes: Counter = Counter()
    secs, n_ok = [], 0
    for f in folders:
        name = f"{f.parent.name}_{f.name}"
        cap_p = runs / f"{name}_png" / "capture.json"
        if not cap_p.exists():
            crashes["not run"] += 1
            continue
        cap = json.loads(cap_p.read_text(encoding="utf-8"))
        secs.append(cap["seconds"])
        if cap["exit_code"] != 0:
            crashes[cap["message"].splitlines()[-1][:120] if cap["message"] else f"exit {cap['exit_code']}"] += 1
            continue
        n_ok += 1
        true = np.asarray(Image.open(proc / f"{name}_mask.png"))
        m = np.load(runs / f"{name}_png" / "capture.npz")
        w, d, wi = m["walls"], m["doors"], m["windows"]
        tp_p, n_p, tp_t, n_t = _tol_prf(w, true == 1)
        A["w_tp_p"] += tp_p
        A["w_np"] += n_p
        A["w_tp_t"] += tp_t
        A["w_nt"] += n_t
        A["w_inter"] += int((w & (true == 1)).sum())
        A["w_union"] += int((w | (true == 1)).sum())
        for c, pm, tm in (("door", d, true == 2), ("window", wi, true == 3)):
            pi, ti = _instances(pm), _instances(tm)
            A[f"{c}_pred"] += len(pi)
            A[f"{c}_true"] += len(ti)
            A[f"{c}_tp50"] += _inst_match(pi, ti, 0.5)
            A[f"{c}_tp30"] += _inst_match(pi, ti, 0.3)
        plan = parse(f)
        H = true.shape[0]
        scale = true.shape[1] / plan.size[0]
        t_true = estimate_wall_thickness_px(true == 1) or 6.0
        spaces = _truth_spaces(plan, scale, H, 0.2 / t_true)
        rooms = [affine_transform(p, [1, 0, 0, -1, 0, H]) for p in _polys(cap["rooms"])]
        mr = match_polygons(rooms, spaces, 0.5)
        A["room_tp"] += mr.tp
        A["room_pred"] += mr.n_pred
        A["room_true"] += mr.n_true

    def prf(tp_p, n_p, tp_t, n_t):
        p = tp_p / n_p if n_p else 0.0
        r = tp_t / n_t if n_t else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}

    res = {"plans": len(folders), "ran_ok": n_ok, "crashes": dict(crashes),
           "seconds_per_plan_median": round(float(np.median(secs)), 2) if secs else None,
           "walls_3px": prf(A["w_tp_p"], A["w_np"], A["w_tp_t"], A["w_nt"]),
           "walls_iou": round(A["w_inter"] / max(A["w_union"], 1), 4)}
    for c in ("door", "window"):
        res[f"{c}_iou50"] = prf(A[f"{c}_tp50"], A[f"{c}_pred"], A[f"{c}_tp50"], A[f"{c}_true"])
        res[f"{c}_iou30"] = prf(A[f"{c}_tp30"], A[f"{c}_pred"], A[f"{c}_tp30"], A[f"{c}_true"])
    res["rooms_iou50"] = prf(A["room_tp"], A["room_pred"], A["room_tp"], A["room_true"])
    return res


def _room_px(truth: dict, room_id: str, dpi: float, page_h_mm: float):
    """Centroid of a truth room (metres) in the pixels of a page rendered at ``dpi``."""
    from shapely.geometry import Polygon

    tr = truth["pdf_transform"]
    room = next(r for r in truth["rooms"] if r["id"] == room_id)
    c = Polygon(room["polygon"]).centroid
    x_mm = c.x * tr["k"] + tr["ox"]
    y_mm = page_h_mm - (c.y * tr["k"] + tr["oy"])
    return x_mm * dpi / 25.4, y_mm * dpi / 25.4


def score_synth(runs: Path, synth_dir: Path) -> dict:
    import pymupdf
    from shapely.geometry import Point

    cases = json.loads((synth_dir.parent / "synth_cases.json").read_text())
    out = defaultdict(lambda: Counter())
    secs = defaultdict(list)
    for case in cases:
        truth = json.loads((synth_dir / f"{case['name']}.truth.json").read_text(encoding="utf-8"))
        page_h_mm = pymupdf.open(synth_dir / f"{case['name']}.pdf")[0].rect.height * 25.4 / 72
        for fmt, dpi in (("png", 200), ("pdf", 300)):       # make_plan PNG dpi; pdf2image dpi in the original
            cp = runs / f"{case['name']}_{fmt}" / "capture.json"
            if not cp.exists():
                out[fmt]["not run"] += 1
                continue
            cap = json.loads(cp.read_text(encoding="utf-8"))
            secs[fmt].append(cap["seconds"])
            S = out[fmt]
            if cap["exit_code"] != 0:
                S["crashed"] += 1
                continue
            S["ran"] += 1
            viol = cap["violations"]
            if not case["errors"]:
                S["clean_plans"] += 1
                S["violations_on_clean_plans"] += len(viol)
                for v in viol:
                    S["clean_" + v["type"]] += 1
                continue
            err = case["errors"][0]
            subject = next(e["subject"] for e in truth["expected_findings"] if e["error"] == err)
            px = _room_px(truth, subject, dpi, page_h_mm)
            rooms = _polys(cap["rooms"])
            hit = [i for i, r in enumerate(rooms) if r.contains(Point(px))]
            S["planted"] += 1
            want = PLANTED_TO_OLD[err]
            if hit and any(v["type"] == want and v.get("room_id") in hit for v in viol):
                S["planted_found_on_right_room"] += 1
            elif any(v["type"] == want for v in viol):
                S["planted_type_reported_elsewhere"] += 1
            if not hit:
                S["planted_room_not_detected"] += 1
            S["violations_total_on_error_plans"] += len(viol)
    return {fmt: {**dict(S), "seconds_median": round(float(np.median(secs[fmt])), 2) if secs[fmt] else None}
            for fmt, S in out.items()}


def rp_synth(synth_dir: Path, runs_dir: Path) -> dict:
    """ReviewPulse end to end (rp check) on the same 30 synthetic inputs. Resumable: an input whose
    run directory already holds findings.json and a recorded time is not run again."""
    from reviewpulse.cli import DEFAULT_PACK
    from reviewpulse.pipeline import run_all, run_id_for
    from reviewpulse.schema import load_findings

    cases = json.loads((synth_dir.parent / "synth_cases.json").read_text())
    tfile = runs_dir.parent / "rp_timings.json"
    timings = json.loads(tfile.read_text()) if tfile.exists() else {}
    out = defaultdict(lambda: Counter())
    secs = defaultdict(list)
    for case in cases:
        truth = json.loads((synth_dir / f"{case['name']}.truth.json").read_text(encoding="utf-8"))
        for fmt in ("png", "pdf"):
            S = out[fmt]
            src = synth_dir / f"{case['name']}.{fmt}"
            run_dir = runs_dir / run_id_for(src)
            key = f"{case['name']}.{fmt}"
            if not ((run_dir / "findings.json").exists() and key in timings):
                t0 = time.perf_counter()
                try:
                    run_all(src, DEFAULT_PACK, runs_dir)
                    timings[key] = round(time.perf_counter() - t0, 2)
                except Exception as e:  # noqa: BLE001 - a crash is a result
                    timings[key] = f"crash: {e!r}"[:200]
                tfile.write_text(json.dumps(timings, indent=1))
                print(key, timings[key], flush=True)
            if isinstance(timings[key], str):
                S["crashed"] += 1
                continue
            secs[fmt].append(timings[key])
            S["ran"] += 1
            fs = load_findings(run_dir / "findings.json")
            flagged = [f for f in fs if f.verdict in ("FAIL", "WARNING")]
            S["fail"] += sum(f.verdict == "FAIL" for f in fs)
            if not case["errors"]:
                S["clean_plans"] += 1
                S["flagged_on_clean_plans"] += len(flagged)
                S["fail_on_clean_plans"] += sum(f.verdict == "FAIL" for f in fs)
                continue
            S["planted"] += 1
            want = {e["rule"] for e in truth["expected_findings"]}
            if want & {f.rule_id for f in flagged}:
                S["planted_found"] += 1
    return {fmt: {**dict(S), "seconds_median": round(float(np.median(secs[fmt])), 2) if secs[fmt] else None}
            for fmt, S in out.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["cubicasa", "synth", "rp-synth", "rp-cubicasa"])
    ap.add_argument("--inputs", default=str(ROOT / "runs" / "baseline" / "inputs_cubicasa.txt"))
    ap.add_argument("--runs", default=None)
    ap.add_argument("--synth-dir", default=str(ROOT / "runs" / "baseline" / "synth"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "baseline"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.what == "cubicasa":
        res = score_cubicasa(Path(a.runs), Path(a.inputs))
    elif a.what == "rp-cubicasa":
        # ReviewPulse on exactly the plans the original was run on, same scoring
        from reviewpulse.eval.raster_eval import run as raster_run

        res, _worst = raster_run(100, ("rules", "model", "model_scan"), "test", names=_list_names(Path(a.inputs)))
    elif a.what == "synth":
        res = score_synth(Path(a.runs), Path(a.synth_dir))
    else:
        res = rp_synth(Path(a.synth_dir), ROOT / "runs" / "baseline" / "rp_runs")
    (out / f"{a.what}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
