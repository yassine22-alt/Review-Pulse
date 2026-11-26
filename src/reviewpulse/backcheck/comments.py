"""Previous comments: a list of dicts, loaded from a JSON file (a list, or an object with a "comments" list)."""

from __future__ import annotations

import json
from pathlib import Path

from .model import Comment

KEYS = ("id", "text", "code", "sheet", "page", "bbox")


def from_dict(d: dict, n: int = 0) -> Comment:
    """Accepts the common alternative names a review tool may export (comment, citation, sheet_number, rect)."""
    text = d.get("text") or d.get("comment") or d.get("body") or ""
    code = d.get("code") or d.get("citation") or d.get("code_section") or ""
    sheet = d.get("sheet") or d.get("sheet_number")
    bbox = d.get("bbox") or d.get("rect")
    page = d.get("page")
    return Comment(id=str(d.get("id", f"C{n + 1}")), text=str(text), code=str(code),
                   sheet=str(sheet) if sheet not in (None, "") else None,
                   page=int(page) if page not in (None, "") else None,
                   bbox=tuple(float(v) for v in bbox) if bbox else None)


def load_comments(path: str | Path) -> list[Comment]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("comments", [])
    return [from_dict(d, i) for i, d in enumerate(data)]


def save_comments(comments: list[Comment], path: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps([c.to_dict() for c in comments], indent=1), encoding="utf-8")
    return p


def from_review_comments(items) -> list[Comment]:
    """Previous cycle comments from the connectors' neutral model (`connectors.model.ReviewComment`)."""
    return [Comment(id=r.id, text=r.text, code=" ".join(x for x in (r.citation_doc, r.citation) if x), sheet=r.sheet or None,
                    page=r.page, bbox=tuple(r.bbox) if r.bbox else None) for r in items]


def load_markups(pdf: str | Path, cycle: int = 1) -> list[Comment]:
    """The reviewer's markups of an annotated PDF, read by the connectors (`connectors.pdf_io.read_annotations`)."""
    from ..connectors.pdf_io import read_annotations

    return from_review_comments(read_annotations(pdf, cycle=cycle).comments)
