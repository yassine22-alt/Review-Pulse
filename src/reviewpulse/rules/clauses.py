"""I3 - Clause splitter.

Turns a requirement document (PDF, Markdown or text) into clauses with exact
character offsets into one concatenated text, so every drafted rule can cite
``source.span`` and the curator sees the original wording.

Structure markers (French and English): "Article 12", "Art. 4.2", "4.2.1 ",
"a)" sub-items, "Chapitre / Section / Titre" headings. Tables found by PyMuPDF
are appended as their own clauses (one per row) because thresholds often live there.
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

ARTICLE_RE = re.compile(r"^\s*(?:#+\s*)?(Article|Art\.?)\s*(\d+(?:[.\-]\d+)*)\b", re.I)
NUMBERED_RE = re.compile(r"^\s*(?:#+\s*)?(\d+(?:\.\d+){0,3})[.)]?\s+(?=[A-ZÀ-Ýa-zà-ý☐(])")
SUBITEM_RE = re.compile(r"^\s*([a-z])\)\s+")
HEADING_RE = re.compile(r"^\s*(?:#+\s*)?(Chapitre|Chapter|Section|Titre|Title|Part|Partie)\b.*$", re.I)


def _strip_accents(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


@dataclass
class Clause:
    id: str
    heading: str
    text: str
    page: int
    start: int
    end: int
    parent: str | None = None
    kind: str = "article"         # article | numbered | subitem | table_row | heading
    scope: str = ""               # the last heading above the clause ("Junctions and cavity closures"): what the clause is about


PAGE_NUMBER_RE = re.compile(r"(?:page|p\.|seite|página)?\s*\d{1,4}(?:\s*(?:/|of|sur|von|de)\s*\d{1,4})?", re.I)


def _norm_running(t: str) -> str:
    return re.sub(r"\d+", "#", " ".join(t.split())).lower()


def _running_text(per_page: list[list[str]]) -> set[str]:
    """Headers and footers: a first or last block of a page that repeats (page number aside) on many pages is not content."""
    if len(per_page) < 3:
        return set()
    counts: dict[str, int] = {}
    for blocks in per_page:
        for t in {_norm_running(blocks[0]), _norm_running(blocks[-1])} if blocks else ():
            counts[t] = counts.get(t, 0) + 1
    return {t for t, n in counts.items() if n >= max(3, 0.4 * len(per_page)) and len(t) < 160}


def _unhyphenate(t: str) -> str:
    """A word split over two lines by a hyphen is joined; the line break inside a sentence is kept as it is."""
    return re.sub(r"(?<=[a-zà-ÿ])-\n(?=[a-zà-ÿ])", "", t)


# Table detection is the slow step of a PDF. Its limit is a number of pages, not a number of seconds: a time limit read more
# of the same document on a fast machine than on a slow or busy one, so two people saw different clauses. Every ruled page up
# to this count is read on every machine; the clock is only a guard against a reader that hangs.
TABLE_PAGE_BUDGET = 600
TABLE_BUDGET_S = 3600.0
TABLE_WORD = r"(?:Table|Tableau|Tabelle|Tabla|Tabella|Tabela)"
CAPTION = re.compile(rf"^\s*({TABLE_WORD})\s+([A-Z]{{0,2}}\d+(?:\.\d+)*[a-z]?)\b[\s.:\x07–-]*(.*)", re.I | re.S)
CONTINUED = re.compile(r"^\(?\s*(?:continued|cont\.?|cont.d|suite|fortsetzung|continuaci[óo]n|continua)\b", re.I)


def _has_ruling(page) -> bool:
    """A ruled table needs ruling lines or boxes; a page of plain text has none, so it is not scanned (exact, and fast)."""
    try:
        return any(it[0] in ("l", "re", "qu") for d in page.get_drawings() for it in d["items"])
    except Exception:  # noqa: BLE001
        return True


def _is_layout_frame(tab, page_rect) -> bool:
    """A "table" that is really the frame of a form: it covers most of the page and its cells hold sentences, not data. Its text is
    already read as ordinary paragraphs, so reading it again as rows would only add a garbled copy."""
    try:
        x0, y0, x1, y1 = tab.bbox
        if (x1 - x0) * (y1 - y0) < 0.5 * page_rect.width * page_rect.height:
            return False
        cells = [c for row in tab.extract() for c in row if c and c.strip()]
        prose = sum(1 for c in cells if len(re.findall(r"[^\W\d_]{2,}", c)) >= 4)       # four or more words: a sentence, not a datum
        return bool(cells) and prose >= 0.5 * len(cells)
    except Exception:  # noqa: BLE001 - when in doubt it is a table
        return False


def _captions(page) -> list[tuple[float, float, str, bool]]:
    """Table captions on a page as (top, bottom, "Table B4", continued), top to bottom. A caption is a block that STARTS with the
    table's name followed by its title ("Table B4 Minimum periods of fire resistance") or by "continued"; a sentence that merely
    begins with a reference ("Table B4 gives ...", "Table 0.1, 12") or an index entry is not one."""
    out = []
    for b in page.get_text("blocks"):
        m = CAPTION.match(b[4]) if len(b) > 4 and isinstance(b[4], str) else None
        if not m:
            continue
        first = m.group(3).strip().split("\n")[0].strip()
        continued = bool(CONTINUED.match(first))
        words = first.split()
        is_title = (bool(words) and words[0][:1].isupper() and not re.match(r"[\d,;)]", first)
                    and not first.rstrip().endswith(".") and len(words) <= 25)
        if continued or is_title:
            out.append((b[1], b[3], f"Table {m.group(2)}", continued))
    return sorted(out)


def _rows_of(tab) -> list[str]:
    rows = []
    for cells in tab.extract():
        cells = [re.sub(r"\s+", " ", c).strip() for c in cells if c and c.strip()]
        if cells:
            rows.append(" | ".join(cells))
    return rows


TABLE_NOTES = re.compile(r"^(?:notes?|remarques?|anmerkung(?:en)?|notas?)\b\s*[:.]?", re.I)


LIST_MARK = re.compile(r"^(?:[a-z]|[ivx]{1,4}|\d{1,2})[.)]\s")          # "b. Detached swimming pool" starts an item, not a wrapped line


def _whitespace_rows(page, clip) -> list[str]:
    """Rows of a table that has no vertical rules: its columns are separated by white space only. Words on one visual line are a
    row, and a gap wider than the line is high starts a new cell. A line whose cells all start in lower case is the rest of a
    wrapped cell ("loading bay with ..." under "a. Balcony, verandah, carport, covered way or"): it is joined to the row above,
    cell by cell, by where each cell starts, so a sentence is not cut in two. Reading stops at the notes under the table. Returns
    nothing unless at least two lines have two cells or more, so a paragraph of prose is not taken for a table."""
    words = sorted(page.get_text("words", clip=clip), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list] = []
    for w in words:
        mid, height = (w[1] + w[3]) / 2, max(w[3] - w[1], 1.0)
        if lines and abs(mid - lines[-1][0]) <= 0.5 * height:
            lines[-1][1].append(w)
        else:
            lines.append([mid, [w]])
    rows: list[list[list]] = []                          # a row is a list of cells [x of its left edge, text]
    wide = 0
    for _mid, ws in lines:
        ws.sort(key=lambda w: w[0])
        height = max(w[3] - w[1] for w in ws)
        cells, cur = [], [ws[0][0], ws[0][4]]
        for prev, w in zip(ws, ws[1:]):
            if w[0] - prev[2] > 1.2 * height:
                cells.append(cur)
                cur = [w[0], w[4]]
            else:
                cur[1] += " " + w[4]
        cells.append(cur)
        if TABLE_NOTES.match(cells[0][1]):
            break
        wide += len(cells) >= 2
        wrapped = rows and all((c[1][:1].islower() or c[1][:1] in ")],") and not LIST_MARK.match(c[1]) for c in cells)
        if wrapped:
            for x, text in cells:                        # each piece goes to the cell of the row above that starts nearest to it
                target = min(rows[-1], key=lambda c: abs(c[0] - x))
                target[1] += " " + text
        else:
            rows.append(cells)
    if wide < 2:
        return []
    return [" | ".join(text for _x, text in r) for r in rows]


def _tables_for_pages(path: str, pages: list[int]) -> list[tuple[int, int, int, str, str | None]]:
    """Table rows of the given pages as (page, table, row, text, name). `name` is the caption the table sits under ("Table B4"),
    which is how the text refers to it; None for a table with no caption. A caption with no ruled table under it (a table drawn
    without lines) is read from the layout of its text. A top-level function so a worker process can run it."""
    import pymupdf

    doc = pymupdf.open(path)
    out = []
    for i in pages:
        try:
            page = doc[i]
            caps = _captions(page)
            tabs = [tab for tab in page.find_tables().tables if not _is_layout_frame(tab, page.rect)]
            named: dict[int, str] = {}
            loose: list[tuple[str, list[str]]] = []
            for k, (top, bottom, name, _continued) in enumerate(caps):
                limit = caps[k + 1][0] if k + 1 < len(caps) else page.rect.height
                # the table of a caption is the first one that starts below it and before the next caption
                below = sorted((tab.bbox[1], t) for t, tab in enumerate(tabs) if t not in named and top - 2 <= tab.bbox[1] < limit)
                if below:
                    named[below[0][1]] = name
                    continue
                # no ruled table under the caption: a table drawn with horizontal rules only, read from the gaps between its words
                clip = pymupdf.Rect(page.rect.x0, bottom, page.rect.x1, limit)
                loose_rows = _whitespace_rows(page, clip)
                if loose_rows:
                    loose.append((name, loose_rows))
            for t, tab in enumerate(tabs):
                for r, row in enumerate(_rows_of(tab)):
                    out.append((i, t, r, row, named.get(t)))
            for k, (name, loose_rows) in enumerate(loose, len(tabs)):
                for r, row in enumerate(loose_rows):
                    out.append((i, k, r, row, name))
        except Exception:  # noqa: BLE001 - table finder is best effort
            pass
    return out


PARALLEL_MIN_PAGES = 12     # fewer ruled pages than this are read in the calling process: starting workers costs more
PAGES_PER_TASK = 6


def _table_workers() -> int:
    import os

    forced = os.environ.get("REVIEWPULSE_WORKERS")
    if forced and forced.isdigit():
        return int(forced)
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def _find_tables(path: Path, ruled: list[int]) -> tuple[list[tuple], list[int]]:
    """(rows, pages not scanned). Pages are read in worker processes when there are many. The first TABLE_PAGE_BUDGET ruled pages
    are read whatever the machine; a failure to start workers falls back to reading in this process."""
    workers = _table_workers()
    ruled, beyond = ruled[:TABLE_PAGE_BUDGET], [i + 1 for i in ruled[TABLE_PAGE_BUDGET:]]
    if len(ruled) >= PARALLEL_MIN_PAGES and workers > 1:
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            from concurrent.futures import TimeoutError as FutureTimeout

            chunks = [ruled[k:k + PAGES_PER_TASK] for k in range(0, len(ruled), PAGES_PER_TASK)]
            rows, done = [], set()
            pool = ProcessPoolExecutor(max_workers=min(workers, len(chunks)))
            try:
                futures = {pool.submit(_tables_for_pages, str(path), ch): k for k, ch in enumerate(chunks)}
                try:
                    for fut in as_completed(futures, timeout=TABLE_BUDGET_S):
                        rows += fut.result()
                        done.add(futures[fut])
                except FutureTimeout:
                    pass
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            late = [i + 1 for k, ch in enumerate(chunks) if k not in done for i in ch]
            return sorted(rows, key=lambda r: r[:3]), late + beyond
        except Exception:  # noqa: BLE001 - no workers (a restricted host, an unguarded script): read here, as before
            pass
    # read in this process, page after page, with no clock: a clock here skipped pages after the machine had slept, and a reader
    # that hangs inside one page could not be interrupted from here anyway
    return _tables_for_pages(str(path), ruled), beyond


def _mark_indented_items(blocks: list) -> list[str]:
    """Block texts, with "- " put in front of the items of an indented list. A checklist is laid out as headings with short items
    indented under them, and its items are often imperatives with no obligation word ("Dimension and label all rooms"), which the
    splitter would take for prose. Four or more short blocks sharing one left edge, with a block further left beside them (the
    heading), are list items."""
    items = [(b, str(b[4]).strip()) for b in blocks if len(b) > 4 and str(b[4]).strip()]
    marked: set[int] = set()
    edges: dict[int, list[int]] = {}
    for k, (b, _t) in enumerate(items):
        edges.setdefault(round(b[0] / 3), []).append(k)
    for edge, members in edges.items():
        if len(members) < 4:
            continue
        x0 = items[members[0]][0][0]
        top, bottom = min(items[k][0][1] for k in members), max(items[k][0][3] for k in members)
        shorter = all(len(items[k][1]) <= 220 and items[k][1].count(chr(10)) <= 3 for k in members)
        headed = any(b[0] < x0 - 8 and top - 20 <= b[1] <= bottom and len(t) <= 80 and b[3] - b[1] < 30
                     for k, (b, t) in enumerate(items) if k not in members and round(b[0] / 3) != edge)
        already = sum(1 for k in members if re.match(r"\s*(?:[-*•–]|\(?\w{1,3}[.)])\s", items[k][1]))
        if shorter and headed and already < len(members) / 2:
            marked.update(members)
    return [("- " + t) if k in marked else t for k, (b, t) in enumerate(items)]


def reading_order(blocks: list, width: float) -> list:
    """Text blocks in reading order. A page sorted top to bottom, left to right interleaves the lines of a two column layout (forms,
    checklists, standards in columns). A gutter is looked for between 35% and 65% of the page width: where almost no block crosses
    it and both sides hold text, each band of the page between full width blocks (titles) is read left column, then right column.
    Anything else keeps the plain order."""
    text = [b for b in blocks if len(b) > 4 and str(b[4]).strip()]
    if len(text) < 8 or width <= 0:
        return blocks
    best = None
    for k in range(35, 66):
        g = width * k / 100
        left = sum(1 for b in text if b[2] <= g + 2)
        right = sum(1 for b in text if b[0] >= g - 2)
        cross = len(text) - left - right
        if best is None or cross < best[0]:
            best = (cross, g, left, right)
    cross, g, left, right = best
    if cross > 0.15 * len(text) or left < 3 or right < 3 or min(left, right) < 0.25 * (left + right):
        return blocks
    crossing = sorted((b for b in text if b[0] < g - 2 and b[2] > g + 2), key=lambda b: b[1])
    keyed = []
    for b in text:
        if b[0] < g - 2 and b[2] > g + 2:
            keyed.append(((sum(1 for c in crossing if c[1] < b[1]) + 0.5), 0, b[1], b))
        else:
            band = sum(1 for c in crossing if c[3] <= b[1] + 1)
            keyed.append((band, 0 if b[2] <= g + 2 else 1, b[1], b))
    return [t[3] for t in sorted(keyed, key=lambda t: t[:3])]


SCANNED_MAX_CHARS = 25      # a page with fewer characters than this in its text layer, and an image on it, is a scan


def _ocr_if_scanned(page, blocks: list[str]) -> list[str]:
    """A scanned page has no text layer: its blocks are empty. The page is then read with OCR (when it is installed); a page that
    has a text layer is never OCR'd, so a born-digital document is read exactly as before."""
    if sum(len(b.strip()) for b in blocks) >= SCANNED_MAX_CHARS or not page.get_images(full=True):
        return blocks
    try:
        from . import readers

        if not readers.ocr_available():
            return blocks
        lines = readers.ocr_lines(page.get_pixmap(dpi=300).tobytes("png"))
        return [p for p in readers.join_ocr_lines(lines).split("\n") if p.strip()]
    except Exception as exc:  # noqa: BLE001 - OCR is a best effort; the page is then empty, as it was before
        warnings.warn(f"page {page.number + 1}: OCR failed ({type(exc).__name__}: {str(exc)[:80]})", stacklevel=2)
        return blocks


