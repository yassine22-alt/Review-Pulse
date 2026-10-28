"""Baseline 0 (A1): run the ORIGINAL repo pipeline (root main.py, DeepFloorPlan) unchanged.

Runs in its own venv (reviewpulse/.baseline_venv, the root requirements.txt):

    .baseline_venv/Scripts/python.exe scripts/baseline_run.py --list runs/baseline/inputs.txt --out runs/baseline/out

For every input, ``main.main()`` of the original code is executed as-is with ``sys.argv`` set
as the CLI would set it. Nothing in the original files is edited. To score its geometry with the
same metrics ReviewPulse uses, the functions main.py imports are wrapped: the wrappers call the
original and keep a copy of the result. Per input it writes:
  <name>/outputs/...        the original outputs (report.json, overlay, masks, graph)
  <name>/capture.npz        geometry masks (walls processed, doors/windows as used for geometry, rooms)
  <name>/capture.json       room/door/window/wall polygons (pixel coords, y down) and violations
plus run_log.jsonl (exit code, printed message, wall-clock seconds).

The original reads its weights from ``store/model`` relative to the working directory, so the
harness runs from a work directory holding a copy of the public TF2DeepFloorplan SavedModel.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # reviewpulse/
REPO = ROOT.parent                                   # original repo root
WEIGHTS = ROOT / "data" / "models" / "deepfloorplan" / "model" / "store"


def _geoms_to_json(geoms) -> list:
    from shapely.geometry import mapping

    return [mapping(g) for g in geoms]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True, help="text file, one input path per line")
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", default=str(ROOT / "runs" / "baseline" / "work"))
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(a.work).resolve()
    if not (work / "store" / "model" / "saved_model.pb").exists():
        shutil.copytree(WEIGHTS, work / "store" / "model", dirs_exist_ok=True)
    inputs = [Path(x.strip()).resolve() for x in Path(a.list).read_text(encoding="utf-8").splitlines() if x.strip()]

    os.chdir(work)
    sys.path.insert(0, str(REPO))
    import numpy as np

    t_import = time.perf_counter()
    import main as orig  # the original entry point, unmodified
    import_s = time.perf_counter() - t_import

    cap: dict = {}
    _prep, _build, _check = orig._prepare_masks_for_contour_extraction, orig.build_geometries, orig.check_compliance

    def prep(processed, raw):
        r = _prep(processed, raw)
        cap["masks"] = {k: np.asarray(v) for k, v in r.items()}
        return r

    def build(contours):
        r = _build(contours)
        cap["geoms"] = r
        return r

    def check(rooms, doors, walls):
        r = _check(rooms, doors, walls)
        cap["violations"] = r
        return r

    orig._prepare_masks_for_contour_extraction, orig.build_geometries, orig.check_compliance = prep, build, check

    log = (out / "run_log.jsonl").open("a", encoding="utf-8")
    for src in inputs:
        name = f"{src.stem}_{src.suffix.lstrip('.').lower()}"
        dst = out / name
        if (dst / "capture.json").exists():
            continue
        cap.clear()
        shutil.rmtree(work / "outputs", ignore_errors=True)
        sys.argv = ["main.py", str(src)]
        buf = io.StringIO()
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(buf):
            code = orig.main()
        secs = time.perf_counter() - t0
        dst.mkdir(parents=True, exist_ok=True)
        if (work / "outputs").exists():
            shutil.copytree(work / "outputs", dst / "outputs", dirs_exist_ok=True)
        rec = {"name": name, "input": str(src), "exit_code": code, "seconds": round(secs, 2),
               "message": buf.getvalue().strip()[-600:], "import_seconds_once": round(import_s, 2)}
        if "masks" in cap:
            np.savez_compressed(dst / "capture.npz", **{k: (v > 0) for k, v in cap["masks"].items()})
        g = cap.get("geoms") or {}
        (dst / "capture.json").write_text(json.dumps({
            **rec,
            "rooms": _geoms_to_json(g.get("rooms", [])), "doors": _geoms_to_json(g.get("doors", [])),
            "windows": _geoms_to_json(g.get("windows", [])), "walls": _geoms_to_json(g.get("walls", [])),
            "violations": cap.get("violations", []),
        }, default=float), encoding="utf-8")
        log.write(json.dumps(rec) + "\n")
        log.flush()
        print(f"{name}: exit {code} in {secs:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
