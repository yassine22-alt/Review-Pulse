"""Every table on a sheet becomes rows of an entity kind, each column typed by the meaning of its header and its unit.

Input is the text layer (words with boxes) of a PDF page, a DXF layout or a Sheet; a PDF page also gives the ruled tables
(pymupdf finds the grid of rules), the others are found from the words alone: a line of words is cut into cells where the gap is
wide, a line whose cells name at least two different meanings is a header, and the lines under it that line up with its columns
are the rows. Both ways end in the same RawTable and the same typing.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from ..annotate.notes import parse_fire_minutes
from ..interpreter.units import UnitError, convert, is_unit, to_si
from . import values
from .model import Candidate, Column, TypedTable
from .vocab import (
    HeaderMatch,
    canonical_unit,
    dim_of,
    fold,
    header_unit,
    match_alternatives,
    match_header,
    tokens,
    vocabulary,
)

GAP_K = 0.6              # a gap wider than this many line heights ends a cell
TABLE_GAP_K = 20.0       # a gap wider than this many line heights separates two tables side by side
MIN_SCORE = 0.6          # a header match below this does not type the column
KIND_ORDER = ["walls", "finishes", "doors", "windows", "fixtures", "rooms"]
LENGTH_GUESS = ((3.5, "m"), (350.0, "cm"), (float("inf"), "mm"))


@dataclass
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass
class Cell:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    cells: list[Cell]
    top: float
    bottom: float
    h: float


@dataclass
class RawTable:
    method: str
    header: list[tuple[str, float, float]]      # text, x0, x1 of each column
    rows: list[list[str]]
    bbox: tuple[float, float, float, float]
    title: str = ""
    row_tops: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------------------------- input

def words_from_page(page) -> list[Word]:
    out = []
    for w in page.get_text("words"):
        x0, y0, x1, y1, t = w[:5]
        if not t.strip() or (y1 - y0) > 3 * max(x1 - x0, 1e-6) and len(t) > 1:     # a vertical word is not read in a row
            continue
        out.append(Word(t, x0, y0, x1, y1))
    return out


def words_from_sheet(sheet) -> list[Word]:
    """Text items of a Sheet (y up) as words (y down). A run of two spaces or more inside an item is a cell gap."""
    out = []
    for t in sheet.texts:
        if abs(t.rotation_deg % 180) > 5 or not t.text.strip():
            continue
        x0, y0, x1, y1 = t.bbox
        top, bottom = -y1, -y0
        n = max(len(t.text), 1)
        for m in re.finditer(r"\S+(?: \S+)*", t.text):
            out.append(Word(m.group(0), x0 + (x1 - x0) * m.start() / n, top, x0 + (x1 - x0) * m.end() / n, bottom))
    return out


# ---------------------------------------------------------------------------------------------------------------- lines

def build_lines(words: list[Word], gap_k: float = GAP_K) -> list[Line]:
    ws = sorted(words, key=lambda w: ((w.top + w.bottom) / 2, w.x0))
    rows: list[list[Word]] = []
    for w in ws:
        cy, h = (w.top + w.bottom) / 2, max(w.bottom - w.top, 1e-6)
        if rows:
            ref = rows[-1]
            rcy = statistics.mean((v.top + v.bottom) / 2 for v in ref)
            rh = statistics.median(v.bottom - v.top for v in ref)
            if abs(cy - rcy) <= 0.45 * min(h, rh):
                ref.append(w)
                continue
        rows.append([w])
    lines = []
    for r in rows:
        r.sort(key=lambda w: w.x0)
        h = statistics.median(w.bottom - w.top for w in r)
        cells: list[Cell] = []
        for w in r:
            if cells and w.x0 - cells[-1].x1 <= gap_k * h:
                c = cells[-1]
                c.text += " " + w.text
                c.x1, c.top, c.bottom = max(c.x1, w.x1), min(c.top, w.top), max(c.bottom, w.bottom)
            else:
                cells.append(Cell(w.text, w.x0, w.top, w.x1, w.bottom))
        lines.append(Line(cells, min(c.top for c in cells), max(c.bottom for c in cells), h))
    return lines


def _segments(line: Line) -> list[list[int]]:
    """Runs of cells of a line; a very wide gap starts another run (a second table beside the first)."""
    out: list[list[int]] = [[0]]
    for i in range(1, len(line.cells)):
        if line.cells[i].x0 - line.cells[i - 1].x1 > TABLE_GAP_K * line.h:
            out.append([i])
        else:
            out[-1].append(i)
    return out


# ---------------------------------------------------------------------------------------------------------------- header

def _typed(m: HeaderMatch) -> bool:
    return m.meaning is not None and m.score >= MIN_SCORE


def _is_header(texts: list[str]) -> bool:
    ms = [match_header(t) for t in texts]
    typed = [m.meaning for m in ms if _typed(m)]
    return len(texts) >= 2 and len(set(typed)) >= 2 and len(typed) >= max(2, 0.5 * len(texts))


def _unit_like(text: str) -> bool:
    inner = re.sub(r"^[\(\[\{]|[\)\]\}]$", "", text.strip())
    return bool(inner) and canonical_unit(inner) is not None and not re.search(r"\d{2,}", inner)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return min(a1, b1) - max(a0, b0)


def _merge_above(line: Line, prev: Line | None, hdr_cells: list[Cell]) -> tuple[list[tuple[str, float, float]], bool]:
    """The header cells, each with the words stacked above it when that makes the meaning clearer ('Fire' over 'Rating')."""
    base = [(c.text, c.x0, c.x1) for c in hdr_cells]
    if prev is None or not prev.cells or line.top - prev.bottom > 0.8 * line.h:
        return base, False
    out, used = [], False
    for text, x0, x1 in base:
        over = [c for c in prev.cells if _overlap(c.x0, c.x1, x0, x1) > 0.3 * min(c.x1 - c.x0, x1 - x0)]
        if len(over) == 1 and not re.search(r"\d", over[0].text):
            combined = over[0].text + " " + text
            a, b = match_header(text), match_header(combined)
            if _typed(b) and (not _typed(a) or b.score >= a.score or a.meaning != b.meaning):
                out.append((combined, min(x0, over[0].x0), max(x1, over[0].x1)))
                used = True
                continue
        out.append((text, x0, x1))
    return out, used


def _merge_below(cols: list[tuple[str, float, float]], cells: list[Cell]) -> list[tuple[str, float, float]] | None:
    """The header with the line under it joined on, or None when that line is not a header line (it has numbers, or joining
    it types no column better). A line of units ('(mm)') always joins."""
    if any(re.search(r"\d", re.sub(r"[\(\[][^\)\]]*[\)\]]", "", c.text)) for c in cells):
        return None
    if all(_unit_like(c.text) for c in cells):
        return [(f"{t} {' '.join(c.text for c in cells if _overlap(c.x0, c.x1, x0, x1) > 0)}".strip(), x0, x1) for t, x0, x1 in cols]
    out, better = [], 0
    for c in cells:                                    # a column with nothing on the first header line: "Tag" under a blank
        if not any(_overlap(c.x0, c.x1, k[1], k[2]) > 0 for k in cols):
            if not _typed(match_header(c.text)):
                return None
            out.append((c.text, c.x0, c.x1))
            better += 1
    for t, x0, x1 in cols:
        over = [c for c in cells if _overlap(c.x0, c.x1, x0, x1) > 0.3 * min(c.x1 - c.x0, x1 - x0)]
        if len(over) == 1:
            combined = f"{t} {over[0].text}"
            a, b = match_header(t), match_header(combined)
            if _typed(b) and (b.score >= a.score or not _typed(a)):
                better += int(b.meaning != a.meaning or not _typed(a) or b.score > a.score)
                out.append((combined, min(x0, over[0].x0), max(x1, over[0].x1)))
                continue
            return None
        if over:
            return None
        out.append((t, x0, x1))
    return sorted(out, key=lambda k: k[1]) if better else None


def _assign(cell: Cell, cols: list[tuple[str, float, float]]) -> int:
    ov = [_overlap(cell.x0, cell.x1, c[1], c[2]) for c in cols]
    best = max(range(len(cols)), key=ov.__getitem__)
    if ov[best] > 0:
        return best
    return min(range(len(cols)), key=lambda i: min(abs(cell.cx - (cols[i][1] + cols[i][2]) / 2), abs(cell.x0 - cols[i][1]),
                                                   abs(cell.x1 - cols[i][2])))


def scan_unruled(lines: list[Line]) -> list[RawTable]:
    used: set[tuple[int, int]] = set()
    tables: list[RawTable] = []
    for li, line in enumerate(lines):
        for seg in _segments(line):
            if any((li, ci) in used for ci in seg) or len(seg) < 2:
                continue
            hdr_cells = [line.cells[i] for i in seg]
            if not _is_header([c.text for c in hdr_cells]):
                continue
            prev = lines[li - 1] if li else None
            if prev is not None:
                prev = Line([c for c in prev.cells if any(_overlap(c.x0, c.x1, hc.x0, hc.x1) > 0 for hc in hdr_cells)],
                            prev.top, prev.bottom, prev.h)
            cols, merged = _merge_above(line, prev, hdr_cells)
            for ci in seg:
                used.add((li, ci))
            start = li + 1
            while start < len(lines):                      # a second header line under the first: units, or "Height" under "Ceiling"
                nxt = lines[start]
                lo_x, hi_x = cols[0][1] - 14 * line.h, cols[-1][2] + 14 * line.h
                cs = [(ci, c) for ci, c in enumerate(nxt.cells) if lo_x <= c.cx <= hi_x and (
                    any(_overlap(c.x0, c.x1, k[1], k[2]) > 0 for k in cols) or _typed(match_header(c.text)))]
                if not cs or nxt.top - lines[start - 1].bottom > 0.8 * line.h:
                    break
                merged_cols = _merge_below(cols, [c for _, c in cs])
                if merged_cols is None:
                    break
                cols = merged_cols
                for ci, _ in cs:
                    used.add((start, ci))
                start += 1
            lo, hi = cols[0][1] - 2 * line.h, cols[-1][2] + 2 * line.h
            rows: list[list[str]] = []
            tops: list[float] = []
            gaps: list[float] = []
            last_bottom = lines[start - 1].bottom
            bottom_all = line.bottom
            for lj in range(start, len(lines)):
                ln = lines[lj]
                inside = [(ci, c) for ci, c in enumerate(ln.cells) if lo <= c.cx <= hi and (lj, ci) not in used]
                gap = ln.top - last_bottom
                limit = max(2.5 * statistics.median(gaps), 1.5 * line.h) if gaps else 6.0 * line.h
                if gap > limit:
                    break
                if not inside:                                 # text of another block on the same height: not a row, not the end
                    continue
                texts = [c.text for _, c in inside]
                if len(texts) >= 2 and _is_header(texts) and not any(re.search(r"\d", t) for t in texts):
                    break
                grid = [""] * len(cols)
                for _, c in inside:
                    k = _assign(c, cols)
                    grid[k] = (grid[k] + " " + c.text).strip()
                if len(inside) < 2:
                    c0 = inside[0][1]
                    if rows and (c0.text[:1].islower() or c0.text[:1] in "(-,&") and _wrap_ok(rows[-1], grid):
                        for k, t in enumerate(grid):
                            if t:
                                rows[-1][k] = (rows[-1][k] + " " + t).strip()
                        for ci, _ in inside:
                            used.add((lj, ci))
                        gaps.append(gap)
                        last_bottom = ln.bottom
                        bottom_all = ln.bottom
                        continue
                    break
                rows.append(grid)
                tops.append(ln.top)
                for ci, _ in inside:
                    used.add((lj, ci))
                gaps.append(gap)
                last_bottom = ln.bottom
                bottom_all = ln.bottom
            if len(rows) < 2 and not (len(rows) == 1 and values.looks_like_tag(rows[0][0])):
                continue
            title = _title_above(lines, li - (1 if merged else 0), cols)
            bbox = (min(c[1] for c in cols), line.top, max(c[2] for c in cols), bottom_all)
            tables.append(RawTable("unruled", cols, rows, bbox, title, tops))
    return tables


def _wrap_ok(prev_row: list[str], grid: list[str]) -> bool:
    return all(prev_row[k] for k, t in enumerate(grid) if t)


def _title_above(lines: list[Line], li: int, cols: list[tuple[str, float, float]], max_lines: int = 2) -> str:
    """The text above the header over the table's columns: a title may sit several lines up, with other blocks' lines between."""
    x0, x1 = cols[0][1], cols[-1][2]
    out: list[str] = []
    if not 0 <= li < len(lines):
        return ""
    ref_top = lines[li].top
    for j in range(li - 1, max(li - 1 - 40, -1), -1):
        ln = lines[j]
        if ref_top - ln.bottom > (6.0 if not out else 1.6) * ln.h:
            break
        texts = [c.text for c in ln.cells if _overlap(c.x0, c.x1, x0 - ln.h, x1 + ln.h) > 0]
        if not texts or len(texts) > 2 or len(" ".join(texts).split()) > 8:       # a sentence of notes is not a title
            continue
        out.append(" ".join(texts))
        ref_top = ln.top
        if len(out) >= max_lines:
            break
    return " | ".join(reversed(out))


# ---------------------------------------------------------------------------------------------------------------- ruled

def _sub_header(cols: list[tuple[str, float, float]], row: list[str]) -> list[tuple[str, float, float]] | None:
    """A row under the header that names the parts of a group ('DOOR' over 'WIDTH', 'HEIGHT', 'MATERIAL'): each part takes the
    group's name from the nearest header to its left. None when the row is data (it has numbers) or names nothing."""
    cells = [c for c in row if c]
    if len(cells) < 2 or any(re.search(r"\d", c) or len(c.split()) > 4 for c in cells):
        return None
    out, carry, typed = [], "", 0
    for (t, x0, x1), sub in zip(cols, row, strict=True):
        if t:
            carry = t
        if not sub:
            out.append((t, x0, x1))
            continue
        head = f"{carry} {sub}".strip() if (not t or t == carry) else f"{t} {sub}"
        m = match_header(head)
        if not _typed(m):
            alone = match_header(sub)
            head = sub if _typed(alone) else head
            m = alone if _typed(alone) else m
        typed += int(_typed(m))
        out.append((head, x0, x1))
    return out if typed >= 1 else None