def _pdf_text(path: Path) -> tuple[str, list[tuple[int, int]], list[str]]:
    """Concatenated text, (page start offset, page number) list and table rows as text."""
    import pymupdf

    doc = pymupdf.open(path)
    parts, pages = [], []
    off = 0
    per_page = [_mark_indented_items(reading_order(page.get_text("blocks", sort=True), page.rect.width)) for page in doc]
    per_page = [_ocr_if_scanned(page, blocks) for page, blocks in zip(doc, per_page)]
    running = _running_text(per_page)
    ruled = []
    for i, page in enumerate(doc):
        kept = [t for t in per_page[i] if _norm_running(t) not in running and not PAGE_NUMBER_RE.fullmatch(t)]
        txt = "\n\n".join(_unhyphenate(t) for t in kept) + "\n\n"       # a block is a paragraph: keep the break between them
        pages.append((off, i))
        parts.append(txt)
        off += len(txt)
        if _has_ruling(page):
            ruled.append(i)
    rows, unscanned = _find_tables(path, ruled)
    if unscanned:
        warnings.warn(f"{path.name}: tables on pages {unscanned[0]}-{unscanned[-1]} were not scanned (the limit is "
                      f"{TABLE_PAGE_BUDGET} pages with ruling lines, or a table reader did not answer); their text is still read as ordinary text", stacklevel=2)
    return "".join(parts), pages, rows


