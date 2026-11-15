"""Text drawn as outlines in vector PDFs (CAD exports of SHX fonts, "text to curves").

Such a page has geometry but no text layer: labels, dimensions and tags exist only as strokes. The page
is rendered and read by the same OCR as scans; the words become TextItems in sheet millimetres, and the
glyph strokes inside each word box are hidden so letters cannot be read as walls or dimension marks.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..schema import Sheet

RENDER_DPI = 300
GLYPH_MAX_MM = 12.0          # a stroke longer than this inside a word box is drawing, not lettering


def needs_ocr(sheet: Sheet) -> bool:
    return any(w.startswith("text_as_outlines") for w in sheet.warnings)


def ocr_outline_text(sheet: Sheet, pdf: Path, page_no: int) -> int:
    """Read outlined text on a vector PDF page; returns the number of words added."""
    import pymupdf
    from shapely.geometry import Polygon, box
    from shapely.strtree import STRtree

    from .ocr import available_backends, read_page, to_text_items

    if not available_backends():
        sheet.warnings.append("text_as_outlines: no OCR backend installed, outlined text not read")
        return 0
    pix = pymupdf.open(pdf)[page_no].get_pixmap(dpi=RENDER_DPI, colorspace=pymupdf.csGRAY)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    mm = 25.4 / RENDER_DPI
    # pixel (x down the row, y down the page) -> sheet mm, y up; the pixmap is the rotated page
    affine = [mm, 0.0, 0.0, 0.0, -mm, pix.height * mm]
    words = read_page(gray)
    items = to_text_items(words, affine, sheet.id)
    for t in items:
        t.prov.stage = "ocr_outline_text"
    # hide glyph strokes: primitives lying inside a word box and short enough to be lettering
    boxes = [Polygon([(affine[0] * x + affine[2], affine[4] * y + affine[5]) for x, y in w.box]).buffer(0.3)
             for w in words]
    if boxes:
        tree = STRtree(boxes)
        for p in sheet.primitives:
            if p.hidden or (not p.pts and p.center is None):
                continue
            pts = p.pts or [(p.center[0] - (p.radius or 0), p.center[1] - (p.radius or 0)),
                            (p.center[0] + (p.radius or 0), p.center[1] + (p.radius or 0))]
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            if max(max(xs) - min(xs), max(ys) - min(ys)) > GLYPH_MAX_MM:
                continue
            g = box(min(xs), min(ys), max(xs), max(ys))
            if any(boxes[i].contains(g) for i in tree.query(g)):
                p.hidden = True
                p.prov.evidence["glyph"] = True
    sheet.texts += items
    sheet.warnings = [w for w in sheet.warnings if not w.startswith("text_as_outlines")]
    sheet.warnings.append(f"text_as_outlines: {len(items)} words read by OCR from the rendered page (tier at most T2)")
    return len(items)
