"""A Sheet that holds only the text of a PDF page, as the PDF reader makes it (y up, paper millimetres): enough for the readers of
annotate/schedules.py, which look at text alone. Used to compare the old reader and the general one on the same page."""

from __future__ import annotations

MM = 25.4 / 72.0


def text_sheet(page, sheet_id: str):
    import pymupdf

    from ..ingest.pdf_backend import PyMuPdfBackend
    from ..schema import Sheet

    rot = page.rotation_matrix
    H = page.rect.height

    def to_sheet(pt):
        q = pymupdf.Point(pt) * rot
        return (round(q.x * MM, 3), round(H * MM - q.y * MM, 3))

    texts = PyMuPdfBackend._texts(page, sheet_id, to_sheet, rot)
    return Sheet(id=sheet_id, source_file="x", page=0, mode="vector", coord_unit="paper_mm", width=page.rect.width * MM,
                 height=page.rect.height * MM, texts=texts)