def _page_of(offset: int, pages: list[tuple[int, int]]) -> int:
    p = 0
    for start, num in pages:
        if start <= offset:
            p = num
    return p


# ---- structure detection ---------------------------------------------------------------------------------------------
# Requirement documents number their parts in many ways. Instead of one scheme, every line is tested against a few generic
# shapes (a word and a number, a code like REQ-001, 1.2.3, (1), (a), (ii), a bullet) and the depth of each shape decides who is
# whose child. A word-and-number label ("Rule 5") only counts as structure when that word starts several lines, which is what
# real numbering does and prose does not. Text no marker covers is cut into paragraphs and sentences so nothing is lost.
WORD_NUM_RE = re.compile(r"^\s*(?:#+\s*)?([A-ZÀ-Ý][A-Za-zÀ-ÿ]{2,})\.?\s+(\d+(?:\.\d+)*|[IVXL]{1,6})\s*[.:)\-–]?(?=\s|$)")
CODE_RE = re.compile(r"^\s*(?:#+\s*)?([A-Z][A-Z0-9]{1,9}[-_.]\d+[\w.\-]*)[:.)]?\s+(?=\S)")
# an item id of a canned correction list ("A1.", "C17.", "H3."): a letter or two and a number, so it is told from a sentence by being a series
ITEM_ID_RE = re.compile(r"^\s*(?:#+\s*)?([A-Z]{1,2})(\d{1,3})\.\s*(?=[A-Z\"“(\[☐])")
PAREN_NUM_RE = re.compile(r"^\s*\((\d{1,3})\)\s+(?=\S)")
LETTER_RE = re.compile(r"^\s*\(?([a-z])\)\s+(?=\S)")
ROMAN_RE = re.compile(r"^\s*\(([ivx]{2,6})\)\s+(?=\S)")
# a list marker is a dash, or a bullet glyph. Word processors and PDF exports draw bullets from symbol fonts (Wingdings, Symbol), and
# their glyphs arrive as private-use characters (U+F0A8, U+F07F ...) that are not text at all
BULLET_GLYPHS = "•▪▫●○◦■□☐☑☒✓✔✗✘➢➤►▶‣⁃◆◇■-◿☐-☒-"
BULLET_RE = re.compile(rf"^\s*(?:[-*–]\s+|[{BULLET_GLYPHS}]\s*)(?=\S)")
BULLET_LEAD = re.compile(rf"^\s*(?:[-*–]\s+|[{BULLET_GLYPHS}]\s*)")
SECTION_SIGN_RE = re.compile(r"^\s*§\s*(\d+(?:\.\d+)*)[.:)\-–]?\s+(?=\S)")
BIG_HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(Chapitre|Chapter|Section|Titre|Title|Part|Partie|Appendix|Annex|Annexe|Schedule|Anhang|Capítulo|"
    r"Apéndice|Kapitel|Teil)\b.*$", re.I)
