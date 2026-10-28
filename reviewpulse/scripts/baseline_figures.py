"""Side-by-side figures for docs/baseline_0.md, from real runs only.

For a CubiCasa5K test plan: the original pipeline's segmentation (from its capture: walls red,
doors = windows blue, since its windows are a copy of its doors), its own annotated output, and
ReviewPulse's model masks on the same pixels (walls red, doors blue, windows green). For a
synthetic plan: the original's annotated PNG next to page 1 of ReviewPulse's annotated report.

    python scripts/baseline_figures.py --cubicasa high_quality_architectural_1191 colorful_2207 \
        --synth synth_0005_metric_room_small synth_0010_topo_isolated_room
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from raster_figures import overlay, report_page, side_by_side  # noqa: E402

OUT = ROOT / "docs" / "progress" / "img" / "baseline"
B = ROOT / "runs" / "baseline"


def cubicasa(name: str) -> Path:
    from reviewpulse.perception.raster.segment import predict

    gray = np.asarray(Image.open(ROOT / "data" / "processed" / "cubicasa_seg" / "test" / f"{name}.png").convert("L"))
    cap = np.load(B / "out_cubicasa" / f"{name}_png" / "capture.npz")
    old = np.zeros(gray.shape, np.uint8)
    old[cap["doors"]] = 2
    old[cap["walls"]] = 1
    annotated = Image.open(B / "out_cubicasa" / f"{name}_png" / "outputs" / "annotated_plan.png").convert("RGB")
    _p, cls, _s = predict(gray, None)
    fig = side_by_side([overlay(gray, old), annotated, overlay(gray, cls)],
                       ["original: DeepFloorPlan masks (walls red, doors=windows blue)",
                        "original: its annotated output", "ReviewPulse: walls red, doors blue, windows green"])
    p = OUT / f"cubicasa_{name}.png"
    fig.save(p)
    return p


def synth(name: str) -> Path:
    annotated = Image.open(B / "out_synth" / f"{name}_png" / "outputs" / "annotated_plan.png").convert("RGB")
    from reviewpulse.pipeline import run_id_for

    run = B / "rp_runs" / run_id_for(B / "synth" / f"{name}.png")      # ReviewPulse on the same PNG
    tmp = OUT / f"_{name}_rp.png"
    report_page(run / "report.pdf", tmp)
    fig = side_by_side([annotated, Image.open(tmp).convert("RGB")],
                       ["original on the PNG: its annotated output", "ReviewPulse: annotated report, page 1"])
    tmp.unlink()
    p = OUT / f"synth_{name}.png"
    fig.save(p)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cubicasa", nargs="*", default=[])
    ap.add_argument("--synth", nargs="*", default=[])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for n in a.cubicasa:
        print(cubicasa(n))
    for n in a.synth:
        print(synth(n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
