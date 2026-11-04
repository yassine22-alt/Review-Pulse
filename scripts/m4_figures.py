"""Figures for docs/progress/M4_robustness.md (writes docs/progress/img/m4/).

    python scripts/m4_figures.py

1. OCR texts on a CubiCasa test scan coloured by how they are read, before and after (cached OCR).
2. Door/window rectangles before and after blob splitting, on the test plan where it changes most.
3. Rooms built from each acceptance input type (runs/acceptance*/<case>/runs/*/rooms_0.png).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "docs" / "progress" / "img" / "m4"
COLORS = {"room_label": (0, 150, 0), "area": (0, 90, 220), "dimension": (220, 0, 0), "note": (150, 150, 150),
          "tag": (200, 120, 0), "title_block": (150, 0, 150)}


def _font(size=22):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _caption(img: Image.Image, text: str) -> Image.Image:
    out = Image.new("RGB", (img.width, img.height + 40), "white")
    out.paste(img, (0, 40))
    ImageDraw.Draw(out).text((10, 8), text, fill="black", font=_font())
    return out


def _side(a: Image.Image, b: Image.Image) -> Image.Image:
    h = max(a.height, b.height)
    out = Image.new("RGB", (a.width + b.width + 20, h), "white")
    out.paste(a, (0, 0))
    out.paste(b, (a.width + 20, 0))
    return out


def fig_ocr() -> None:
    from eval_ocr_labels import ocr_words
    from eval_room_labels import BASELINE

    from reviewpulse.annotate import text_classify as tc
    from reviewpulse.eval.adapters.cubicasa import split_ids
    from reviewpulse.ingest.ocr import to_text_items

    folder = split_ids(ROOT / "data", "test")[0]
    words = ocr_words(folder, ROOT / "runs" / "ocr_cache")
    base = Image.open(folder / "F1_scaled.png").convert("RGB")
    panels = []
    for name in ("before", "after"):
        items = to_text_items(words, [1, 0, 0, 0, 1, 0], "p")       # keep pixel coordinates, y down
        if name == "before":
            lex = {tc.label_core(w): rt for rt, ws in BASELINE.items() for w in ws}
            saved, tc.room_lexicon = tc.room_lexicon, (lambda lex=lex: lex)
            try:
                for it in items:
                    c = tc.classify(it.text)
                    it.kind, it.value, it.unit, it.norm = c.kind, c.value, c.unit, c.norm
            finally:
                tc.room_lexicon = saved
        else:
            tc.classify_items(items)
        im = base.copy()
        d = ImageDraw.Draw(im)
        for t in items:
            d.rectangle(t.bbox, outline=COLORS.get(t.kind, (0, 0, 0)), width=4)
            if t.kind == "room_label":
                d.text((t.bbox[0], t.bbox[3] + 2), t.norm or "", fill=COLORS["room_label"], font=_font(20))
        n_lab = sum(t.kind == "room_label" for t in items)
        n_dim = sum(t.kind == "dimension" for t in items)
        im.thumbnail((1400, 1400))
        panels.append(_caption(im, f"{name}: {n_lab} room labels, {n_dim} dimensions "
                                   "(green label, blue area, red dimension, grey note)"))
    _side(*panels).save(OUT / "01_ocr_labels_1191.png")


def fig_openings() -> None:
    from reviewpulse.eval.adapters.cubicasa import split_ids
    from reviewpulse.perception.raster import vectorize
    from reviewpulse.perception.raster.segment import predict

    proc = ROOT / "data" / "processed" / "cubicasa_seg" / "test"
    best = None
    for f in split_ids(ROOT / "data", "test")[::4][:100]:
        ip = proc / f"{f.parent.name}_{f.name}.png"
        if not ip.exists():
            continue
        gray = np.asarray(Image.open(ip).convert("L"))
        _p, cls, _s = predict(gray, None)
        win = cls == 3
        vectorize.FILL_MIN = 0.0
        before = [r for _y, _x, r in vectorize.opening_parts(win)]
        vectorize.FILL_MIN = 0.6
        after = [r for _y, _x, r in vectorize.opening_parts(win)]
        gain = sum(r.area for r in before) - sum(r.area for r in after)
        if best is None or gain > best[0]:
            best = (gain, gray, before, after, ip.stem)
    _gain, gray, before, after, name = best
    panels = []
    for label, rects in (("before: one rectangle per blob", before), ("after: thin strokes split off", after)):
        im = Image.fromarray(gray).convert("RGB")
        d = ImageDraw.Draw(im)
        for r in rects:
            d.polygon([tuple(p) for p in list(r.exterior.coords)[:-1]], outline=(0, 160, 0), width=3)
        panels.append(_caption(im, f"{label} ({len(rects)} windows)"))
    _side(*panels).save(OUT / "02_window_rects.png")
    print("openings figure from", name)


def fig_acceptance() -> None:
    tiles = []
    for d in ("acceptance_final",):
        for case in sorted((ROOT / "runs" / d).glob("*")):
            pngs = sorted(case.glob("runs/*/rooms_0.png"))
            if pngs:
                im = Image.open(pngs[-1]).convert("RGB")
                im.thumbnail((520, 420))
                tiles.append((case.name, im))
    seen, uniq = set(), []
    for n, im in reversed(tiles):
        if n not in seen:
            seen.add(n)
            uniq.append((n, im))
    uniq.reverse()
    cols = 4
    rows = (len(uniq) + cols - 1) // cols
    W, H = 540, 470
    sheet = Image.new("RGB", (cols * W, rows * H), "white")
    d = ImageDraw.Draw(sheet)
    for i, (n, im) in enumerate(uniq):
        x, y = (i % cols) * W, (i // cols) * H
        sheet.paste(im, (x + 10, y + 40))
        d.text((x + 10, y + 8), n, fill="black", font=_font())
    sheet.save(OUT / "03_acceptance_rooms.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    which = set(sys.argv[1:]) or {"ocr", "openings", "acceptance"}
    if "ocr" in which:
        fig_ocr()
    if "openings" in which:
        fig_openings()
    if "acceptance" in which:
        fig_acceptance()
