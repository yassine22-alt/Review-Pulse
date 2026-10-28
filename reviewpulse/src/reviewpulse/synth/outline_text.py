"""Convert a PDF's text to vector outlines, as CAD exports of SHX fonts do.

Every text span is redrawn as filled glyph outlines (matplotlib TextPath) at the same position, size
and direction, then the real text is removed. Geometry is untouched. Used to test the outlined-text
path (ingest/outline_text.py) on any generated or real PDF.
"""

from __future__ import annotations

import math
from pathlib import Path


def outline_pdf(src: str | Path, dst: str | Path) -> Path:
    import pymupdf
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath

    doc = pymupdf.open(src)
    font = FontProperties(family="DejaVu Sans")
    for page in doc:
        spans = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                dx, dy = line["dir"]                     # unit baseline direction, y down
                for sp in line["spans"]:
                    if sp["text"].strip():
                        spans.append((sp["text"], sp["size"], sp["origin"], dx, dy, sp["bbox"]))
        for _text, _size, _origin, _dx, _dy, bbox in spans:
            page.add_redact_annot(pymupdf.Rect(bbox))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        shape = page.new_shape()
        for text, size, (ox, oy), dx, dy, _bbox in spans:
            tp = TextPath((0, 0), text, size=size, prop=font)
            ang = math.atan2(-dy, dx)                    # counter-clockwise, y up
            ca, sa = math.cos(ang), math.sin(ang)
            for poly in tp.to_polygons():
                if len(poly) < 3:
                    continue
                pts = [pymupdf.Point(ox + x * ca - y * sa, oy - (x * sa + y * ca)) for x, y in poly]
                shape.draw_polyline(pts + pts[:1])
            shape.finish(color=(0, 0, 0), fill=(0, 0, 0), width=0)
        shape.commit()
    dst = Path(dst)
    doc.save(dst)
    return dst
