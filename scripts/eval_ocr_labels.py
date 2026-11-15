"""Room labels and stated areas read by OCR from CubiCasa5K test scans, scored per ground-truth space.

    python scripts/eval_ocr_labels.py --n 20 [--llm]

OCR words are cached in runs/ocr_cache/<plan>.json (OCR is ~2 min per page on CPU). Per space whose
ground-truth class has a room type:
  label_ok   an OCR text inside the space is read as a room label of the right type
  area_read  a stated area was read for the space (label value or an area text inside it)
  area_ok    ... and it is within 10% of the space's own "a m x b m" dimensions label (rectangular
             spaces only: polygon area within 10% of its bounding box)
  false_dims bare numbers inside spaces read as dimensions (they feed the scale vote)
Variants: before (FR/EN keyword list, no label/number stacking) and after (shipped classifier);
--llm adds the LLM label fallback.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

SVG_NS = "{http://www.w3.org/2000/svg}"
DIMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*m\s*x\s*(\d+(?:\.\d+)?)\s*m")


def gt_spaces(folder: Path) -> list[dict]:
    from lxml import etree

    from reviewpulse.eval.adapters.cubicasa import _points, room_type_of
    from reviewpulse.ingest.svg_reader import _parse_transform

    out = []

    def walk(el, m):
        m = m @ _parse_transform(el.get("transform"))
        cls = (el.get("class") or "").strip()
        if cls == "Space" or cls.startswith("Space "):
            poly = el.find(f"{SVG_NS}polygon")
            txt = " ".join(t.strip() for t in el.itertext() if t.strip())
            if poly is not None:
                pts = _points(poly)
                if len(pts) >= 3:
                    hp = np.c_[pts, np.ones(len(pts))] @ m.T
                    dm = DIMS_RE.search(txt)
                    out.append({"type": room_type_of(cls[5:].strip()), "poly": hp[:, :2],
                                "dims_m2": float(dm.group(1)) * float(dm.group(2)) if dm else None})
            return
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch, m)

    walk(etree.parse(str(folder / "model.svg")).getroot(), np.eye(3))
    return out


def ocr_words(folder: Path, cache: Path, rotations=None, det=None, rec=None, timing: list | None = None):
    from reviewpulse.ingest.ocr import Word, read_page

    f = cache / (folder.parent.name + "_" + folder.name + ".json")
    if f.exists():
        return [Word(w["text"], w["score"], np.array(w["box"]), w["angle"], w["upright"])
                for w in json.loads(f.read_text(encoding="utf-8"))]
    from PIL import Image

    gray = np.asarray(Image.open(folder / "F1_scaled.png").convert("L"))
    import time

    t0 = time.time()
    words = read_page(gray, rotations=rotations, det=det, rec=rec)
    if timing is not None:
        timing.append(time.time() - t0)
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps([{"text": w.text, "score": w.score, "box": w.box.tolist(), "angle": w.angle,
                              "upright": w.upright} for w in words], ensure_ascii=False), encoding="utf-8")
    return words


def main() -> None:
    from eval_room_labels import BASELINE, SAME
    from shapely.geometry import Point, Polygon

    from reviewpulse.annotate import text_classify as tc
    from reviewpulse.eval.adapters.cubicasa import split_ids
    from reviewpulse.ingest.ocr import to_text_items

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--vlm", action="store_true", help="add the vision-model second reader (qwen2.5vl:7b)")
    ap.add_argument("--rotations", default="", help="e.g. 0,90 (default: the module's)")
    ap.add_argument("--det", default=None)
    ap.add_argument("--rec", default=None)
    ap.add_argument("--tag", default="", help="cache/report suffix for an OCR configuration")
    a = ap.parse_args()
    folders = split_ids(ROOT / "data", "test")
    folders = folders[:: max(1, len(folders) // a.n)][: a.n]
    cache = ROOT / "runs" / ("ocr_cache" + (f"_{a.tag}" if a.tag else ""))
    rots = tuple(int(r) for r in a.rotations.split(",")) if a.rotations else None
    timing: list = []

    def before(items):
        lex = {tc.label_core(w): rt for rt, ws in BASELINE.items() for w in ws}
        saved = tc.room_lexicon
        tc.room_lexicon = lambda: lex
        try:
            for it in items:
                c = tc.classify(it.text)
                it.kind, it.value, it.unit, it.norm = c.kind, c.value, c.unit, c.norm
        finally:
            tc.room_lexicon = saved

    def after(items):
        tc.classify_items(items)

    def after_llm(items):
        from reviewpulse.annotate.label_llm import apply_llm_labels

        tc.classify_items(items)
        apply_llm_labels(items)

    page = {}

    def after_vlm(items):
        from reviewpulse.annotate.label_vlm import reread_labels

        tc.classify_items(items)
        # items are in y-up pixels (to_text_items with [1, 0, 0, 0, -1, 0]): back to image rows
        reread_labels(items, page["gray"], lambda b: (b[0], -b[3], b[2], -b[1]))

    variants = {"before": before, "after": after}
    if a.llm:
        variants["after+llm"] = after_llm
    if a.vlm:
        variants["after+vlm"] = after_vlm
    agg = {k: dict(spaces=0, label_ok=0, area_read=0, area_ok=0, area_rect=0, false_dims=0) for k in variants}
    for i, folder in enumerate(folders):
        try:
            words = ocr_words(folder, cache, rots, a.det, a.rec, timing)
        except Exception as e:  # noqa: BLE001 - one bad page must not stop the eval
            print("skip", folder, repr(e)[:120], flush=True)
            continue
        spaces = [s for s in gt_spaces(folder) if s["type"] != "other"]
        if a.vlm:
            from PIL import Image

            page["gray"] = np.asarray(Image.open(folder / "F1_scaled.png").convert("L"))
        for name, fn in variants.items():
            items = to_text_items(words, [1, 0, 0, 0, -1, 0], "p")      # y up, pixels
            fn(items)
            g = agg[name]
            for s in spaces:
                poly = Polygon([(x, -y) for x, y in s["poly"]]).buffer(0)
                inside = [t for t in items if poly.contains(Point((t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2))]
                g["spaces"] += 1
                if any(t.kind == "room_label" and (t.norm == s["type"] or (t.norm, s["type"]) in SAME) for t in inside):
                    g["label_ok"] += 1
                vals = [t.value for t in inside if t.kind == "area" and t.value] + \
                       [t.value for t in inside if t.kind == "room_label" and t.value]
                if vals:
                    g["area_read"] += 1
                rect = s["dims_m2"] and poly.area >= 0.9 * poly.envelope.area
                if rect:
                    g["area_rect"] += 1
                    if vals and abs(vals[0] - s["dims_m2"]) <= 0.1 * s["dims_m2"]:
                        g["area_ok"] += 1
                g["false_dims"] += sum(1 for t in inside if t.kind == "dimension"
                                       and re.fullmatch(r"\s*\d+(?:[.,]\d+)?\s*", t.text))
        print(f"{i + 1}/{len(folders)} {folder.name}", flush=True)
    res = {}
    for k, g in agg.items():
        n = max(g["spaces"], 1)
        res[k] = {"spaces": g["spaces"], "label_correct": round(g["label_ok"] / n, 4),
                  "stated_area_read": round(g["area_read"] / n, 4),
                  "stated_area_within_10pct_of_rect": round(g["area_ok"] / max(g["area_rect"], 1), 4),
                  "bare_numbers_read_as_dimensions": g["false_dims"]}
    if timing:
        res["ocr_seconds_per_page"] = round(sum(timing) / len(timing), 1)
    from reviewpulse.ingest.ocr import ocr_device

    res["config"] = {"rotations": a.rotations or "default", "det": a.det or "default", "rec": a.rec or "default",
                     "device": ocr_device()}
    out = ROOT / "reports" / f"{dt.date.today()}_ocr_labels_cubicasa{('_' + a.tag) if a.tag else ''}.md"
    lines = ["# Evaluation: OCR room labels and stated areas", "",
             f"- dataset: CubiCasa5K test, {len(folders)} plans, PaddleOCR words (cached in runs/ocr_cache)",
             "- truth: space class and its 'a m x b m' label in model.svg", "", "## Metrics", "", "```",
             json.dumps(res, indent=1), "```"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
