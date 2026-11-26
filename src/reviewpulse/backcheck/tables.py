"""Schedule cell diff: the tables of two aligned pages read with the schedule reader, rows matched by their tag, cells compared."""

from __future__ import annotations

from dataclasses import dataclass, field

from .snapshot import BBox, PageSnap

TAG_OK = 0.0


@dataclass
class Cell:
    text: str
    meaning: str
    header: str
    value_si: float | None


@dataclass
class Table:
    title: str
    kind: str
    headers: tuple[str, ...]
    bbox: BBox
    rows: dict[str, dict[str, Cell]] = field(default_factory=dict)       # tag -> header -> cell


@dataclass
class CellChange:
    table: str
    tag: str
    header: str
    meaning: str
    old_text: str
    new_text: str
    old_si: float | None
    new_si: float | None
    box_old: BBox | None
    box_new: BBox | None

    def describe(self) -> str:
        if not self.old_text:
            return f"row {self.tag} added ({self.header}: {self.new_text})"
        if not self.new_text:
            return f"row {self.tag} removed ({self.header}: {self.old_text})"
        return f"{self.table or 'table'} {self.tag} {self.header}: {self.old_text} -> {self.new_text}"


def read_tables(pdf: str, page_index: int) -> list[Table]:
    import pymupdf

    from ..schedules.reader import read_page_tables

    try:
        with pymupdf.open(pdf) as doc:
            typed = read_page_tables(doc[page_index], f"p{page_index + 1}")
    except Exception:
        return []
    out = []
    for t in typed:
        tb = Table(t.title, t.kind, tuple(c.header for c in t.columns), tuple(float(v) for v in t.bbox))
        for r, tag in enumerate(t.tags):
            if not tag or tag in tb.rows:
                continue
            row: dict[str, Cell] = {}
            for ci, col in enumerate(t.columns):
                cell = t.rows[r][ci] if ci < len(t.rows[r]) else ""
                row[col.header] = Cell(cell, col.meaning or "", col.header, None)
            tb.rows[tag] = row
        for c in t.candidates:
            if c.entity_tag in tb.rows and c.header_text in tb.rows[c.entity_tag]:
                tb.rows[c.entity_tag][c.header_text].value_si = c.value_si
                if c.meaning:
                    tb.rows[c.entity_tag][c.header_text].meaning = c.meaning
        out.append(tb)
    return out


def _row_box(page: PageSnap, table: BBox, tag: str) -> BBox | None:
    for w in page.words:
        if w.text == tag and table[0] - 4 <= (w.bbox[0] + w.bbox[2]) / 2 <= table[2] and table[1] - 4 <= (w.bbox[1] + w.bbox[3]) / 2 <= table[3] + 4:
            return (table[0], w.bbox[1] - 1, table[2], w.bbox[3] + 1)
    return None


def diff_tables(old: list[Table], new: list[Table], a: PageSnap, b: PageSnap) -> list[CellChange]:
    """Tables are paired by title, else by identical column headers. Rows by tag. A tag in only one table is a row change."""
    out: list[CellChange] = []
    used: set[int] = set()
    for t in old:
        match = None
        for j, u in enumerate(new):
            if j not in used and ((t.title and t.title == u.title) or (t.headers == u.headers and not t.title)):
                match = j
                break
        if match is None:
            for j, u in enumerate(new):
                if j not in used and t.headers == u.headers:
                    match = j
                    break
        if match is None:
            continue
        used.add(match)
        u = new[match]
        for tag in sorted(set(t.rows) | set(u.rows)):
            ro, rn = t.rows.get(tag), u.rows.get(tag)
            bo, bn = _row_box(a, t.bbox, tag), _row_box(b, u.bbox, tag)
            for h in (ro or rn):
                co, cn = (ro or {}).get(h), (rn or {}).get(h)
                to, tn = co.text if co else "", cn.text if cn else ""
                if to != tn:
                    meaning = (cn or co).meaning
                    out.append(CellChange(t.title, tag, h, meaning, to, tn, co.value_si if co else None,
                                          cn.value_si if cn else None, bo, bn))
    return out


def row_values(tables: list[Table], tag: str) -> dict[str, Cell]:
    for t in tables:
        if tag in t.rows:
            return t.rows[tag]
    return {}


def all_tags(tables: list[Table]) -> set[str]:
    return {tag for t in tables for tag in t.rows}