def _cell_text(words: list[Word], box) -> str:
    """The words whose centre is inside a ruled cell, in reading order (the text of the file, not pymupdf's re-assembly)."""
    if not box:
        return ""
    inside = [w for w in words if box[0] - 0.5 <= (w.x0 + w.x1) / 2 <= box[2] + 0.5 and box[1] - 0.5 <= (w.top + w.bottom) / 2 <= box[3] + 0.5]
    if not inside:
        return ""
    h = statistics.median(w.bottom - w.top for w in inside)
    inside.sort(key=lambda w: ((w.top + w.bottom) / 2, w.x0))
    lines: list[list[Word]] = []
    for w in inside:
        if lines and abs((w.top + w.bottom) / 2 - (lines[-1][0].top + lines[-1][0].bottom) / 2) <= 0.5 * h:
            lines[-1].append(w)
        else:
            lines.append([w])
    return " ".join(" ".join(x.text for x in sorted(ln, key=lambda w: w.x0)) for ln in lines)


def ruled_tables(page, lines: list[Line], words: list[Word], max_drawings: int = 40000) -> list[RawTable]:
    """Tables drawn with rules, found by pymupdf from the lines of the page. Skipped on a page too heavy to analyse."""
    try:
        if len(page.get_drawings()) > max_drawings:
            return []
        try:
            found = page.find_tables(use_layout=False)       # the rules only: no layout model, so no extra weight and no GPU
        except TypeError:                                    # an older pymupdf has no layout model
            found = page.find_tables()
    except Exception:  # noqa: BLE001 - a failure of the finder must not stop the words reader
        return []
    out = []
    for tab in found.tables:
        geom = [r.cells for r in tab.rows]
        if len(geom) < 2 or len(geom[0]) < 2:
            continue
        sub = [w for w in words if tab.bbox[0] - 1 <= (w.x0 + w.x1) / 2 <= tab.bbox[2] + 1 and tab.bbox[1] - 1 <= (w.top + w.bottom) / 2 <= tab.bbox[3] + 1]
        rows = [[_cell_text(sub, box) for box in g] for g in geom]
        hi = None
        for i in range(min(3, len(rows))):
            if _is_header([c for c in rows[i] if c]):
                hi = i
                break
        if hi is None:
            continue
        ncol = len(rows[hi])
        cols = []
        for k in range(ncol):
            xs = [g[k] for g in geom[hi:hi + 1] if k < len(g) and g[k]]
            x0, x1 = (xs[0][0], xs[0][2]) if xs else (tab.bbox[0], tab.bbox[2])
            text = rows[hi][k]
            for j in range(hi):                          # rows above the header row stack on it ("Fire" over "Rating")
                if rows[j][k] and len([c for c in rows[j] if c]) > 1 and not re.search(r"\d", rows[j][k]):
                    text = (rows[j][k] + " " + text).strip()
            cols.append((text, x0, x1))
        body = rows[hi + 1:]
        while body and any(body[0]):
            if all(_unit_like(c) for c in body[0] if c):
                cols = [(f"{t} {body[0][k]}".strip(), x0, x1) for k, (t, x0, x1) in enumerate(cols)]
            else:
                sub = _sub_header(cols, body[0])
                if sub is None:
                    break
                cols = sub
            body = body[1:]
        body = [r for r in body if any(r)]
        if not body:
            continue
        title = " | ".join(" ".join(c for c in rows[j] if c) for j in range(hi) if len([c for c in rows[j] if c]) == 1)
        title = (title + " | " + _title_for_bbox(lines, tab.bbox)).strip(" |")
        out.append(RawTable("ruled", cols, body, tuple(tab.bbox), title))
    return out