NOT_STRUCTURE_WORDS = {"table", "tableau", "tabla", "tabelle", "figure", "fig", "note", "notes", "page", "example",
                       "exemple", "see", "voir", "step", "version", "date"}
UNIT_WORDS = {"m", "mm", "cm", "km", "m2", "m²", "%", "min", "h", "s", "kg", "n", "pa", "lux", "persons", "people"}
MODALS = re.compile(
    r"\b(shall|must|should|need|needs|require[sd]?|required|may not|may|at least|no less|no more|not exceed|minimum|maximum|"
    r"doit|doivent|devra|devront|faut|exig|minimal|maximal|muss|müssen|soll|sollen|mindestens|höchstens|debe|deben|deberá|"
    r"mínimo|máximo|deve|devem|devono|dovrà|minimo|massimo|moet|moeten|zal|minstens|ten minste)\b", re.I)
DEFINITION_RE = re.compile(r"\b((?<!other )(?<!by )(?<!any )(?<!such )means(?! of\b)|shall mean|refers to|is defined as|are defined as|signifie|désigne|bedeutet|significa|"
                           r"si intende|betekent|se entiende)\b", re.I)
ABBREVIATIONS = {"art", "no", "nos", "e.g", "i.e", "etc", "approx", "max", "min", "vs", "fig", "tab", "cf", "al", "sec", "par",
                 "para", "ref", "vol", "dr", "st", "mr", "mrs"}


def _is_table_line(line: str) -> bool:
    return line.count("|") >= 2 and not re.fullmatch(r"[\s|:\-+]+", line)


