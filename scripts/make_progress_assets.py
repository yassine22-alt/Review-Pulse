"""Produce the screenshots used in docs/progress/ reports.

    python scripts/make_progress_assets.py docs/progress/img/m1

Writes: input plan, detected building model, annotated report page, summary page,
and a montage of randomised plans (input vs detected rooms).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

from reviewpulse import pipeline
from reviewpulse.cli import DEFAULT_PACK
from reviewpulse.report.debug_png import rooms_png
from reviewpulse.schema import BuildingModel, load, load_findings
from reviewpulse.synth.make_plan import make_plan
from reviewpulse.synth.random_plan import random_plan


def pdf_page_png(pdf: Path, page: int, out: Path, dpi: int = 110) -> Path:
    pymupdf.open(pdf)[page].get_pixmap(dpi=dpi).save(out)
    return out


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="rp_assets_"))
    errors = ("topo_exit_via_bath", "metric_door_narrow", "cons_written_vs_drawn", "coord_swing_overlap",
              "cons_schedule_width")
    p = make_plan(work, seed=5, errors=errors, name="demo")
    Image.open(p["png"]).convert("RGB").save(out_dir / "01_input_plan.png")
    run_dir, summary = pipeline.run_all(p["pdf"], DEFAULT_PACK, runs_dir=work / "runs")
    model = load(BuildingModel, run_dir / "building_0.json")
    rooms_png(model, out_dir / "02_detected_model.png")
    pdf_page_png(run_dir / "report.pdf", 0, out_dir / "03_annotated_report.png")
    pdf_page_png(run_dir / "report.pdf", 1, out_dir / "04_report_summary.png", dpi=90)
    findings = load_findings(run_dir / "findings.json")
    (out_dir / "demo_findings.json").write_text(json.dumps(
        {"summary": summary, "planted": list(errors),
         "issues": [dict(rule=f.rule_id, verdict=f.verdict, message=f.message, detected=f.detected,
                         required=f.required, tier=f.tier) for f in findings if f.verdict != "PASS"]},
        indent=1), encoding="utf-8")

    # generality montage: 4 randomised plans, input (PDF render) next to detected rooms
    styles = [dict(scheme="none", wall_style="filled", door_style="segments", angle=0.0, units="mm"),
              dict(scheme="numeric", wall_style="hatched", door_style="block", angle=17.0, units="m"),
              dict(scheme="fr", wall_style="polylines", door_style="bulge", angle=-33.0, units="mm"),
              dict(scheme="aia", wall_style="lines", door_style="arc_only", angle=90.0, units="m")]
    tiles = [_tile(work, 900 + i, st) for i, st in enumerate(styles)]
    _stack(tiles).save(out_dir / "05_generality_montage.png")

    # the same with real-world clutter (furniture, fixtures, hatch patterns, frame, grid axes)
    tiles = [_tile(work, 920 + i, dict(st, clutter=True)) for i, st in enumerate(styles)]
    _stack(tiles).save(out_dir / "06_clutter_montage.png")
    print("assets in", out_dir, "| run dir", run_dir)


def _tile(work: Path, seed: int, st: dict) -> Image.Image:
    from reviewpulse.eval.cli import _model_from

    rp = random_plan(work, seed=seed, png=True, **st)
    m = _model_from(rp["pdf"])
    det = work / f"det_{seed}.png"
    rooms_png(m, det)
    a = Image.open(rp["png"]).convert("RGB")
    b = Image.open(det).convert("RGB")
    h = 420
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h / b.height), h))
    tile = Image.new("RGB", (a.width + b.width + 30, h + 40), "white")
    tile.paste(a, (0, 40))
    tile.paste(b, (a.width + 30, 40))
    ImageDraw.Draw(tile).text((5, 8), " | ".join(f"{k}={v}" for k, v in st.items()), fill="black")
    return tile


def _stack(tiles: list) -> Image.Image:
    W = max(t.width for t in tiles)
    mont = Image.new("RGB", (W, sum(t.height + 20 for t in tiles)), "white")
    y = 0
    for t in tiles:
        mont.paste(t, (0, y))
        y += t.height + 20
    return mont


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/progress/img/latest"))
