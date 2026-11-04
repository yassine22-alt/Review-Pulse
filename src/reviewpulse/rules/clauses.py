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
from dataclasses import asdict, dataclass
from pathlib import Path

ARTICLE_RE = re.compile(r"^\s*(?:#+\s*)?(Article|Art\.?)\s*(\d+(?:[.\-]\d+)*)\b", re.I)
NUMBERED_RE = re.compile(r"^\s*(?:#+\s*)?(\d+(?:\.\d+){0,3})[.)]?\s+(?=[A-ZÀ-Ýa-zà-ý])")
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


def _pdf_text(path: Path) -> tuple[str, list[tuple[int, int]], list[str]]:
    """Concatenated text, (page start offset, page number) list and table rows as text."""
    import pymupdf

    doc = pymupdf.open(path)
    parts, pages, rows = [], [], []
    off = 0
    for i, page in enumerate(doc):
        blocks = page.get_text("blocks", sort=True)
        txt = "\n".join(b[4].strip() for b in blocks if b[4].strip()) + "\n"
        pages.append((off, i))
        parts.append(txt)
        off += len(txt)
        try:
            for tab in page.find_tables().tables:
                for r in tab.extract():
                    cells = [c.strip() for c in r if c and c.strip()]
                    if cells:
                        rows.append((i, " | ".join(cells)))
        except Exception:  # noqa: BLE001 - table finder is best effort
            pass
    return "".join(parts), pages, rows


def _page_of(offset: int, pages: list[tuple[int, int]]) -> int:
    p = 0
    for start, num in pages:
        if start <= offset:
            p = num
    return p


def split_text(full: str, pages: list[tuple[int, int]] | None = None) -> list[Clause]:
    pages = pages or [(0, 0)]
    lines = full.splitlines(keepends=True)
    starts = []
    off = 0
    for ln in lines:
        starts.append(off)
        off += len(ln)
    marks = []      # (line index, id, kind, heading)
    current_article = None
    for i, ln in enumerate(lines):
        m = ARTICLE_RE.match(ln)
        if m:
            current_article = f"Art. {m.group(2)}"
            marks.append((i, current_article, "article", ln.strip()))
            continue
        m = HEADING_RE.match(ln)
        if m:
            marks.append((i, ln.strip()[:60], "heading", ln.strip()))
            continue
        m = NUMBERED_RE.match(ln)
        if m and len(ln.strip()) > len(m.group(1)) + 3:
            current_article = m.group(1)
            marks.append((i, m.group(1), "numbered", ln.strip()))
            continue
        m = SUBITEM_RE.match(ln)
        if m and current_article:
            marks.append((i, f"{current_article} {m.group(1)})", "subitem", ln.strip()))
    clauses = []
    for k, (i, cid, kind, heading) in enumerate(marks):
        j = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        start = starts[i]
        end = starts[j] if j < len(lines) else len(full)
        while end > start and full[end - 1] in "\n\r ":
            end -= 1
        parent = None
        if kind == "subitem":
            parent = cid.rsplit(" ", 1)[0]
        clauses.append(Clause(id=cid, heading=heading[:120], text=full[start:end], page=_page_of(start, pages),
                              start=start, end=end, parent=parent, kind=kind))
    # an article whose body is only sub-items keeps its own lead-in sentence
    return [c for c in clauses if c.kind != "heading"]


def split_document(path: str | Path) -> tuple[str, list[Clause]]:
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        full, pages, rows = _pdf_text(path)
        clauses = split_text(full, pages)
        for n, (pg, row) in enumerate(rows):
            start = len(full)
            full += row + "\n"
            clauses.append(Clause(id=f"table:{pg}:{n}", heading="table row", text=row, page=pg, start=start,
                                  end=start + len(row), kind="table_row"))
        return full, clauses
    if path.suffix.lower() == ".docx":
        full = _docx_text(path)
        return full, split_text(full)
    full = path.read_text(encoding="utf-8")
    return full, split_text(full)


def _docx_text(path: Path) -> str:
    """Paragraphs, then table rows (cells joined by " | "), in document order (needs python-docx)."""
    try:
        import docx
    except ImportError as e:
        raise RuntimeError('reading .docx needs python-docx: pip install -e ".[app]"') from e
    d = docx.Document(str(path))
    lines = []
    for block in d.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append("".join(t.text or "" for t in block.iter() if t.tag.endswith("}t")))
        elif tag == "tbl":
            for row in block.iter():
                if row.tag.endswith("}tr"):
                    cells = ["".join(t.text or "" for t in c.iter() if t.tag.endswith("}t"))
                             for c in row if c.tag.endswith("}tc")]
                    lines.append(" | ".join(c.strip() for c in cells))
    return "\n".join(lines) + "\n"


def write_clauses(path: str | Path, out: str | Path) -> Path:
    full, clauses = split_document(path)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"doc": str(path), "full_text": full, "clauses": [asdict(c) for c in clauses]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return out