def _word_counts(lines: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ln in lines:
        m = WORD_NUM_RE.match(ln)
        if m and m.group(1).lower() not in NOT_STRUCTURE_WORDS:
            counts[m.group(1).lower()] = counts.get(m.group(1).lower(), 0) + 1
        m = ITEM_ID_RE.match(ln)
        if m:
            counts["#" + m.group(1)] = counts.get("#" + m.group(1), 0) + 1
    return counts


def _classify(ln: str, prev_blank: bool, words: dict[str, int], wrapped: bool = False, next_number: int = 1):
    """(level, kind, label, own) for a line that starts a part of the document, else None. `own` is what the id is made of.
    `wrapped`: the line before it is in the same paragraph and does not end a sentence, so a line that opens with a number
    ("... the requirements of / 233.3.1.1 and 233.3.1.2 shall apply") continues that sentence instead of starting a clause."""
    s = ln.strip()
    if not s:
        return None
    m = ARTICLE_RE.match(ln)
    if m:
        return 1, "article", f"Art. {m.group(2)}", None
    if BIG_HEADING_RE.match(ln) and len(s) <= 90:
        return 0, "heading", s[:60], None
    m = SECTION_SIGN_RE.match(ln)
    if m:
        return 1, "article", f"§ {m.group(1)}", None
    m = WORD_NUM_RE.match(ln)
    if m and (words.get(m.group(1).lower(), 0) >= 2) and m.group(1).lower() not in NOT_STRUCTURE_WORDS:
        return 1, "article", f"{m.group(1)} {m.group(2)}", None
    m = ITEM_ID_RE.match(ln)
    if m and words.get("#" + m.group(1), 0) >= 3:           # "A1.", "C17.": the letter starts a series of items, as numbering does
        return 1, "numbered", m.group(1) + m.group(2), None
    m = CODE_RE.match(ln)
    if m:
        tail = ln[m.end(1):].lstrip(".:) 	 ")
        if wrapped and (tail[:1] in ("[", "(") or tail[:1].islower()):
            return None                                    # "... in accordance with CRC / R302.2.3. [CRC R302.2.2]": a section reference wrapped to a new line
        return 1, "article", m.group(1), None
    m = NUMBERED_RE.match(ln)
    if m and len(s) > len(m.group(1)) + 3:
        label = m.group(1)
        if ln[m.end():m.end() + 1] == "(" and s[len(label):len(label) + 1] not in (".", ")"):
            return None                                    # "12 (units) ...": a number and a parenthesis is a clause only after a full stop ("13. (Continuous ...)")
        rest = s[len(label):].lstrip(".) \t")
        first = rest.split(" ", 1)[0] if rest else ""
        in_sequence = "." not in label and int(label) == next_number and (next_number > 1 or not wrapped)      # "1. ... 2. ... 3. ..." is a list, whatever the case
        if "." not in label and not in_sequence and (int(label) > 999 or first[:1].islower() or first.lower().rstrip(".,;") in UNIT_WORDS):
            return None                                    # "30 m to reach a stair": a wrapped line, not a clause number
        if wrapped and first[:1].islower():
            return None                                    # "206.7 to use a platform lift": a reference inside a sentence
        if wrapped and label.startswith("0.") and s[len(label):len(label) + 1] == ".":
            return None                                    # "ratio of / 0.45. No special ...": a decimal, and no clause number starts with 0
        return 1, "numbered", label, None
    m = PAREN_NUM_RE.match(ln)
    if m:
        return 2, "subitem", f"({m.group(1)})", None
    m = ROMAN_RE.match(ln)
    if m:
        return 4, "subitem", f"{m.group(1)})", None
    m = LETTER_RE.match(ln)
    if m:
        return 3, "subitem", f"({m.group(1)})" if ln.lstrip().startswith("(") else f"{m.group(1)})", None
    if BULLET_RE.match(ln):
        return 5, "subitem", "item", None
    return None


def _is_loud_heading(ln: str) -> bool:
    s = ln.strip()
    if re.match(r"#+\s+\S", s) and not re.match(r"#+\s*\d", s):
        return True
    letters = [c for c in s if c.isalpha()]
    return (4 <= len(s) <= 70 and len(letters) >= 4 and all(c.isupper() for c in letters) and not s.endswith((".", ";", ","))
            and not _is_table_line(s))


def _continues(item: str, after: str) -> bool:
    """A list item that stops without a full stop, and a paragraph that goes on in lower case, are one sentence cut by a page or column
    break in the PDF ("... one operable window or exterior" / "door approved for emergency egress")."""
    tail, head = item.rstrip(), after.lstrip()
    return bool(tail) and not tail.endswith((".", ":", ";", "!", "?")) and bool(head) and head[:1].islower() \
        and not BULLET_LEAD.match(head)


def _is_quiet_heading(lines: list[str], i: int, words: dict[str, int]) -> bool:
    """A heading in ordinary type ("Junctions and cavity closures"): a short line with no end punctuation, opening a block, that the
    next block answers with a numbered clause or the first item of a list. Without this the heading ends up as the last line of the clause before it."""
    s = lines[i].strip()
    if not (3 <= len(s) <= 80) or len(s.split()) > 10 or s.endswith((".", ";", ",", ":", "|")) or not s[:1].isupper() \
            or s[:1].isdigit() or _is_table_line(s) or MODALS.search(s):
        return False
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines) or j > i + 3:
        return False
    nxt = _classify(lines[j], j > i + 1, words)
    return nxt is not None and (nxt[0] == 1 and nxt[1] in ("numbered", "article") or nxt[1] == "subitem")


def _sentences(text: str, base: int):
    """(start, end) of each sentence of a paragraph; abbreviations and decimals do not end one."""
    cuts, begin = [], 0
    for m in re.finditer(r"[.!?;]\s+(?=[A-ZÀ-Ý“\"(])", text):
        word = re.findall(r"[\w.]+$", text[begin:m.start()])
        raw = (word[-1] if word else "").rstrip(".")
        last = raw.lower()
        if last in ABBREVIATIONS or len(raw) == 1 and raw.isupper():          # "J. Smith"; a unit such as "m." ends a sentence
            continue
        cuts.append((begin, m.start() + 1))
        begin = m.end()
    cuts.append((begin, len(text)))
    return [(base + a, base + b) for a, b in cuts if text[a:b].strip()]


LINE_ITEM = re.compile(r"^[^\S\n]*([A-Z]{1,2}|)(\d{1,3})\.[^\S\n]+(?=[A-Z(☐])", re.M)
INLINE_ITEM = re.compile(r"(?<=[a-z.\]\)\"”])(?:[^\S\n]*(?=[A-Z]{1,2}\d)|[^\S\n]{2,}(?=\d))([A-Z]{1,2}|)(\d{1,3})\.[^\S\n]+(?=[A-Z(☐])")
LONE_NUMBER = re.compile(r"^[^\S\n]*(?:\d{1,3}|[IVX]{1,4})\.[^\S\n]*\n(?=[^\S\n]*[A-Za-z])", re.M)


