"""Parts of the set read once all sheets have their views: the sheet index against the title blocks, and the legends."""

from __future__ import annotations

import re

from .model import IndexEntry, LegendEntry, Sheet
from .pagedata import Line, PageData
from .views import box_of, gap, in_view, owner_of, union
from .vocab import Vocab, fold, norm_id, plain

_COMBINED = re.compile(r"^(?P<id>[A-Za-z]{1,3}[-. ]?\d{1,3}(?:[.-]\d{1,2})?[A-Za-z]?)\s*[-:.\u2013)]*\s+(?P<t>.*[A-Za-z]{3}.*)$")
_COMBINED_R = re.compile(r"^(?P<t>.*[A-Za-z]{3}.*?)\s+(?P<id>[A-Z]{1,3}[-. ]?\d{1,3}(?:[.-]\d{1,2})?[A-Z]?)$")


def read_index(pages: dict[int, PageData], sheets: list[Sheet], vocab: Vocab) -> list[IndexEntry]:
    """Entries (sheet number, title) of every view of kind index, paired by row."""
    entries: list[IndexEntry] = []
    for sh in sheets:
        pg = pages[sh.index]
        for v in sh.views:
            if v.kind != "index":
                continue
            region = v.title_bbox or v.bbox
            ls = [ln for ln in pg.lines if region[0] <= ln.cx <= region[2] and region[1] <= ln.cy <= region[3]
                  and ln.horizontal and fold(ln.text) != fold(v.title)]
            ids = [ln for ln in ls if vocab.letter_id.match(plain(ln.text).upper().strip(" .:"))
                   or vocab.number_id.match(plain(ln.text).strip(" .:"))]
            texts = [ln for ln in ls if ln not in ids and len(re.findall(r"[A-Za-z]", ln.text)) >= 3]
            used: set[int] = set()
            for ln in ids:
                row = [t for t in texts if id(t) not in used and abs(t.cy - ln.cy) <= 0.6 * max(t.h, ln.h)]
                if row:
                    t = min(row, key=lambda t: gap(box_of(t), box_of(ln)))
                    used.add(id(t))
                    entries.append(IndexEntry(plain(ln.text).strip(" .:"), plain(t.text), sh.index, view=v.id))
            for t in texts:
                if id(t) in used:
                    continue
                m = _COMBINED.match(plain(t.text)) or _COMBINED_R.match(plain(t.text))
                if m and not vocab.kind_regex["index"].search(fold(t.text)):
                    entries.append(IndexEntry(m.group("id").strip(), m.group("t").strip(), sh.index, view=v.id))
    return entries


def validate_untitled_indexes(entries: list[IndexEntry], sheets: list[Sheet]) -> list[IndexEntry]:
    """A list with no heading is an index only if most of its rows are a sheet of the set with a title alike the one in its title block. Else it is a numbered list (keynotes,
    a legend of parts) and is turned into a legend view; its rows are not index entries."""
    keys = {norm_id(s.number): s for s in sheets if s.number}
    by_view: dict[str, list[IndexEntry]] = {}
    for e in entries:
        by_view.setdefault(e.view, []).append(e)
    drop: set[str] = set()
    for sh in sheets:
        for v in sh.views:
            if v.kind == "index" and v.title.startswith("(sheet index"):
                es = by_view.get(v.id, [])
                hit = sum(1 for e in es if norm_id(e.number) in keys and _sim(e.title, keys[norm_id(e.number)].title) >= 0.5)
                if not es or hit < 0.5 * len(es):
                    v.kind, v.title = "legend", "(numbered list, not a sheet index)"
                    drop.add(v.id)
    return [e for e in entries if e.view not in drop]


def _sim(a: str, b: str | None) -> float:
    wa, wb = _words(a), _words(b or "")
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", fold(t)) if len(w) > 1}


def compare_index(entries: list[IndexEntry], sheets: list[Sheet]) -> list[str]:
    """Mark each entry against the title blocks; return sheets that carry a number but are not listed."""
    by_key: dict[str, Sheet] = {}
    for s in sheets:
        if s.number:
            by_key.setdefault(norm_id(s.number), s)
    seen: set[str] = set()
    for e in entries:
        s = by_key.get(norm_id(e.number))
        if s is None:
            e.status = "not in set"
            continue
        seen.add(norm_id(s.number))
        a, b = _words(e.title), _words(s.title or "")
        sim = len(a & b) / len(a | b) if a | b else 0.0
        e.matched_sheet, e.similarity = s.index, round(sim, 2)
        e.status = "match" if sim >= 0.5 else "title differs"
    listed = {norm_id(e.number) for e in entries}
    return [s.number for s in sheets if s.number and norm_id(s.number) not in listed]


def read_legends(pages: dict[int, PageData], sheets: list[Sheet], vocab: Vocab) -> list[LegendEntry]:
    """Every row of a legend view: its words and the drawn symbol next to them, kept as a region of the page."""
    out: list[LegendEntry] = []
    for sh in sheets:
        pg = pages[sh.index]
        for v in sh.views:
            if v.kind != "legend":
                continue
            ls = [ln for ln in pg.lines if in_view(ln, v) and owner_of(ln.cx, ln.cy, sh.views) is v and ln.horizontal
                  and fold(ln.text) != fold(v.title) and len(re.findall(r"[A-Za-z]", ln.text)) >= 2]
            rects = pg.rects
            for ln in ls:
                sym = []
                if len(rects):
                    h = ln.h
                    sel = ((rects[:, 2] <= ln.x0 + 0.5 * h) & (rects[:, 2] >= ln.x0 - 14 * h)
                           & (rects[:, 3] >= ln.cy - 1.6 * h) & (rects[:, 1] <= ln.cy + 1.6 * h)
                           & ((rects[:, 2] - rects[:, 0]) <= 12 * h) & ((rects[:, 3] - rects[:, 1]) <= 4 * h))
                    sym = rects[sel]
                if len(sym):
                    sb = (float(sym[:, 0].min()), float(sym[:, 1].min()), float(sym[:, 2].max()), float(sym[:, 3].max()))
                    out.append(LegendEntry(sh.index, v.id, plain(ln.text), sb, int(len(sym)), union([sb, box_of(ln)])))
                else:
                    out.append(LegendEntry(sh.index, v.id, plain(ln.text), None, 0, box_of(ln)))
    return out


def line_text(lines: list[Line]) -> str:
    return " ".join(plain(ln.text) for ln in lines)
