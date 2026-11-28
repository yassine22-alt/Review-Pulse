"""What the drawing set model reads from a page: text lines with boxes and the boxes of the vector drawing.

The model works on `PageData`, never on the PDF itself, so the same code serves a text layer, OCR words and the metamorphic
tests (which rotate a page, rename a sheet number or move a view by changing this data).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float = 10.0          # font size, or box height for OCR
    dx: float = 1.0             # reading direction (1, 0) = left to right
    dy: float = 0.0
    src: str = "text"           # "text" (vector text layer) or "ocr"

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        """Text height: the short side of the box."""
        return max(1.0, min(self.x1 - self.x0, self.y1 - self.y0))

    @property
    def horizontal(self) -> bool:
        return abs(self.dx) >= abs(self.dy)


@dataclass
class PageData:
    index: int
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    rects: np.ndarray = field(default_factory=lambda: np.zeros((0, 4)))   # boxes of the drawing paths, display frame
    has_text_layer: bool = True


def rotate_cw90(pg: PageData) -> PageData:
    """The page turned a quarter turn clockwise (x' = H - y, y' = x)."""
    H = pg.height
    out = PageData(pg.index, pg.height, pg.width, has_text_layer=pg.has_text_layer)
    for ln in pg.lines:
        out.lines.append(Line(ln.text, H - ln.y1, ln.x0, H - ln.y0, ln.x1, ln.size, -ln.dy, ln.dx, ln.src))
    r = pg.rects
    out.rects = np.stack([H - r[:, 3], r[:, 0], H - r[:, 1], r[:, 2]], axis=1) if len(r) else r.copy()
    return out


def canonicalize(pg: PageData) -> PageData:
    """Turn the page so that most of its text reads left to right. A rotated PDF page then gives the same model."""
    for _ in range(4):
        w = {(1, 0): 0, (0, 1): 0, (-1, 0): 0, (0, -1): 0}
        for ln in pg.lines:
            d = (int(round(ln.dx)), int(round(ln.dy)))
            if d in w:
                w[d] += len(ln.text)
        if not any(w.values()) or max(w, key=w.get) == (1, 0):
            return pg
        pg = rotate_cw90(pg)
    return pg


def from_pdf(path: str | Path, pages: list[int] | None = None) -> list[PageData]:
    """Text lines and drawing boxes of every page of a PDF, in the displayed frame (page rotation applied)."""
    import pymupdf

    doc = pymupdf.open(str(path))
    out = []
    for pno in range(len(doc)):
        if pages is not None and pno not in pages:
            continue
        page = doc[pno]
        m = page.rotation_matrix
        W, H = page.rect.width, page.rect.height
        pg = PageData(pno, W, H)
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if not txt:
                    continue
                r = pymupdf.Rect(ln["bbox"]) * m
                d = pymupdf.Point(ln["dir"]) * pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)
                size = max(s["size"] for s in ln["spans"])
                pg.lines.append(Line(txt, r.x0, r.y0, r.x1, r.y1, size, round(d.x, 3), round(d.y, 3)))
        rects = []
        for d in page.get_drawings():
            r = d.get("rect")
            if r is None:
                continue
            r = pymupdf.Rect(r) * m
            rects.append((r.x0, r.y0, r.x1, r.y1))
        if rects:
            pg.rects = np.array(rects, dtype=float)
        pg.has_text_layer = bool(pg.lines)
        out.append(canonicalize(pg))
    return out


def from_ocr_words(index: int, width: float, height: float, words: list[tuple[str, float, float, float, float]],
                   rects: np.ndarray | None = None) -> PageData:
    """A page from OCR words (text, x0, y0, x1, y1). Words on the same row and close together are joined into lines."""
    pg = PageData(index, width, height, has_text_layer=False)
    ws = sorted(words, key=lambda w: ((w[2] + w[4]) / 2, w[1]))
    rows: list[list[tuple]] = []
    for w in ws:
        h = w[4] - w[2]
        for row in rows:
            last = row[-1]
            if abs((last[2] + last[4]) / 2 - (w[2] + w[4]) / 2) < 0.5 * h and 0 <= w[1] - last[3] < 1.2 * h:
                row.append(w)
                break
        else:
            rows.append([w])
    for row in rows:
        row.sort(key=lambda w: w[1])
        pg.lines.append(Line(" ".join(w[0] for w in row), min(w[1] for w in row), min(w[2] for w in row),
                             max(w[3] for w in row), max(w[4] for w in row), max(w[4] - w[2] for w in row), src="ocr"))
    if rects is not None:
        pg.rects = rects
    return pg


def merge_ocr(pg: PageData, ocr_lines: list[Line]) -> PageData:
    """Add OCR lines to a page, skipping those that repeat a text line already there (same text and place)."""
    out = copy.deepcopy(pg)
    for o in ocr_lines:
        dup = any(o.text.lower() == ln.text.lower() and abs(o.cx - ln.cx) < 2 * ln.h and abs(o.cy - ln.cy) < 2 * ln.h
                  for ln in out.lines)
        if not dup:
            out.lines.append(o)
    return out


# ---- changes used by the metamorphic tests -------------------------------------------------------------------------

def rename_sheet(pages: list[PageData], old: str, new: str) -> list[PageData]:
    """Replace a sheet number everywhere it is written (title block, callouts, index), whole tokens only."""
    pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(old) + r"(?![A-Za-z0-9])")
    out = copy.deepcopy(pages)
    for pg in out:
        for ln in pg.lines:
            ln.text = pat.sub(new, ln.text)
    return out


def translate_box(pg: PageData, box: tuple[float, float, float, float], dx: float, dy: float) -> PageData:
    """Move every line and path whose centre is inside `box` by (dx, dy)."""
    out = copy.deepcopy(pg)
    x0, y0, x1, y1 = box
    for ln in out.lines:
        if x0 <= ln.cx <= x1 and y0 <= ln.cy <= y1:
            ln.x0 += dx
            ln.x1 += dx
            ln.y0 += dy
            ln.y1 += dy
    r = out.rects
    if len(r):
        cx, cy = (r[:, 0] + r[:, 2]) / 2, (r[:, 1] + r[:, 3]) / 2
        sel = (cx >= x0) & (cx <= x1) & (cy >= y0) & (cy <= y1)
        r = r.copy()
        r[sel, 0] += dx
        r[sel, 2] += dx
        r[sel, 1] += dy
        r[sel, 3] += dy
        out.rects = r
    return out