def prepare_items(full: str, pages: list[tuple[int, int]]) -> tuple[str, list[tuple[int, int]]]:
    """Two layout accidents of PDF text that hide the item ids of a numbered list or of a canned correction list. A number alone on its
    line ("1." then the sentence on the next line) is joined to the sentence (same length, so offsets do not move). An item that follows
    the end of the one before on the same line ("... at recheck.A20. Complete ...", "... for (____).   13. (Continuous ...") starts a
    line of its own, when its id is the next in the series it belongs to (A19 came before A20; 12 before 13). The page ranges are
    shifted by the line breaks inserted."""
    full = LONE_NUMBER.sub(lambda m: m.group(0)[:-1] + " ", full)
    starts = [(m.start(), m.group(1), int(m.group(2)), False) for m in LINE_ITEM.finditer(full)]
    series = {k for k in {s[1] for s in starts} if sum(1 for s in starts if s[1] == k) >= 3}
    inline = [(m.start(), m.group(1), int(m.group(2)), True) for m in INLINE_ITEM.finditer(full) if m.group(1) in series]
    if not inline:
        return full, pages
    last: dict[str, int] = {}
    cuts: list[tuple[int, int]] = []                       # (offset where the line break goes, offset of the id)
    for at, letters, n, is_inline in sorted(s for s in starts + inline if s[1] in series):
        if is_inline:
            if n != last.get(letters, 0) + 1:
                continue
            cuts.append((at, INLINE_ITEM.match(full, at).start(1)))
        last[letters] = n
    out, pos = [], 0
    for at, id_at in cuts:
        out += [full[pos:at], "\n"]
        pos = id_at
    out.append(full[pos:])

    def moved(off: int) -> int:
        shift = sum(1 for at, _ in cuts if at < off)
        return off + shift - sum(id_at - at for at, id_at in cuts if id_at <= off)

    return "".join(out), [(moved(a), moved(b)) for a, b in pages]


def split_text(full: str, pages: list[tuple[int, int]] | None = None) -> list[Clause]:
    pages = pages or [(0, 0)]
    lines = full.splitlines(keepends=True)
    starts, off = [], 0
    for ln in lines:
        starts.append(off)
        off += len(ln)
    words = _word_counts(lines)
    marks = []      # (line index, id, kind, heading text, parent id or None)
    stack: list[tuple[int, str]] = []                   # (level, id) of the open parts
    used: set[str] = set()
    scope, counters = "", {}                           # the last heading, and bullet counters per parent
    table_n, i, after_heading = 0, 0, -1
    prev_blank, prev_line, last_number, open_cite = True, "", 0, False
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            prev_blank = True
            i += 1
            continue
        if _is_table_line(ln):                         # a block of rows: the first is the header, each row keeps it as parent
            j = i
            while j < len(lines) and (_is_table_line(lines[j]) or re.fullmatch(r"[\s|:\-+]*", lines[j]) and lines[j].strip()):
                j += 1
            block = [k for k in range(i, j) if _is_table_line(lines[k])]
            if len(block) >= 2:
                table_n += 1
                head = lines[block[0]].strip().strip("|").strip()
                tm = re.match(r"(Table|Tableau|Tabla|Tabelle)\s+\S+", head, re.I)
                hid = tm.group(0) if tm else f"table {table_n}"
                hid = _unique(hid, used, scope)
                marks.append((block[0], hid, "table_header", lines[block[0]].strip(), None))
                for r, k in enumerate(block[1:], 1):
                    marks.append((k, _unique(f"{hid} row {r}", used, scope), "table_row", lines[k].strip(), hid))
                i, prev_blank = j, False
                continue
        wrapped = not prev_blank and bool(prev_line) and not prev_line.rstrip().endswith((".", ":", ";", "!", "?"))
        if prev_blank:
            open_cite = False
        c = _classify(ln, prev_blank, words, wrapped, last_number + 1)
        if c is not None and open_cite:
            c = None                                       # "[CRC / R302.2.3. ...": the rest of a bracketed citation is not a clause
        if "[" in ln or "]" in ln or open_cite:
            open_cite = (open_cite and "]" not in ln) or ln.count("[") > ln.count("]")
        if c is not None and c[1] == "numbered" and c[2].isdigit():
            last_number = int(c[2])
        if c is None and (prev_blank or after_heading == i) and (_is_loud_heading(ln) or _is_quiet_heading(lines, i, words)):
            c = (0, "heading", ln.strip()[:60], None)
        prev_blank, prev_line = False, ln
        if c is None:
            i += 1
            continue
        level, kind, label, _ = c
        if level == 0:
            scope, stack = ln.strip()[:30], []
            marks.append((i, ln.strip()[:60], "heading", ln.strip(), None))
            i += 1
            after_heading = i                           # a heading may continue on the next line ("CHEMINEMENT / EXTERIEUR")
            continue
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        if level >= 2 and parent is None and label != "item" and not label.startswith("("):
            i += 1                                      # a "b)" with nothing above it is not structure
            continue
        if level == 1:
            cid = label
        elif label == "item":
            counters[parent] = counters.get(parent, 0) + 1
            cid = f"{parent} item {counters[parent]}" if parent else f"item {counters.get('', 0) + 1}"
            if not parent:
                counters[""] = counters.get("", 0) + 1
        else:
            cid = f"{parent} {label}" if parent else label
        cid = _unique(cid, used, scope)
        if level == 1 and kind == "article":
            scope = cid[:30]                            # numbers that repeat under the next article are told apart by it
        stack.append((level, cid))
        marks.append((i, cid, kind, ln.strip(), parent if level >= 2 else None))
        i += 1

    clauses: list[Clause] = []
    covered: list[tuple[int, int]] = []
    heads: list[tuple[int, str]] = []
    order = sorted(marks, key=lambda m: m[0])
    for k, (i, cid, kind, heading, parent) in enumerate(order):
        j = order[k + 1][0] if k + 1 < len(order) else len(lines)
        start = starts[i]
        end = starts[j] if j < len(lines) else len(full)
        while end > start and full[end - 1] in "\n\r ":
            end -= 1
        if kind == "heading":                           # a heading's own line is not a clause; text under it still is
            heads.append((start, heading.strip()[:100]))
            body_start = starts[i + 1] if i + 1 < len(lines) else len(full)
            covered.append((start, min(body_start, end)))
            continue
        if kind == "subitem":                           # a list item ends at the blank line; what follows is a paragraph of its own
            pos = 0
            while True:
                blank = re.compile(r"\n[ \t]*\n").search(full, start + pos, end)
                if blank is None or not _continues(full[start:blank.start()], full[blank.end():end]):
                    break
                pos = blank.end() - start                           # the item runs on after a page or column break
            if blank:
                end = blank.start()
        if kind in ("table_header", "table_row"):
            end = min(end, starts[i + 1] - 1 if i + 1 < len(lines) else end)
            while end > start and full[end - 1] in "\n\r ":
                end -= 1
        covered.append((start, end))
        text = full[start:end]
        if kind in ("article", "numbered") and DEFINITION_RE.search(text) and not MODALS.search(text):
            kind = "definition"
        clauses.append(Clause(id=cid, heading=heading[:120], text=text, page=_page_of(start, pages), start=start, end=end,
                              parent=parent, kind=kind))

    # text no marker owns (a preamble, prose under a heading, a document with no numbering at all)
    gaps, pos = [], 0
    for a, b in sorted(covered):
        if a > pos:
            gaps.append((pos, a))
        pos = max(pos, b)
    if pos < len(full):
        gaps.append((pos, len(full)))
    n = 0
    for a, b in gaps:
        paras: list[list[int]] = []                         # [start, end] of each paragraph; one cut by a page break is rejoined
        for pm in re.finditer(r"\S[^\n]*(?:\n(?!\s*\n)[^\n]*)*", full[a:b]):
            if paras and _continues(full[paras[-1][0]:paras[-1][1]], pm.group(0)):
                paras[-1][1] = a + pm.end()
            else:
                paras.append([a + pm.start(), a + pm.end()])
        for ps, pe in paras:
            para, base = full[ps:pe], ps
            sents = _sentences(para, base)
            for s, e in sents:
                text = full[s:e].strip()
                s += len(full[s:e]) - len(full[s:e].lstrip())
                e = s + len(text)
                kind = "definition" if DEFINITION_RE.search(text) and not MODALS.search(text) else "paragraph"
                if len(text) < 15 or not (MODALS.search(text) or kind == "definition"):    # a digit alone ("item 5") is not an obligation
                    continue
                n += 1
                clauses.append(Clause(id=_unique(f"P{n}", used, scope), heading=text[:120], text=text, page=_page_of(s, pages),
                                      start=s, end=e, parent=None, kind=kind))
    clauses.sort(key=lambda c: (c.start, c.end))
    for c in clauses:                                   # the heading each clause sits under
        above = [h for st, h in heads if st <= c.start]
        c.scope = above[-1] if above else ""
    # a list with no numbered parent hangs from the sentence that introduces it ("... the following characteristics:")
    lead = None
    for c in clauses:
        if c.kind == "subitem" and c.parent is None and lead is not None:
            c.parent = lead
        elif c.kind != "subitem":
            lead = c.id if c.text.rstrip().endswith(":") else None
    return clauses


