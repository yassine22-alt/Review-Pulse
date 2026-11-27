"""Everything of a drawing set that a requirement can be matched against, each piece saying where it sits.

A note read on its own often does not say what it is about: "all fans to be vented to the exterior" matters differently in an
HVAC plan and in an elevation, and a requirement such as "location of the air handler" may be answered by no sentence at all,
only by there being an HVAC plan. So the search is given three kinds of piece:

  * a note, searched together with the titles of its sheet and of the drawing it stands in (contextual retrieval: the piece
    is indexed with where it comes from, and shown as it is written);
  * a drawing (plan, section, elevation, detail, schedule, legend, notes block), by its title;
  * a sheet, by its title and the titles of its drawings.

Titles and drawings come from the drawing set model (``drawingset``), notes and their places from ``passages``. Nothing here
knows what any piece is about."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .passages import Passage, _union, set_passages, sheet_passages

PT_PER_MM = 72 / 25.4
WATERMARK_SHARE = 0.3          # a "drawing title" found on this share of the sheets is a stamp or watermark, not a title


@dataclass(frozen=True)
class Unit:
    page: int                                          # sheet number in the file, from 1
    kind: str                                          # note | view | sheet
    text: str                                          # what a person is shown
    search: str                                        # what is matched: the text with where it comes from
    box: tuple[float, float, float, float] | None = None   # sheet space (mm, y up); None: the sheet or drawing as a whole
    sheet: str = ""                                    # id of the sheet model, so a person can be taken there
    times: int = 1                                     # how often the same words stand on this sheet


def _inside(view_box, x: float, y: float) -> bool:
    return view_box[0] <= x <= view_box[2] and view_box[1] <= y <= view_box[3]


def _view_of(views, passage, height_mm: float):
    """The smallest drawing whose frame holds the middle of the note. Frames are in page points, y down; notes in mm, y up."""
    if passage.box is None:
        return None
    x = (passage.box[0] + passage.box[2]) / 2 * PT_PER_MM
    y = (height_mm - (passage.box[1] + passage.box[3]) / 2) * PT_PER_MM
    holding = [v for v in views if _inside(v.bbox, x, y)]
    return min(holding, key=lambda v: (v.bbox[2] - v.bbox[0]) * (v.bbox[3] - v.bbox[1]), default=None)


def _clean(title: str | None) -> str:
    return " ".join((title or "").split()).strip(" :")


def _drawings(drawing_set):
    """(sheets by page, and for a sheet its titled drawings), leaving out a "title" that stamps or watermarks put everywhere."""
    sheets = {s.index: s for s in drawing_set.sheets} if drawing_set is not None else {}
    stamped: Counter = Counter()
    for s in sheets.values():
        stamped.update({_clean(v.title).casefold() for v in s.views if _clean(v.title)})
    common = {t for t, n in stamped.items() if len(sheets) >= 4 and n > WATERMARK_SHARE * len(sheets)}
    return sheets, lambda sheet: [v for v in sheet.views if _clean(v.title) and _clean(v.title).casefold() not in common]


def evidence_units(models, drawing_set=None) -> list[Unit]:
    """``models``: the sheet models of the set; ``drawing_set``: its drawing set model, or None (then notes only)."""
    by_id = {m.sheet.id: m for m in models}
    sheets, views_of = _drawings(drawing_set)
    out: list[Unit] = []
    for p in set_passages(models):
        model = by_id[p.sheet]
        sheet = sheets.get(model.sheet.page)
        where = []
        if sheet is not None:
            view = _view_of(views_of(sheet), p, model.sheet.height)
            where = [t for t in (_clean(sheet.title), _clean(view.title) if view else "") if t]
        search = f"{' / '.join(where)}: {p.text}" if where else p.text
        out.append(Unit(model.sheet.page + 1, "note", p.text, search, p.box, p.sheet))
    for index, sheet in sorted(sheets.items()):
        title, views = _clean(sheet.title), views_of(sheet)
        for v in views:
            named = f"{v.kind} drawing: {_clean(v.title)}" if v.kind not in ("unknown", "other") else f"drawing: {_clean(v.title)}"
            out.append(Unit(index + 1, "view", _clean(v.title), f"{title} / {named}" if title else named))
        listed = "; ".join(dict.fromkeys(_clean(v.title) for v in views))[:600]
        if title or listed:
            out.append(Unit(index + 1, "sheet", title or listed[:80], f"sheet {title}. drawings on it: {listed}"))
    return out


LABEL_CHARS = 60                # longer than this is a statement, which the note search already reads
WORD = re.compile(r"[^\W\d_]{3,}")   # three letters in a row, in any alphabet: marks such as S6, K1 or R-50 are not words
EXAMPLES = 6


def _frame_mm(bbox, height_mm: float) -> tuple[float, float, float, float]:
    """A drawing frame (page points, y down) in sheet millimetres, y up."""
    return (bbox[0] / PT_PER_MM, height_mm - bbox[3] / PT_PER_MM, bbox[2] / PT_PER_MM, height_mm - bbox[1] / PT_PER_MM)


def _rows(texts) -> list[Passage]:
    """The lines of a table: every run at one height is one row, across the columns a note search keeps apart."""
    runs = sorted((t for t in texts if t.text.strip()), key=lambda t: (-(t.bbox[1] + t.bbox[3]) / 2, t.bbox[0]))
    rows: list[list] = []
    for t in runs:
        mid, height = (t.bbox[1] + t.bbox[3]) / 2, t.height or abs(t.bbox[3] - t.bbox[1]) or 1.0
        if rows and abs((rows[-1][0].bbox[1] + rows[-1][0].bbox[3]) / 2 - mid) <= 0.5 * height:
            rows[-1].append(t)
        else:
            rows.append([t])
    out = []
    for row in rows:
        row.sort(key=lambda t: t.bbox[0])
        if len(row) > 1:
            box = (min(t.bbox[0] for t in row), min(t.bbox[1] for t in row), max(t.bbox[2] for t in row),
                   max(t.bbox[3] for t in row))
            out.append(Passage("", " | ".join(" ".join(t.text.split()) for t in row), box))
    return out


def _located(model, title: str, views, kind: str, text: str, box, times: int = 1) -> Unit:
    view = _view_of(views, Passage("", text, box), model.sheet.height)
    where = " / ".join(t for t in (title, _clean(view.title) if view else "") if t)
    return Unit(model.sheet.page + 1, kind, text, f"{where}: {text}" if where else text, box, model.sheet.id, times)


def _measured(model, title: str, views, texts) -> list[Unit]:
    """One piece per drawing that carries written measurements; those inside no titled drawing count for the sheet."""
    groups: dict[str, tuple] = {}
    for t in texts:
        if t.kind == "dimension":
            box = tuple(t.bbox)
            view = _view_of(views, Passage("", t.text, box), model.sheet.height)
            groups.setdefault(view.id if view else "", (view, []))[1].append((" ".join(t.text.split()), box))
    out = []
    for view, measures in groups.values():
        name = f"the drawing {_clean(view.title)}" if view else f"the sheet {title}" if title else "this sheet"
        shown = ", ".join(list(dict.fromkeys(m for m, _ in measures))[:EXAMPLES])
        noun = "dimension" if len(measures) == 1 else "dimensions"
        words = f"{len(measures)} written {noun} on {name}, such as {shown}"
        out.append(Unit(model.sheet.page + 1, "dimensions", words, f"{title} / {words}" if title else words,
                        _union([b for _, b in measures]), model.sheet.id))
    return out


def written_units(models, drawing_set=None) -> list[Unit]:
    """What is written on the drawings that is not a sentence, each piece searched with the titles of where it stands:

      label       a short text (a room or equipment name, a mark with a word in it), once per sheet, with its place;
      row         a line of a table inside a drawing titled as a schedule;
      dimensions  one per drawing that carries written measurements: how many, the first few, and where they stand.

    Nothing rests on the classifier's guess of what a short text is (it reads room names, codes and values alike), only on
    its reading of measurements and of the title block."""
    sheets, views_of = _drawings(drawing_set)
    said = {p.text.casefold() for p in set_passages(models)}
    out: list[Unit] = []
    for model in sorted(models, key=lambda m: m.sheet.page):
        sheet = sheets.get(model.sheet.page)
        views = views_of(sheet) if sheet is not None else []
        title = _clean(sheet.title) if sheet is not None else ""
        texts = [t for t in model.sheet.texts if t.text.strip() and t.kind != "title_block"]
        seen: dict[str, list] = {}
        for p in sheet_passages(model.sheet.id, texts, skip={"dimension"}, min_letters=3):
            if len(p.text) <= LABEL_CHARS and WORD.search(p.text) and p.text.casefold() not in said:
                seen.setdefault(p.text.casefold(), []).append(p)
        out += [_located(model, title, views, "label", ps[0].text, ps[0].box, len(ps)) for ps in seen.values()]
        for view in [v for v in views if v.kind == "schedule"]:
            frame = _frame_mm(view.bbox, model.sheet.height)
            inside = [t for t in texts if _inside(frame, (t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2)]
            out += [_located(model, title, views, "row", r.text, r.box) for r in _rows(inside) if WORD.search(r.text)]
        out += _measured(model, title, views, texts)
    return out


def sheets_in_order(ranked: list[Unit], top: int = 3) -> list[int]:
    """Sheets by their best piece: the order in which they first appear among the ranked pieces (a sheet with many weak pieces
    does not outrank a sheet with one strong one)."""
    return list(dict.fromkeys(u.page for u in ranked))[:top]