def _title_for_bbox(lines: list[Line], bbox, max_lines: int = 2) -> str:
    out = []
    ref_top = bbox[1]
    for ln in sorted((ln for ln in lines if ln.bottom <= bbox[1] + 1.0), key=lambda ln: -ln.bottom):
        if ref_top - ln.bottom > (3.0 if not out else 1.6) * ln.h or len(ln.cells) > 2:
            break
        texts = [c.text for c in ln.cells if _overlap(c.x0, c.x1, bbox[0] - ln.h, bbox[2] + ln.h) > 0]
        if texts:
            out.append(" ".join(texts))
            ref_top = ln.top
            if len(out) >= max_lines:
                break
    return " | ".join(reversed(out))


# ---------------------------------------------------------------------------------------------------------------- typing

def _fire_like(text: str) -> bool:
    t = text.strip()
    return bool(t) and bool(re.search(r"\b(?:\d+\s*(?:-\s*\d+/\d+\s*)?(?:hr|hrs|hour|min|minute|h)s?|ei\s?\d+|rei\s?\d+|nr|f\d{2,3})\b", t, re.I))


def _type_columns(raw: RawTable) -> list[Column]:
    cols = []
    for k, (text, x0, x1) in enumerate(raw.header):
        cells = [r[k] for r in raw.rows if r[k]]
        m = match_header(text)
        if _typed(m) and cells and not _content_fits(dim_of(m.meaning), cells):     # "Plafond" over words is a finish, over numbers a height
            for alt in match_alternatives(text):
                if alt.score >= MIN_SCORE and _content_fits(dim_of(alt.meaning), cells):
                    m = alt
                    break
            else:
                m = HeaderMatch(None, 0.0, "none")           # the header names a quantity and the cells are words: not typed
        col = Column(k, text, m.meaning if _typed(m) else None, m.score if _typed(m) else 0.0, m.via if _typed(m) else "none",
                     dim_of(m.meaning) if _typed(m) else "text", x0=x0, x1=x1)
        if col.meaning is None and len(cells) >= 2:                     # an unknown header: what the cells themselves are
            if sum(_fire_like(c) for c in cells) >= 0.8 * len(cells):
                col.meaning, col.score, col.via, col.dim = "fire_rating", 0.5, "content", "time"
        cols.append(col)
    return cols


