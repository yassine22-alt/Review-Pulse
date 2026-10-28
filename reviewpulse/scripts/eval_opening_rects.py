"""Door / window rectangles before and after blob splitting (vectorize.opening_parts), CubiCasa5K test.

    python scripts/eval_opening_rects.py --n 100

'before' disables the split (FILL_MIN = 0: every blob keeps its own rotated rectangle). Masks come
from the trained model on the rendered test split, so the mask-level scores are identical in both
runs; only the rectangles (and rooms, which use them) can change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from reviewpulse.eval import raster_eval
    from reviewpulse.perception.raster import vectorize

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    a = ap.parse_args()
    out = {}
    for name, fill in (("before", 0.0), ("after", vectorize.FILL_MIN)):
        vectorize.FILL_MIN = fill
        res, _ = raster_eval.run(n=a.n, methods=("model",))
        m = res["model"]
        out[name] = {k: m[k] for k in ("door_rect_iou50", "door_rect_oversized", "window_rect_iou50",
                                       "window_rect_oversized", "door_iou50", "window_iou50", "rooms_iou50")}
        print(name, json.dumps(out[name]), flush=True)
    rep = ROOT / "reports" / "2026-10-25_raster_opening_rects.md"
    rep.write_text("# Evaluation: door/window rectangles (blob splitting)\n\n- dataset: CubiCasa5K test, "
                   f"{res['plans']} plans, model masks\n\n```\n{json.dumps(out, indent=1)}\n```\n", encoding="utf-8")


if __name__ == "__main__":
    main()
