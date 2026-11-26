"""Build the drawing set model from the pages of a set."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .model import DrawingSet
from .pagedata import PageData, from_pdf
from .refs import parse_bubbles, parse_text_callouts, resolve, sheet_shapes
from .setparts import compare_index, read_index, read_legends, validate_untitled_indexes
from .views import build_sheet, find_title_block, title_block_texts
from .vocab import Vocab, load_vocab, plain

METHODS = ("xycut", "voronoi", "sheet")


def build_drawing_set(pages: list[PageData], name: str = "set", method: str = "xycut", vocab: Vocab | None = None) -> DrawingSet:
    vocab = vocab or load_vocab()
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}")
    sheets, by_index = [], {}
    # what a title block says on most sheets (project, address, firm) is the set's, not the sheet's: it cannot be a sheet title
    seen = Counter(t for pg in pages for t in title_block_texts(pg, vocab))
    constants = frozenset(t for t, n in seen.items() if len(pages) >= 3 and n >= 0.6 * len(pages))
    for pg in pages:
        sheet, _ = build_sheet(pg, vocab, method, constants)
        sheets.append(sheet)
        by_index[pg.index] = pg
    shapes = sheet_shapes(sheets)
    callouts = []
    known = {plain(s.number).upper().replace(" ", "") for s in sheets if s.number}
    for pg, sheet in zip(pages, sheets, strict=True):
        tb = sheet.title_block
        callouts += parse_text_callouts(pg, vocab, tb)
        callouts += parse_bubbles(pg, vocab, tb, known)
    callouts = [c for c in callouts if not _is_own_tag(c, sheets)]
    index = validate_untitled_indexes(read_index(by_index, sheets, vocab), sheets)
    skip = {v.id for s in sheets for v in s.views if v.kind in ("legend", "index")}
    resolve(callouts, sheets, shapes, skip)
    missing = compare_index(index, sheets)
    legend = read_legends(by_index, sheets, vocab)
    return DrawingSet(name=name, method=method, sheets=sheets, callouts=callouts, legend=legend, index=index,
                      index_missing=missing, shapes=sorted(shapes))


def _is_own_tag(c, sheets) -> bool:
    """A number and sheet number stacked inside a view's own title bar name the view, they do not point to it."""
    if c.grammar != "bubble":
        return False
    sh = next(s for s in sheets if s.index == c.sheet)
    cx, cy = (c.where[0] + c.where[2]) / 2, (c.where[1] + c.where[3]) / 2
    for v in sh.views:
        t = v.title_bbox
        if t is None:
            continue
        m = 0.5 * (t[3] - t[1])
        if t[0] - m <= cx <= t[2] + m and t[1] - m <= cy <= t[3] + m:
            return True
    return False


def build_from_pdf(path: str | Path, method: str = "xycut", ocr_pages: dict[int, list] | None = None) -> DrawingSet:
    """The model of a PDF set. `ocr_pages` maps a page index to OCR `Line`s already available (merged into the text layer)."""
    from .pagedata import merge_ocr

    pages = from_pdf(path)
    if ocr_pages:
        pages = [merge_ocr(p, ocr_pages[p.index]) if p.index in ocr_pages else p for p in pages]
    return build_drawing_set(pages, Path(path).stem, method)


__all__ = ["METHODS", "build_drawing_set", "build_from_pdf", "find_title_block"]