def _content_fits(dim: str, cells: list[str]) -> bool:
    numeric = sum(1 for c in cells if values.quantity(c) is not None or values.size(c) is not None or _fire_like(c)
                  or (dim == "time" and c.strip().lower() in {"-", "--", "n/a", "na", "none", "no", "non"}))
    if dim in ("length", "area", "volume", "mass", "power", "voltage", "ratio", "count", "size", "time"):
        return numeric >= 0.6 * len(cells)
    if dim == "text":
        return numeric <= 0.6 * len(cells)
    return True


def _tag_column(cols: list[Column], raw: RawTable, kind_hint_rooms: bool) -> int | None:
    order = ["room_number", "tag"] if kind_hint_rooms else ["tag", "room_number"]
    for meaning in order:
        cand = [c for c in cols if c.meaning == meaning]
        if cand:
            return max(cand, key=lambda c: c.score).index
    for k in range(min(2, len(cols))):                                  # no tag header: a left column of tag-like, distinct cells
        cells = [r[k] for r in raw.rows if r[k]]
        if len(cells) >= 2 and len(set(cells)) == len(cells) and all(values.looks_like_tag(c) for c in cells) \
                and cols[k].meaning is None:
            cols[k].meaning, cols[k].score, cols[k].via, cols[k].dim = "tag", 0.5, "content", "tag"
            return k
    for k in range(min(2, len(cols))):                                  # a schedule keyed by its first column ("TYPE": A, B, C)
        cells = [r[k] for r in raw.rows if r[k]]
        if len(cells) >= 2 and len(set(cells)) == len(cells) and all(values.looks_like_tag(c) for c in cells):
            return k
    return None


