"""The neutral exchange model: one ReviewComment is one correction item, whatever system it travels to or comes from.

Every connector (PDF markups, BCF, Accela, Bluebeam, OpenGov, file drop) reads and writes this one shape, so a new
connector never has to understand findings, and the findings code never has to understand a connector.

Coordinates. `page` counts from 1. `bbox` is `[x0, y0, x1, y1]` in PDF points on the unrotated page, origin at the top left,
y growing downward (the PyMuPDF convention). `located` is False when the comment has no place on a page.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "reviewpulse.comments/1"
MM = 25.4 / 72          # one PDF point in millimetres (sheet space is paper millimetres, y up)

State = Literal["open", "information_requested", "deferred", "not_applicable", "addressed", "verified", "rejected",
                "dismissed"]
STATES: tuple[str, ...] = ("open", "information_requested", "deferred", "not_applicable", "addressed", "verified",
                           "rejected", "dismissed")
STATE_WORDS = {"open": "Open", "information_requested": "Information requested", "deferred": "Deferred",
               "not_applicable": "Not applicable", "addressed": "Addressed", "verified": "Verified",
               "rejected": "Rejected", "dismissed": "Dismissed"}
SEVERITIES = ("critical", "major", "minor", "info")


class StatusEntry(BaseModel):
    state: State
    by: str = ""
    at: str = Field("", description="ISO 8601 time, empty when unknown.")
    note: str = ""


class Reply(BaseModel):
    author: str = ""
    at: str = ""
    text: str = ""


class ReviewComment(BaseModel):
    id: str = Field(description="Stable id. Re-exporting the same finding gives the same id (used for idempotency).")
    number: int = Field(0, description="Item number in the correction list (1, 2, 3 ...). 0 when unknown.")
    discipline: str = ""
    citation: str = Field("", description="Code section the item rests on, e.g. 'R305.1'.")
    citation_doc: str = Field("", description="The requirement document the citation belongs to.")
    text: str = Field("", description="The correction wording shown to the applicant.")
    subject: str = Field("", description="Bluebeam 'Subject' of a markup read from a PDF.")
    sheet: str = ""
    page: int | None = Field(None, description="Page, counted from 1.")
    bbox: list[float] | None = Field(None, description="[x0, y0, x1, y1], PDF points, unrotated page, origin top left.")
    located: bool = False
    state: State = "open"
    severity: str = ""
    evidence_quote: str = Field("", description="Words from the plan that the item rests on.")
    source_facts: dict[str, Any] = Field(default_factory=dict, description="Detected and required values, missing facts.")
    cycle: int = 1
    author: str = ""
    created: str = ""
    modified: str = ""
    color: str = Field("", description="Markup colour as #rrggbb when read from a PDF.")
    status_history: list[StatusEntry] = Field(default_factory=list)
    replies: list[Reply] = Field(default_factory=list)
    origin: str = Field("reviewpulse", description="reviewpulse, pdf, bcf, csv or json: where the comment was built from.")


def json_schema() -> dict:
    """JSON Schema (draft 2020-12 as emitted by pydantic) of one comment and of the file wrapper."""
    one = ReviewComment.model_json_schema()
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "ReviewPulse comments file",
            "type": "object", "required": ["schema_version", "comments"],
            "properties": {"schema_version": {"const": SCHEMA_VERSION},
                           "comments": {"type": "array", "items": {"$ref": "#/$defs/ReviewComment"}}},
            "$defs": {**one.get("$defs", {}), "ReviewComment": {k: v for k, v in one.items() if k != "$defs"}}}


# ---- findings dicts to comments -------------------------------------------------------------------------------------

_FAIL_ORDER = {"FAIL": 0, "WARNING": 1, "NOT_EVALUATED": 2, "PASS": 3}


def stable_id(*parts) -> str:
    return "rp-" + hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _bbox_from_polygons(polys, height_pt: float | None) -> list[float] | None:
    pts = [p for poly in polys or [] for p in poly]
    if not pts or height_pt is None:
        return None
    xs = [p[0] / MM for p in pts]
    ys = [height_pt - p[1] / MM for p in pts]
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]


def _quote(ev: dict) -> str:
    for key in ("quote", "evidence_quote"):
        if ev.get(key):
            return str(ev[key])
    for item in ev.get("snippets") or ev.get("quotes") or []:
        text = item.get("text") if isinstance(item, dict) else item
        if text:
            return str(text)
    return ""


def from_findings(findings: Iterable[dict], *, sheets: dict[str, dict] | None = None, cycle: int = 1,
                  author: str = "ReviewPulse", include_pass: bool = False,
                  discipline_of: Callable[[dict], str] | None = None) -> list[ReviewComment]:
    """Build the correction list from findings dicts (the shape of `findings.json`; no other module is imported).

    `sheets` maps a sheet id to `{"page": <0-based page>, "height_pt": <page height in points>}`; it turns the evidence
    polygons (paper millimetres, y up) into a box on the page. A finding may instead carry `evidence.page` (from 1) and
    `evidence.bbox_pt` itself. FAIL and WARNING become `open`, NOT_EVALUATED becomes `information_requested` (the plan does
    not give a fact the rule needs), a dismissed finding becomes `dismissed`. PASS is left out unless asked for.
    """
    sheets = sheets or {}
    rows = []
    for f in findings:
        verdict = f.get("verdict", "FAIL")
        if verdict == "PASS" and not include_pass:
            continue
        rows.append(f)
    rows.sort(key=lambda f: (_FAIL_ORDER.get(f.get("verdict", "FAIL"), 9), str(f.get("rule_id", "")),
                             str(f.get("subject_ids", ""))))
    out: list[ReviewComment] = []
    for f in rows:
        ev = f.get("evidence") or {}
        src = f.get("source") or {}
        sheet_id = str(ev.get("sheet", ""))
        info = sheets.get(sheet_id, {})
        page = int(ev["page"]) if ev.get("page") else (int(info["page"]) + 1 if "page" in info else None)
        bbox = ev.get("bbox_pt") or _bbox_from_polygons(ev.get("polygons"), info.get("height_pt"))
        if bbox is None and ev.get("labels") and info.get("height_pt") is not None:
            lab = next((lab["at"] for lab in ev["labels"] if lab.get("at")), None)
            if lab:
                bbox = _bbox_from_polygons([[lab, lab]], info["height_pt"])
                bbox = [bbox[0] - 12, bbox[1] - 12, bbox[2] + 12, bbox[3] + 12]
        verdict = f.get("verdict", "FAIL")
        state = ev.get("state") if ev.get("state") in STATES else (
            "dismissed" if ev.get("dismissed") else "information_requested" if verdict == "NOT_EVALUATED" else "open")
        facts = {k: v for k, v in (("detected", f.get("detected")), ("required", f.get("required")),
                                   ("missing", ev.get("missing")), ("subjects", f.get("subject_ids") or None),
                                   ("verdict", verdict), ("rule_id", f.get("rule_id"))) if v not in (None, "", [])}
        cid = str(ev.get("finding_id") or stable_id(f.get("rule_id"), ",".join(map(str, f.get("subject_ids") or [])),
                                                    sheet_id, page))
        discipline = (discipline_of(f) if discipline_of else "") or str(ev.get("discipline") or src.get("discipline") or "")
        out.append(ReviewComment(
            id=cid, discipline=discipline, citation=str(src.get("clause") or ""), citation_doc=str(src.get("doc") or ""),
            text=str(f.get("message", "")), sheet=sheet_id, page=page, bbox=[float(x) for x in bbox] if bbox else None,
            located=bool(page and bbox), state=state, severity=str(f.get("severity", "")), evidence_quote=_quote(ev),
            source_facts=facts, cycle=cycle, author=author, origin="reviewpulse"))
    out.sort(key=lambda c: (c.discipline, c.page or 10**6, c.id))
    for n, c in enumerate(out, 1):
        c.number = n
    return out


# ---- JSON file ------------------------------------------------------------------------------------------------------


def dump(comments: Iterable[ReviewComment]) -> dict:
    return {"schema_version": SCHEMA_VERSION, "comments": [c.model_dump(mode="json") for c in comments]}


def load(data: dict) -> list[ReviewComment]:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unknown schema_version {data.get('schema_version')!r}, expected {SCHEMA_VERSION}")
    return [ReviewComment.model_validate(c) for c in data.get("comments", [])]


def short_text(c: ReviewComment, limit: int = 140) -> str:
    cite = f"[{c.citation}] " if c.citation else ""
    text = f"{cite}{c.text}".strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
