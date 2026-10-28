"""R5 - Layout and sheet type (vector).

Frame (largest closed rectangle covering >= 90% of the page), title block
(text block with title keywords), plan box (extent of walls), tables (R12),
and the sheet type by regex over title-block and large text.
"""

from __future__ import annotations

import re

from ..schema import Element, Layout, Sheet
from .text_classify import normalise

SHEET_TYPES = [  # precedence order
    ("schedule", r"tableau|nomenclature|menuiseries|schedule"),
    ("structural", r"coffrage|ferraillage|fondations|structural|framing"),
    ("site", r"plan de masse|situation|site plan|cadastre"),
    ("floor_plan", r"\bplan\b|rez.de.chaussee|\brdc\b|etage|niveau|floor plan|ground floor"),
]


def _frame(sheet: Sheet) -> tuple | None:
    page = sheet.width * sheet.height
    if page <= 0 or sheet.coord_unit != "paper_mm":
        return None
    best = None
    for p in sheet.primitives:
        if p.kind == "polygon" and len(p.pts) == 4:
            xs, ys = [q[0] for q in p.pts], [q[1] for q in p.pts]
            a = (max(xs) - min(xs)) * (max(ys) - min(ys))
            if a >= 0.9 * page * 0.81 and (best is None or a > best[0]):   # >= 90% of each side
                best = (a, (min(xs), min(ys), max(xs), max(ys)))
    return best[1] if best else None


def title_block_box(sheet: Sheet) -> tuple | None:
    tb = [t for t in sheet.texts if t.kind == "title_block"]
    if not tb:
        return None
    pad = max((t.height or 0) for t in tb) * 2 or 1.0
    return (min(t.bbox[0] for t in tb) - pad, min(t.bbox[1] for t in tb) - pad,
            max(t.bbox[2] for t in tb) + pad, max(t.bbox[3] for t in tb) + pad)


def sheet_type(sheet: Sheet, walls: list[Element]) -> str:
    texts = [t for t in sheet.texts if t.kind == "title_block"]
    if sheet.texts:
        hmax = max((t.height or 0) for t in sheet.texts)
        texts += [t for t in sheet.texts if (t.height or 0) >= 0.8 * hmax]
    blob = " ".join(normalise(t.text) for t in texts)
    for name, pat in SHEET_TYPES:
        if re.search(pat, blob):
            return name
    n_walls = sum(1 for w in walls if w.cls == "wall")
    return "floor_plan" if n_walls >= 4 else "unknown"


def classify_sheet_text(blob: str) -> str:
    t = normalise(blob)
    for name, pat in SHEET_TYPES:
        if re.search(pat, t):
            return name
    return "other"


def build_layout(sheet: Sheet, walls: list[Element], tables: list[tuple]) -> Layout:
    plan_box = None
    ws = [w for w in walls if w.cls == "wall"]
    if ws:
        xs = [p[0] for w in ws for p in w.geom]
        ys = [p[1] for w in ws for p in w.geom]
        plan_box = (min(xs), min(ys), max(xs), max(ys))
    return Layout(frame=_frame(sheet), plan_box=plan_box, title_block=title_block_box(sheet), tables=list(tables))
