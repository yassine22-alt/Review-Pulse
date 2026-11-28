"""JSON and HTML report of a back check, with side by side crops (old and new region, PNG files, red box on the comment's place)."""

from __future__ import annotations

import html
import json
from pathlib import Path

import numpy as np

from .check import BackCheckResult
from .model import BBox

COLORS = {"RESOLVED": "#1a7f37", "NOT ADDRESSED": "#b3261e", "CHANGED BUT NOT SETTLED": "#9a6700", "MOVED": "#0b57d0",
          "CANNOT TELL": "#5f6368"}


def crop_png(pdf: str, page: int, box: BBox, out: Path, *, zoom: float = 2.0, context: float = 60.0) -> bool:
    """A PNG of `box` (page frame, points) with `context` points around it, and the box drawn in red. False when it cannot be made."""
    import pymupdf

    try:
        with pymupdf.open(pdf) as doc:
            pg = doc[page - 1]
            W, H = pg.rect.width, pg.rect.height
            if pg.rotation % 180:
                W, H = H, W
            clip = pymupdf.Rect(max(0, box[0] - context), max(0, box[1] - context), min(W, box[2] + context), min(H, box[3] + context))
            if clip.is_empty or clip.width < 2 or clip.height < 2:
                return False
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip * pg.rotation_matrix, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
            r = (clip * pg.rotation_matrix)
            b = pymupdf.Rect(box) * pg.rotation_matrix
            x0, x1 = int((b.x0 - r.x0) * zoom), int((b.x1 - r.x0) * zoom)
            y0, y1 = int((b.y0 - r.y0) * zoom), int((b.y1 - r.y0) * zoom)
            h, w = img.shape[:2]
            red = np.array([220, 0, 0], dtype=np.uint8)
            for t in range(2):
                for yy in (y0 + t, y1 - t):
                    if 0 <= yy < h:
                        img[yy, max(0, x0):min(w, x1 + 1), :3] = red
                for xx in (x0 + t, x1 - t):
                    if 0 <= xx < w:
                        img[max(0, y0):min(h, y1 + 1), xx, :3] = red
            out.parent.mkdir(parents=True, exist_ok=True)
            pymupdf.Pixmap(pymupdf.csRGB, w, h, img[:, :, :3].tobytes(), False).save(str(out))
            return True
    except Exception:
        return False


def write_report(res: BackCheckResult, out_dir: str | Path, title: str = "Back check") -> tuple[Path, Path]:
    out = Path(out_dir)
    img = out / "crops"
    img.mkdir(parents=True, exist_ok=True)
    for v in res.verdicts:
        e = v.evidence
        for side, pdf, place in (("old", res.old_pdf, e.old_place), ("new", res.new_pdf, e.new_place)):
            if place.page and place.bbox:
                f = img / f"{v.comment.id}_{side}.png"
                if crop_png(pdf, place.page, place.bbox, f):
                    e.crops[side] = f"crops/{f.name}"
    for r in [*res.new_issues, *res.not_clouded]:
        for side, pdf, pg, box in (("old", res.old_pdf, r.page_old, r.bbox_old), ("new", res.new_pdf, r.page_new, r.bbox_new)):
            f = img / f"{r.id}_{side}.png"
            if not f.exists():
                crop_png(pdf, pg, box, f)
    jp = out / "backcheck.json"
    jp.write_text(json.dumps(res.to_dict(), indent=1, default=float), encoding="utf-8")
    hp = out / "backcheck.html"
    hp.write_text(_html(res, title), encoding="utf-8")
    return jp, hp


def _pair(out_dir_rel: str, key: str) -> str:
    return (f'<div class="pair"><figure><img src="crops/{key}_old.png" alt="old"><figcaption>old</figcaption></figure>'
            f'<figure><img src="crops/{key}_new.png" alt="new"><figcaption>new</figcaption></figure></div>')


def _html(res: BackCheckResult, title: str) -> str:
    esc = html.escape
    parts = [f"<!doctype html><meta charset='utf-8'><title>{esc(title)}</title><style>body{{font:14px sans-serif;max-width:1100px;margin:2em auto}}"
             ".pair{display:flex;gap:8px}.pair img{max-width:100%;border:1px solid #888}figure{margin:0;flex:1}"
             ".tag{color:#fff;padding:1px 8px;border-radius:3px}.c{border-top:1px solid #ccc;margin-top:1.2em;padding-top:.6em}"
             "small{color:#555}</style>", f"<h1>{esc(title)}</h1>",
             f"<p>Old: {esc(res.old_pdf)}<br>New: {esc(res.new_pdf)}</p>",
             "<p>" + ", ".join(f"{esc(k)}: {n}" for k, n in res.counts().items()) + "</p><h2>Previous comments</h2>"]
    for v in res.verdicts:
        e = v.evidence
        parts.append(f"<div class='c'><b>{esc(v.comment.id)}</b> <span class='tag' style='background:{COLORS.get(v.status, '#000')}'>{esc(v.status)}</span> "
                     f"<small>{esc(v.comment.code)}</small><p>{esc(v.comment.text)}</p><p>{esc(v.reason)}</p>")
        parts.append(f"<small>old: page {e.old_place.page} sheet {esc(str(e.old_place.sheet))} | new: page {e.new_place.page} sheet {esc(str(e.new_place.sheet))}"
                     f" | demand: {esc(e.demand)}<br>old value: {esc(e.old_value)}<br>new value: {esc(e.new_value)}<br>diff: {esc(e.diff)}")
        for ch in e.checks:
            parts.append(f"<br>check: {esc(ch)}")
        if e.person_must_check:
            parts.append(f"<br><b>a person must check:</b> {esc(e.person_must_check)}")
        parts.append("</small>")
        if e.crops:
            parts.append(_pair("", v.comment.id))
        if len(v.history) > 1:
            parts.append("<br><small>history: " + " > ".join(esc(h["status"]) for h in v.history) + "</small>")
        parts.append("</div>")
    parts.append(f"<h2>New issues (changed, no previous comment): {len(res.new_issues)}</h2>")
    for r in res.new_issues:
        parts.append(f"<div class='c'><b>{r.id}</b> sheet {esc(r.sheet_new)} {esc(r.view)}: {esc(r.describe())}{_pair('', r.id)}</div>")
    if res.clouds_present:
        parts.append(f"<h2>Changes not clouded: {len(res.not_clouded)}</h2>")
        for r in res.not_clouded:
            parts.append(f"<div class='c'><b>{r.id}</b> sheet {esc(r.sheet_new)}: {esc(r.describe())}{_pair('', r.id)}</div>")
        parts.append(f"<h2>Clouds with no change under them: {len(res.clouds_without_change)}</h2><ul>"
                     + "".join(f"<li>sheet {esc(str(c['sheet']))} page {c['page']} at {c['cloud']}</li>" for c in res.clouds_without_change) + "</ul>")
    parts.append(f"<h2>Sheets</h2><p>paired {len(res.sheets)}; removed {len(res.sheets_removed)}; added {len(res.sheets_added)}; "
                 f"renumbered {sum(s['renumbered'] for s in res.sheets)}; views moved {len(res.moved)}</p>")
    return "\n".join(parts)
