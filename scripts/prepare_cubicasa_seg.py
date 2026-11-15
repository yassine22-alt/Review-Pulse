"""Render CubiCasa5K images + class masks for segmentation training.

    python scripts/prepare_cubicasa_seg.py --max-side 1024 --workers 8

Writes data/processed/cubicasa_seg/<split>/<subset>_<id>.png (grey) and ..._mask.png (0 bg, 1 wall,
2 door, 3 window), scaled so the longest side is at most --max-side (never upscaled).
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _one(args):
    folder, out_dir, max_side = args
    from PIL import Image

    from reviewpulse.eval.adapters.cubicasa import masks, parse

    name = f"{folder.parent.name}_{folder.name}"
    dst = out_dir / f"{name}.png"
    if dst.exists() and (out_dir / f"{name}_mask.png").exists():
        return name, "cached"
    try:
        plan = parse(folder)
        scale = min(1.0, max_side / max(plan.size))
        with Image.open(folder / "F1_scaled.png") as im:
            g = im.convert("L").resize((int(round(plan.size[0] * scale)), int(round(plan.size[1] * scale))),
                                      Image.BILINEAR)
        m = masks(plan, scale)
        if m.shape[::-1] != g.size:
            m = __import__("numpy").asarray(Image.fromarray(m).resize(g.size, Image.NEAREST))
        g.save(dst)
        Image.fromarray(m).save(out_dir / f"{name}_mask.png")
        return name, "ok"
    except Exception as e:  # noqa: BLE001 - a broken sample is skipped and reported
        return name, f"error {e!r}"[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-side", type=int, default=1024)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--splits", nargs="*", default=["train", "val", "test"])
    a = ap.parse_args()
    from reviewpulse.eval.adapters.cubicasa import split_ids

    for split in a.splits:
        out_dir = ROOT / "data" / "processed" / "cubicasa_seg" / split
        out_dir.mkdir(parents=True, exist_ok=True)
        jobs = [(f, out_dir, a.max_side) for f in split_ids(ROOT / "data", split)]
        errors = []
        with ProcessPoolExecutor(a.workers) as ex:
            for name, status in ex.map(_one, jobs, chunksize=8):
                if status.startswith("error"):
                    errors.append((name, status))
        print(f"{split}: {len(jobs) - len(errors)} ok, {len(errors)} errors", errors[:3])
    return 0


if __name__ == "__main__":
    sys.exit(main())