def _unique(cid: str, used: set[str], scope: str) -> str:
    """A clause id nobody else has: a repeated number is told apart by the heading it sits under."""
    if cid not in used:
        used.add(cid)
        return cid
    cand = f"{cid} [{scope}]" if scope else cid
    k = 2
    while cand in used:
        cand = f"{cid} [{scope or 'dup'}] #{k}"
        k += 1
    used.add(cand)
    return cand


def split_document(path: str | Path) -> tuple[str, list[Clause]]:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        full, pages, rows = _pdf_text(path)
        full, pages = prepare_items(full, pages)
        clauses = split_text(full, pages)
        used = {c.id for c in clauses}
        header_of: dict[str, str] = {}                  # table id -> the text of its header row
        count: dict[str, int] = {}                      # table id -> rows written so far
        tid = ""
        for pg, t, r, row, name in rows:
            start = len(full)
            if r == 0:
                if name and name in header_of:          # the same table going on over the page: its rows join the first part
                    tid = name
                    if row == header_of[tid]:           # the header printed again on the new page is not a row
                        continue
                else:
                    tid = name if name and name not in used else f"table p{pg + 1}.{t + 1}"
                    used.add(tid)
                    header_of[tid], count[tid] = row, 0
                    full += row + "\n"
                    clauses.append(Clause(id=tid, heading=row[:120], text=row, page=pg, start=start, end=start + len(row),
                                          parent=None, kind="table_header"))
                    continue
            count[tid] += 1
            full += row + "\n"
            clauses.append(Clause(id=f"{tid} row {count[tid]}", heading=row[:120], text=row, page=pg, start=start,
                                  end=start + len(row), parent=tid, kind="table_row"))
        return full, clauses
    from . import readers

    suffix = path.suffix.lower()
    if suffix == ".docx":
        full = _docx_text(path)
    elif suffix in readers.SHEET_TYPES:
        full = readers.sheet_text(path)
    elif suffix in readers.HTML_TYPES:
        full = readers.html_text(path)
    elif suffix in readers.IMAGE_TYPES:
        full = readers.ocr_image_text(path)
    else:
        full = _read_text(path)
    return full, split_text(full)


