"""Readers for requirement documents that are not prose files: spreadsheets, web pages and scanned pages.

Building departments publish their plan-review checklists as Excel sheets, web pages and scans of paper forms as often as PDFs.
Each reader here turns one of them into the same plain text the clause splitter already understands: a heading is a "# " line, a
list item a "- " line, a table row cells joined by " | ". Nothing else about the document is guessed, so a clause found in a
spreadsheet cites the same kind of text span as one found in a PDF.

OCR is a fallback for pages that have no text layer; it uses RapidOCR (ONNX, no external program) when it is installed.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

SHEET_TYPES = {".xlsx", ".xlsm", ".csv", ".tsv"}
HTML_TYPES = {".html", ".htm"}
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def _clean(cell) -> str:
    if cell is None:
        return ""
    if isinstance(cell, float) and cell == int(cell):
        cell = int(cell)
    return re.sub(r"\s+", " ", str(cell)).strip()


def _is_prose(cell: str) -> bool:
    """A cell that is a sentence (several words) and not a label or a number."""
    return len(re.findall(r"[^\W\d_]{2,}", cell)) >= 4


ANSWER_CELL = re.compile(r"^(?:[xX✓✔√☐☑□■○●-]|y(?:es)?|no?|n/?a|n\.a\.|ok|pass|fail|done|complete|approved|"
                         r"(?:y(?:es)?|no?|n\.?/?a\.?)(?:\s*[/,|]\s*(?:y(?:es)?|no?|n\.?/?a\.?))+)$", re.I)


def _is_answer(cell: str) -> bool:
    """A cell where a reviewer ticks or writes the outcome ("yes / no / n.a."): it is not part of the requirement."""
    return bool(ANSWER_CELL.match(cell.strip())) or bool(re.fullmatch(r"\d{1,3}[.)]?", cell.strip()))      # or the row number


def rows_to_text(rows: list[list[str]], title: str = "") -> str:
    """One sheet as text. A sheet whose rows each hold one sentence (a checklist) becomes a list; a grid of short cells (a table of
    limits) keeps its columns, the first row being the header, so that a row can be read with the column names above it."""
    rows = [[_clean(c) for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""
    out = [f"# {title}", ""] if title else []
    width = max(len(r) for r in rows)
    filled = [[c for c in r if c and not _is_answer(c)] for r in rows]
    prose_rows = sum(1 for r in filled if any(_is_prose(c) for c in r))
    if prose_rows >= max(2, 0.5 * len(rows)) and width <= 12:
        # a checklist: the longest cell of a row is the requirement; a short cell beside it (a code, a "yes") is kept with it
        for r in filled:
            if not r:
                continue
            if len(r) == 1 and not _is_prose(r[0]):
                out += ["", f"# {r[0]}", ""] if len(r[0]) < 80 else [r[0]]            # a lone short cell is a section title
                continue
            main = max(r, key=len)
            rest = [c for c in r if c is not main]
            out.append("- " + main + ("  (" + "; ".join(rest) + ")" if rest and all(len(c) < 40 for c in rest) else ""))
            if rest and any(len(c) >= 40 for c in rest):
                out += ["- " + c for c in rest if len(c) >= 40]
        return "\n".join(out) + "\n"
    out.append("")
    for r in filled:
        out.append(" | ".join(r) if len(r) >= 2 else r[0])
    return "\n".join(out) + "\n"


def _delimited(text: str, suffix: str) -> list[list[str]]:
    """Rows of a delimited text file. The delimiter is the one that cuts most rows into the same number of columns (csv.Sniffer gives
    up on prose); a file in which none does is a single column."""
    best, best_score = None, 0.0
    candidates = ("\t", ",", ";", "|") if suffix == ".tsv" else (",", ";", "\t", "|")
    for delim in candidates:
        try:
            rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
        except csv.Error:
            continue
        if len(rows) < 2:
            continue
        counts = [len(r) for r in rows]
        mode = max(set(counts), key=counts.count)
        score = (counts.count(mode) / len(rows)) * (1 if mode >= 2 else 0)
        if score > best_score + 1e-9:
            best, best_score = rows, score
    if best is not None and best_score >= 0.6:
        return best
    return [[line] for line in text.splitlines()]


def sheet_text(path: Path) -> str:
    """Every sheet of a workbook (or the rows of a csv/tsv file), one block per sheet. Needs openpyxl for Excel files."""
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        return rows_to_text(_delimited(text, ".tsv" if suffix == ".tsv" else ".csv"))
    try:
        import openpyxl
    except ImportError as e:
        raise RuntimeError('reading .xlsx needs openpyxl: pip install openpyxl') from e
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        blocks = []
        for ws in wb.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            blocks.append(rows_to_text([list(r) for r in ws.iter_rows(values_only=True)],
                                       title=ws.title if len(wb.worksheets) > 1 else ""))
        return "\n".join(b for b in blocks if b.strip())
    finally:
        wb.close()          # a read-only workbook keeps the file open; on Windows the file could then not be replaced or deleted


BLOCK_TAGS = {"p", "div", "section", "article", "li", "tr", "table", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
              "blockquote", "pre", "br", "header", "footer", "main", "form", "fieldset", "figure", "figcaption", "caption"}
SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head", "nav"}


def html_text(path: Path) -> str:
    """A web page as text: headings, list items, table rows and paragraphs, in document order (needs lxml)."""
    from lxml import html

    raw = path.read_bytes()
    root = html.fromstring(raw)
    out: list[str] = []

    def text_of(el) -> str:
        return re.sub(r"\s+", " ", el.text_content()).strip()

    def walk(el):
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag in SKIP_TAGS:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            t = text_of(el)
            if t:
                out.extend(["", "# " + t, ""])
            return
        if tag == "tr":
            cells = [text_of(c) for c in el if isinstance(c.tag, str) and c.tag in ("td", "th")]
            cells = [c for c in cells if c]
            if len(cells) >= 2:
                out.append(" | ".join(cells))
            elif cells:
                out.append(cells[0])
            return
        if tag == "li" and not any(isinstance(c.tag, str) and c.tag in ("ul", "ol") for c in el):
            t = text_of(el)
            if t:
                out.append("- " + t)
            return
        if tag in ("p", "pre", "blockquote", "figcaption", "caption", "dt", "dd") and not any(
                isinstance(c.tag, str) and c.tag in BLOCK_TAGS for c in el):
            t = text_of(el)
            if t:
                out.extend(["", t, ""])
            return
        if el.text and el.text.strip() and tag in ("div", "section", "article", "body", "td", "th"):
            out.append(el.text.strip())
        for child in el:
            walk(child)
            if child.tail and child.tail.strip():
                out.append(child.tail.strip())

    walk(root.find("body") if root.find("body") is not None else root)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


_ENGINE = None


def ocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def ocr_lines(png_or_array) -> list[str]:
    """The lines of text in an image, top to bottom (needs rapidocr_onnxruntime). Words on one visual line are joined."""
    global _ENGINE
    from rapidocr_onnxruntime import RapidOCR

    if _ENGINE is None:
        _ENGINE = RapidOCR()
    result, _ = _ENGINE(png_or_array)
    if not result:
        return []
    items = []
    for box, text, score in result:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append((min(ys), max(ys), min(xs), text))
    items.sort(key=lambda t: (t[0] + t[1]) / 2)
    lines, cur, cur_y = [], [], None
    for top, bottom, left, text in items:
        mid, height = (top + bottom) / 2, max(bottom - top, 1)
        if cur and abs(mid - cur_y) > 0.6 * height:
            lines.append(" ".join(t for _, t in sorted(cur)))
            cur = []
        cur.append((left, text))
        cur_y = mid if len(cur) == 1 else cur_y
    if cur:
        lines.append(" ".join(t for _, t in sorted(cur)))
    return lines


def ocr_image_text(path: Path) -> str:
    """A photo or scan of a requirement page as text. Paragraphs are lines; a line that starts a list item keeps its marker."""
    if not ocr_available():
        raise RuntimeError("reading a scanned page needs OCR: pip install rapidocr-onnxruntime")
    lines = ocr_lines(str(path))
    return join_ocr_lines(lines)


def join_ocr_lines(lines: list[str]) -> str:
    """OCR returns one string per visual line. A line that does not start a new item continues the one before it (the way the text
    of a PDF block is wrapped), so a requirement that runs over two lines is one sentence for the splitter."""
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        starts_item = bool(re.match(r"^(?:[-*•–▪●○□☐]\s|\(?[a-z0-9]{1,3}[.)]\s|\d+(?:\.\d+)+\s+[A-Z])", s))
        ends = out and out[-1].rstrip().endswith((".", ":", ";", "!", "?"))
        if out and not starts_item and not ends:
            out[-1] = out[-1].rstrip() + " " + s
        else:
            out.append(s)
    return "\n".join(out) + "\n"
