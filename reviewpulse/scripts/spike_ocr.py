"""Spike S-D: choose the OCR backend for raster plans.

Two measurements on CubiCasa5K test-split scans with FP-TXT text boxes (Schönfelder et al. 2023,
COCO boxes, no transcriptions):
- detection: precision / recall of the full read_page pipeline (tiles + rotations + dedupe)
  against the FP-TXT machine-printed boxes, IoU >= 0.3 (FP-TXT boxes are word or phrase level);
- recognition: character error rate on hand-transcribed crops (``crops`` writes the crops and an
  empty transcription file; a person fills ``gt.json``; ``cer`` scores each backend).

    python scripts/spike_ocr.py crops --n 20
    python scripts/spike_ocr.py cer
    python scripts/spike_ocr.py detect --n 30
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "data" / "raw" / "cubicasa5k" / "cubicasa5k"
FPTXT = ROOT / "data" / "raw" / "fptxt" / "FP-TXT" / "datasets" / "CubiCasa5k" / "labels.json"
OUT = ROOT / "reports" / "ocr_spike"


def fptxt_items(split: str | None = None) -> list[tuple[Path, list[list[float]]]]:
    """(scan path, machine-printed boxes xywh). FP-TXT names an image F1_original<n>.png where n is
    the 1-based position of that file in the sorted listing of high_quality_architectural (the
    replication rule of its main.py, re-implemented here rather than run); only image 1 is stored
    rotated. Sizes are checked so a changed listing cannot silently misalign boxes."""
    d = json.loads(FPTXT.read_text())
    root = CC / "high_quality_architectural"
    flat = [root / sub / f for sub in sorted(p.name for p in root.iterdir() if p.is_dir())
            for f in sorted(q.name for q in (root / sub).iterdir())]
    keep = None
    if split:
        keep = {Path(line.strip().strip("/")).name for line in (CC / f"{split}.txt").read_text().splitlines()
                if line.strip()}
    boxes: dict[int, list] = {}
    for a in d["annotations"]:
        if a["category_id"] == 1:
            boxes.setdefault(a["image_id"], []).append(a["bbox"])
    out = []
    for im in d["images"]:
        n = int(im["file_name"].removeprefix("F1_original").removesuffix(".png"))
        p = flat[n - 1] if 0 < n <= len(flat) else None
        if p is None or p.name != "F1_original.png" or im["id"] not in boxes:
            continue
        if keep is not None and p.parent.name not in keep:
            continue
        w, h = Image.open(p).size
        if (w, h) != (im["width"], im["height"]) and (h, w) != (im["width"], im["height"]):
            continue
        out.append((p, boxes[im["id"]]))
    return out


def gray(p: Path) -> np.ndarray:
    g = np.asarray(Image.open(p).convert("L"))
    return np.ascontiguousarray(np.rot90(g)) if p.parent.name == "1" else g   # FP-TXT image 1 is rotated


def cmd_crops(n: int, seed: int) -> None:
    rng = random.Random(seed)
    items = fptxt_items()
    (OUT / "crops").mkdir(parents=True, exist_ok=True)
    gt = {}
    for i in range(n):
        p, boxes = items[rng.randrange(len(items))]
        x, y, w, h = boxes[rng.randrange(len(boxes))]
        g = gray(p)
        crop = g[max(0, int(y) - 4):int(y + h) + 4, max(0, int(x) - 4):int(x + w) + 4]
        name = f"crop_{i:02d}.png"
        Image.fromarray(crop).save(OUT / "crops" / name)
        gt[name] = {"source": str(p.relative_to(ROOT)), "bbox": [x, y, w, h], "text": ""}
    (OUT / "gt_template.json").write_text(json.dumps(gt, indent=1, ensure_ascii=False))
    print(f"{n} crops in {OUT / 'crops'}; transcribe into gt.json")


def _cer(a: str, b: str) -> float:
    if not b:
        return float(bool(a))
    # Levenshtein distance via dynamic programming (case kept: plans mix cases meaningfully)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / len(b)


def cmd_cer(backends: list[str]) -> dict:
    from reviewpulse.ingest.ocr import read_page

    gt = json.loads((OUT / "gt.json").read_text(encoding="utf-8"))
    res = {}
    for be in backends:
        errs, rows, t0 = [], [], time.time()
        for name, rec in gt.items():
            g = gray(OUT / "crops" / name)
            pad = np.pad(g, 24, constant_values=255)
            words = read_page(pad, backend=be)        # same four rotations as the pipeline
            words.sort(key=lambda w: (w.box[:, 0].min() if w.angle == 0 else -w.box[:, 1].max()))
            pred = " ".join(w.text for w in words)
            e = _cer(pred.replace(" ", ""), rec["text"].replace(" ", ""))
            errs.append(e)
            rows.append({"crop": name, "truth": rec["text"], "pred": pred, "cer": round(e, 3)})
        res[be] = {"cer_mean": round(float(np.mean(errs)), 4), "exact": sum(r["cer"] == 0 for r in rows),
                   "n": len(rows), "seconds": round(time.time() - t0, 1), "rows": rows}
        print(be, res[be]["cer_mean"], res[be]["exact"], "/", len(rows), flush=True)
    (OUT / "cer.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    iw, ih = max(0, min(ax1, bx1) - max(ax0, bx0)), max(0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    u = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / u if u else 0.0


def detection_prf(pred: list, truth: list, thr: float = 0.3) -> tuple[int, int, int]:
    """Greedy one-to-one matching; a predicted box covering several truth words (or the reverse)
    still counts once - FP-TXT and OCR engines group words differently."""
    used, tp = set(), 0
    for p in sorted(pred, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1])):
        best, bi = 0.0, -1
        for i, t in enumerate(truth):
            if i in used:
                continue
            v = _iou(p, t)
            if v > best:
                best, bi = v, i
        if best >= thr:
            used.add(bi)
            tp += 1
    return tp, len(pred) - tp, len(truth) - tp


def cmd_detect(backends: list[str], n: int, seed: int) -> dict:
    from reviewpulse.ingest.ocr import read_page

    items = fptxt_items("test")            # pages of the CubiCasa test split only
    random.Random(seed).shuffle(items)
    items = items[:n]
    res = {}
    for be in backends:
        TP = FP = FN = 0
        t0 = time.time()
        for p, boxes in items:
            words = read_page(gray(p), backend=be)
            pred = [(w.box[:, 0].min(), w.box[:, 1].min(), w.box[:, 0].max(), w.box[:, 1].max()) for w in words]
            truth = [(x, y, x + w, y + h) for x, y, w, h in boxes]
            tp, fp, fn = detection_prf(pred, truth)
            TP, FP, FN = TP + tp, FP + fp, FN + fn
        P, R = TP / max(TP + FP, 1), TP / max(TP + FN, 1)
        res[be] = {"precision": round(P, 4), "recall": round(R, 4), "f1": round(2 * P * R / max(P + R, 1e-9), 4),
                   "pages": len(items), "truth_boxes": TP + FN, "sec_per_page": round((time.time() - t0) / len(items), 1)}
        print(be, res[be], flush=True)
    (OUT / "detect.json").write_text(json.dumps(res, indent=1))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["crops", "cer", "detect"])
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--backends", default="easyocr,paddle")
    a = ap.parse_args()
    bes = a.backends.split(",")
    if a.cmd == "crops":
        cmd_crops(a.n, a.seed)
    elif a.cmd == "cer":
        cmd_cer(bes)
    else:
        cmd_detect(bes, a.n, a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