def _read_text(path: Path) -> str:
    """A text file in whatever encoding it was saved in: a checklist exported from Windows is often cp1252, not UTF-8."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _docx_text(path: Path) -> str:
    """Paragraphs, then table rows (cells joined by " | "), in document order (needs python-docx).

    Word keeps list numbers and heading levels outside the text, so they are put back: an automatically numbered paragraph gets
    its label ("1.", "(a)", "-"), a heading style becomes a "#" line, and a table gets the caption line above it as its header."""
    try:
        import docx
    except ImportError as e:
        raise RuntimeError('reading .docx needs python-docx: pip install -e ".[app]"') from e
    d = docx.Document(str(path))
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    styles = {st.style_id: (st.name or "") for st in d.styles}
    formats = _numbering_formats(d)
    style_numbering = {}
    for st in d.styles:
        ppr = st.element.find(f"{ns}pPr")
        if ppr is not None and ppr.find(f"{ns}numPr") is not None:
            style_numbering[st.style_id] = ppr.find(f"{ns}numPr")
    counters: dict[tuple[str, int], int] = {}
    lines = []
    for block in d.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = "".join(t.text or "" for t in block.iter() if t.tag.endswith("}t"))
            ppr = block.find(f"{ns}pPr")
            style = ""
            num = None
            if ppr is not None:
                st = ppr.find(f"{ns}pStyle")
                style = styles.get(st.get(f"{ns}val"), "") if st is not None else ""
                np_ = ppr.find(f"{ns}numPr")
                if np_ is None and st is not None:           # numbering given by the paragraph style ("List Number")
                    np_ = style_numbering.get(st.get(f"{ns}val"))
                if np_ is not None and np_.find(f"{ns}numId") is not None:
                    lvl = np_.find(f"{ns}ilvl")
                    num = (np_.find(f"{ns}numId").get(f"{ns}val"), int(lvl.get(f"{ns}val")) if lvl is not None else 0)
            if text.strip() and re.match(r"(Heading|Title|Titre)\b", style, re.I) and num is None:
                text = "# " + text
            elif text.strip() and num is not None:
                for k in [k for k in counters if k[0] == num[0] and k[1] > num[1]]:
                    del counters[k]
                counters[num] = counters.get(num, 0) + 1
                text = _numbered_label(formats.get(num, "decimal"), num[1], counters[num], counters, num[0]) + " " + text
            lines.append(text)
        elif tag == "tbl":
            for row in block.iter():
                if row.tag.endswith("}tr"):
                    cells = ["".join(t.text or "" for t in c.iter() if t.tag.endswith("}t"))
                             for c in row if c.tag.endswith("}tc")]
                    lines.append("| " + " | ".join(c.strip() for c in cells) + " |")
            lines.append("")
    return "\n".join(lines) + "\n"


def _numbering_formats(d) -> dict[tuple[str, int], str]:
    """(numId, level) -> Word's number format (decimal, lowerLetter, lowerRoman, bullet ...), best effort."""
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    out: dict[tuple[str, int], str] = {}
    try:
        root = d.part.numbering_part.element
    except Exception:  # noqa: BLE001 - a document without list definitions
        return out
    abstract = {}
    for a in root.iter(f"{ns}abstractNum"):
        for lv in a.iter(f"{ns}lvl"):
            fmt = lv.find(f"{ns}numFmt")
            abstract[(a.get(f"{ns}abstractNumId"), int(lv.get(f"{ns}ilvl")))] = fmt.get(f"{ns}val") if fmt is not None else "decimal"
    for n in root.iter(f"{ns}num"):
        ref = n.find(f"{ns}abstractNumId")
        for (aid, lvl), fmt in abstract.items():
            if ref is not None and ref.get(f"{ns}val") == aid:
                out[(n.get(f"{ns}numId"), lvl)] = fmt
    return out


def _numbered_label(fmt: str, level: int, n: int, counters: dict, num_id: str) -> str:
    if fmt == "bullet" or fmt == "none":
        return "-"
    if fmt in ("lowerLetter", "upperLetter"):
        return f"({chr(96 + (n - 1) % 26 + 1)})"
    if fmt in ("lowerRoman", "upperRoman"):
        romans = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv"]
        return f"({romans[min(n, len(romans)) - 1]})"
    if level == 0:
        return f"{n}."
    parts = [counters.get((num_id, k), 1) for k in range(level + 1)]
    return ".".join(str(x) for x in parts)


SPLITTER_VERSION = "13"     # change it whenever the splitting rules change: cached splits are then ignored


def split_cached(path: str | Path, cache_dir: str | Path) -> tuple[str, list[Clause]]:
    """`split_document`, remembered: reading a long PDF takes minutes and the screens ask for the same split on every click.
    Keyed by the file's content and the splitter version, so an edited document or a new splitter is never served stale."""
    import hashlib

    path, cache_dir = Path(path), Path(cache_dir)
    key = hashlib.sha256(path.read_bytes() + SPLITTER_VERSION.encode()).hexdigest()[:32]
    f = cache_dir / f"split_{key}.json"
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return data["full"], [Clause(**c) for c in data["clauses"]]
        except (OSError, ValueError, KeyError, TypeError):
            pass                                              # a damaged cache is rebuilt, never trusted
    full, clauses = split_document(path)
    try:                       # the cache is an optimisation: several clauses are read at once, and a failed write never fails a read
        import uuid

        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.name}.{uuid.uuid4().hex}.tmp")      # one name per writer, so parallel readers never collide
        tmp.write_text(json.dumps({"full": full, "clauses": [asdict(c) for c in clauses]}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)
        for old in cache_dir.glob("split_*.json"):                # one split per project is enough
            if old != f:
                old.unlink(missing_ok=True)
    except OSError:
        pass
    return full, clauses


def write_clauses(path: str | Path, out: str | Path, cache_dir: str | Path | None = None) -> Path:
    """The clauses of a document as a file. With ``cache_dir`` the split is remembered for the screens that ask for it next."""
    full, clauses = split_cached(path, cache_dir) if cache_dir else split_document(path)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"doc": str(path), "full_text": full, "clauses": [asdict(c) for c in clauses]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return out
