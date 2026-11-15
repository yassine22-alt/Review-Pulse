"""Figures for docs/progress/M3_raster_path.md, produced from real runs (no hand editing).

For one CubiCasa5K test scan: the input, the rule and model wall/door/window masks, the
BuildingModel the pipeline built (rooms_0.png from ``rp check``), and the first page of the
annotated report. The same scan is also wrapped in an image-only PDF and checked, to show the
scanned-PDF route.

    python scripts/raster_figures.py --plan high_quality_architectural/1191
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "data" / "raw" / "cubicasa5k" / "cubicasa5k"
COLORS = {1: (200, 40, 40), 2: (30, 140, 230), 3: (40, 170, 70)}     # wall, door, window


def overlay(gray: np.ndarray, cls: np.ndarray, alpha: float = 0.55) -> Image.Image:
    rgb = np.dstack([gray] * 3).astype(np.float32)
    for k, c in COLORS.items():
        m = cls == k
        rgb[m] = (1 - alpha) * rgb[m] + alpha * np.array(c, np.float32)
    return Image.fromarray(rgb.astype(np.uint8))


def side_by_side(images: list[Image.Image], titles: list[str], height: int = 700) -> Image.Image:
    ims = [im.resize((max(1, int(im.width * height / im.height)), height)) for im in images]
    out = Image.new("RGB", (sum(i.width for i in ims) + 20 * (len(ims) - 1), height + 30), "white")
    d = ImageDraw.Draw(out)
    x = 0
    for im, t in zip(ims, titles):
        out.paste(im, (x, 30))
        d.text((x + 4, 8), t, fill=(0, 0, 0))
        x += im.width + 20
    return out


def image_pdf(png: Path, pdf: Path, dpi: float = 150) -> None:
    import fitz

    w, h = Image.open(png).size
    doc = fitz.open()
    page = doc.new_page(width=w * 72 / dpi, height=h * 72 / dpi)
    page.insert_image(page.rect, filename=str(png))
    doc.save(pdf)


def run_check(target: Path, runs: Path) -> Path:
    from reviewpulse import pipeline
    from reviewpulse.cli import DEFAULT_PACK

    run_dir = pipeline.inspect(target, runs)
    pipeline.extract(run_dir, None)
    pipeline.build(run_dir, None, set())
    pipeline.check(run_dir, DEFAULT_PACK, set())
    return run_dir


def report_page(pdf: Path, png: Path, zoom: float = 1.6) -> None:
    import fitz

    doc = fitz.open(pdf)
    doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(png)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="high_quality_architectural/1191")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "progress" / "img" / "m3")
    ap.add_argument("--runs", type=Path, default=ROOT / "runs" / "m3")
    ap.add_argument("--also", type=Path, nargs="*", default=[],
                    help="more scans to check; their model and report figures get the file stem as prefix")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    a.runs.mkdir(parents=True, exist_ok=True)

    from reviewpulse.ingest.raster_prep import load_image, prepare
    from reviewpulse.perception.raster.rules import wall_mask_rules
    from reviewpulse.perception.raster.segment import model_available, predict_refined

    src = CC / a.plan / "F1_scaled.png"
    name = "cc_" + a.plan.replace("/", "_")
    scan = a.runs / f"{name}.png"
    shutil.copy(src, scan)
    page = prepare(*load_image(scan))
    Image.fromarray(page.gray).save(a.out / "01_input.png")

    rule_wall, t = wall_mask_rules(page.binary, gray=page.gray)
    panels, titles = [overlay(page.gray, rule_wall.astype(np.uint8))], [f"rules: walls (t = {t:.0f} px)"]
    if model_available():
        _p, cls, s, _t = predict_refined(page.gray, page.binary)
        panels.append(overlay(page.gray, cls))
        titles.append(f"model: walls red, doors blue, windows green (rescale x{s:.2f})")
    side_by_side(panels, titles).save(a.out / "02_masks.png")

    summary = {}
    for kind, target in (("png", scan), ("pdf", a.runs / f"{name}_scan.pdf")):
        if kind == "pdf":
            image_pdf(scan, target)
        run_dir = run_check(target, a.runs / kind)
        model = json.loads((run_dir / "building_0.json").read_text(encoding="utf-8"))
        findings = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
        n_by = {}
        for el in model["elements"]:
            n_by[el["cls"]] = n_by.get(el["cls"], 0) + 1
        verdicts = {}
        for f in findings:
            verdicts[f["verdict"]] = verdicts.get(f["verdict"], 0) + 1
        summary[kind] = {"run": str(run_dir.relative_to(ROOT)), "tier": model.get("tier"),
                         "scale": model["sheet"].get("scale"), "elements": n_by, "rooms": len(model["rooms"]),
                         "texts": len(model["sheet"].get("texts", [])),
                         "warnings": model["sheet"].get("warnings", []), "verdicts": verdicts}
        if kind == "png":
            shutil.copy(run_dir / "rooms_0.png", a.out / "03_model.png")
            report_page(run_dir / "report.pdf", a.out / "04_report.png")
    for extra in a.also:
        run_dir = run_check(extra, a.runs / "also")
        model = json.loads((run_dir / "building_0.json").read_text(encoding="utf-8"))
        summary[extra.stem] = {"run": str(run_dir.relative_to(ROOT)), "tier": model.get("tier"),
                               "scale": model["sheet"].get("scale"), "rooms": [
                                   (r.get("label"), round(r.get("area_m2") or 0, 2)) for r in model["rooms"]],
                               "elements": {c: sum(e["cls"] == c for e in model["elements"])
                                            for c in ("wall", "door", "window")}}
        Image.fromarray(np.asarray(Image.open(extra).convert("L"))).save(a.out / f"{extra.stem}_input.png")
        shutil.copy(run_dir / "rooms_0.png", a.out / f"{extra.stem}_model.png")
        report_page(run_dir / "report.pdf", a.out / f"{extra.stem}_report.png")
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