def _prefix(tag: str) -> str:
    m = re.match(r"[A-Za-z]+", tag.strip())
    return m.group(0).lower() if m else ""


def _kind(raw: RawTable, cols: list[Column], tags: list[str | None]) -> tuple[str, str]:
    vocab = vocabulary()
    title_t = set(tokens(raw.title))
    title_s = " " + fold(raw.title) + " "
    score: dict[str, float] = {}
    why: dict[str, set] = {}
    for kind, spec in vocab["kinds"].items():
        n = sum(1 for w in spec.get("title", []) if (" " + fold(w) + " ") in title_s or fold(w) in title_t)
        if n:
            score[kind] = score.get(kind, 0) + 3 * min(n, 2)
            why.setdefault(kind, set()).add("title")
    meanings = {c.meaning for c in cols if c.meaning}
    for kind, hints in vocab["kind_hints"].items():
        n = len(meanings & set(hints))
        if n:
            score[kind] = score.get(kind, 0) + 1.0 * n
            why.setdefault(kind, set()).add("columns")
    pre = [_prefix(t) for t in tags if t]
    if pre:
        for kind, spec in vocab["kinds"].items():
            share = sum(1 for p in pre if p and p in spec.get("prefix", [])) / len(pre)
            if share >= 0.7:
                score[kind] = score.get(kind, 0) + 1.0
                why.setdefault(kind, set()).add("tag prefix")
    if not score or max(score.values()) < 1.5:               # a tag prefix or a single hinting column alone does not name a kind
        return "other", "none"
    best = max(score.values())
    top = [k for k, v in score.items() if v == best]
    top.sort(key=lambda k: KIND_ORDER.index(k) if k in KIND_ORDER else 99)
    return top[0], "+".join(sorted(why[top[0]]))


def _guess_length_unit(vals: list[float]) -> str:
    mx = max(vals) if vals else 0.0
    return next(u for lim, u in LENGTH_GUESS if mx <= lim)


def _si(value: float, unit: str | None) -> float | None:
    if unit is None or not is_unit(unit):
        return None
    try:
        return to_si(value, unit)
    except UnitError:
        return None


def _column_unit(col: Column, cells: list[str]) -> tuple[str | None, str]:
    hu = header_unit(col.header)
    if hu:
        return hu, "header"
    units = [q[1] for c in cells if (q := values.quantity(c)) and q[1]]
    if units:
        best = max(set(units), key=units.count)
        return best, "cell"
    return None, "none"


def _make_candidates(raw: RawTable, tbl_id: str, sheet_id: str, kind: str, cols: list[Column], tags: list[str | None],
                     tag_raw: list[str | None]) -> list[Candidate]:
    out: list[Candidate] = []
    for k, col in enumerate(cols):
        if not col.meaning or col.meaning in ("tag", "room_number"):
            continue
        cells = [r[k] for r in raw.rows]
        col.unit, col.unit_source = _column_unit(col, [c for c in cells if c])
        if col.dim == "time":
            col.unit, col.unit_source = "min", "fire_parser"
        nums = []
        if col.dim == "length":
            nums = [q[0] for c in cells if c and (q := values.quantity(c)) and q[1] is None]
        guessed = None
        if col.dim == "length" and col.unit is None and nums:
            guessed = _guess_length_unit(nums)
            col.unit, col.unit_source = guessed, "inferred"
        for i, cell in enumerate(cells):
            if not cell:
                continue
            base = dict(meaning=col.meaning, entity_kind=kind, entity_tag=tags[i], entity_tag_raw=tag_raw[i], sheet=sheet_id,
                        table=tbl_id, row=i, cell_text=cell, col=k, header_text=col.header, table_title=raw.title,
                        bbox=None)
            conf = col.score
            if col.dim == "size":
                parts = values.size(cell)
                if parts:
                    unit = parts[0][1] or header_unit(col.header)
                    src = "cell" if parts[0][1] else ("header" if unit else "none")
                    if unit is None:
                        unit, src = _guess_length_unit([p[0] for p in parts]), "inferred"
                    for name, (v, _u) in zip(("width", "height"), parts, strict=True):
                        out.append(Candidate(value=v, unit=unit, unit_source=src, confidence=conf * (0.6 if src == "inferred" else 1.0),
                                             value_si=_si(v, unit), derived_from="size", **{**base, "meaning": name}))
                else:
                    out.append(Candidate(value=cell, unit=None, confidence=conf * 0.5, **base))
                continue
            if col.dim == "time":
                v = _fire(cell, col)
                if v is not None:
                    out.append(Candidate(value=v, unit="min", unit_source="fire_parser", confidence=conf, value_si=v * 60.0, **base))
                continue
            if col.dim in ("length", "area", "volume", "mass", "power", "voltage", "ratio", "count"):
                q = values.quantity(cell)
                if q is None:
                    continue
                v, u = q
                src = "cell" if u else col.unit_source
                u = u or col.unit
                if col.dim == "count":
                    u, src = "count", "none"
                if col.dim == "length" and u is not None and src != "inferred" and not _compatible(u, "m"):
                    u = None
                if col.dim == "area" and u is None and col.unit_source == "none":
                    u = None
                out.append(Candidate(value=v, unit=u, unit_source=src if u else "none",
                                     confidence=conf * (0.6 if src == "inferred" else 1.0), value_si=_si(v, u), **base))
                continue
            out.append(Candidate(value=cell, unit=None, unit_source="none", confidence=conf, **base))
    return out


def _compatible(a: str, b: str) -> bool:
    try:
        convert(1.0, a, b)
        return True
    except UnitError:
        return False


UNSTATED_CELLS = {"-", "--", "---", "–", "—", "?", "tbd", "tba"}


def is_unstated(cell: str) -> bool:
    """A cell that holds only a dash (or TBD): the drawing does not say. "NR" and "none" do say: not rated."""
    return (cell or "").strip().lower() in UNSTATED_CELLS


def _fire(cell: str, col: Column) -> float | None:
    """A fire rating cell as minutes: '1 HR', '45 min', '1-1/2 HR', 'EI30', 'NR', '-', or a bare number in the unit of the header."""
    t = cell.strip()
    if is_unstated(t):
        return None                      # a dash states nothing: the rating is unknown, not 0 minutes
    q = values.quantity(t)
    if q is not None:
        v, u = q
        u = u or header_unit(col.header)
        if u and _compatible(u, "s"):
            return convert(v, u, "min")
    return parse_fire_minutes(t)


def type_table(raw: RawTable, sheet_id: str, index: int) -> TypedTable:
    cols = _type_columns(raw)
    rooms_hint = any(c.meaning in ("room_name", "area", "ceiling_height") for c in cols) and not any(c.meaning == "tag" for c in cols)
    tk = _tag_column(cols, raw, rooms_hint)
    name_col = next((c.index for c in cols if c.meaning == "room_name"), None)
    tag_raw: list[str | None] = []
    for r in raw.rows:
        t = r[tk] if tk is not None and r[tk] else (r[name_col] if name_col is not None and r[name_col] else None)
        tag_raw.append(t)
    tags = [values.entity_key(t) if t else None for t in tag_raw]
    kind, why = _kind(raw, cols, tags)
    tbl_id = f"{sheet_id}:T{index}"
    tt = TypedTable(tbl_id, sheet_id, kind, why, raw.title, raw.method, tuple(raw.bbox), cols, raw.rows, tags)
    tt.candidates = _make_candidates(raw, tbl_id, sheet_id, kind, cols, tags, tag_raw)
    return tt


# ---------------------------------------------------------------------------------------------------------------- api

def _iou_small(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    sa, sb = (a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])
    return ix * iy / max(min(sa, sb), 1e-9)


def _plausible(raw: RawTable, t: TypedTable) -> bool:
    """A table read from words alone must be mostly filled and carry something besides keys: a symbol legend ('ROOM NUMBER',
    'LITE TAG') has the first and not the second."""
    cells = [c for row in raw.rows for c in row]
    fill = sum(1 for c in cells if c) / max(len(cells), 1)
    return fill >= 0.4 and any(c.meaning and c.dim != "tag" for c in t.columns)


def read_tables(words: list[Word], sheet_id: str = "sheet", page=None, ruled: bool = True) -> list[TypedTable]:
    """Every table of a sheet, typed. `page` is the pymupdf page, for the tables drawn with rules."""
    lines = build_lines(words)
    raws = scan_unruled(lines)
    if page is not None and ruled:
        raws = ruled_tables(page, lines, words) + raws
    typed = [(raw, type_table(raw, sheet_id, 0)) for raw in raws]
    typed = [(r, t) for r, t in typed if t.n_typed >= 2 and (r.method == "ruled" or _plausible(r, t))]
    typed.sort(key=lambda rt: (-rt[1].n_typed, -len(rt[0].rows), rt[0].method != "ruled"))
    kept: list[tuple[RawTable, TypedTable]] = []
    for r, t in typed:                                                   # the same table found twice is kept once
        if all(_iou_small(t.bbox, k[1].bbox) < 0.5 for k in kept):
            kept.append((r, t))
    kept.sort(key=lambda rt: (round(rt[1].bbox[1]), rt[1].bbox[0]))
    return [type_table(r, sheet_id, i + 1) for i, (r, _) in enumerate(kept)]


def read_page_tables(page, sheet_id: str, ruled: bool = True) -> list[TypedTable]:
    return read_tables(words_from_page(page), sheet_id, page=page, ruled=ruled)


def read_pdf_tables(path, pages: list[int] | None = None, ruled: bool = True) -> list[TypedTable]:
    import pymupdf

    out = []
    with pymupdf.open(path) as doc:
        for i in (pages if pages is not None else range(len(doc))):
            out += read_page_tables(doc[i], f"p{i + 1}", ruled=ruled)
    return out


def read_sheet_tables(sheet) -> list[TypedTable]:
    return read_tables(words_from_sheet(sheet), sheet.id)
