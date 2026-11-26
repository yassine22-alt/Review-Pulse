"""Status history of each comment across cycles, with the allowed moves of the state machine.

A comment that was RESOLVED is closed: it is not carried to the next cycle. If a later check of the same comment finds it
not resolved, that is recorded as a regression and flagged, never silently reopened."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .model import (
    CANNOT_TELL,
    CHANGED_NOT_SETTLED,
    MOVED,
    NOT_ADDRESSED,
    RESOLVED,
    STATUSES,
    Comment,
    Verdict,
)

ALLOWED = {
    None: set(STATUSES),
    NOT_ADDRESSED: set(STATUSES),
    CHANGED_NOT_SETTLED: set(STATUSES),
    MOVED: set(STATUSES),
    CANNOT_TELL: set(STATUSES),
    RESOLVED: {RESOLVED},                       # closed; anything else is a regression
}


class History:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.data: dict[str, list[dict]] = {}
        if self.path and self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def last(self, cid: str) -> str | None:
        h = self.data.get(cid)
        return h[-1]["status"] if h else None

    def record(self, cycle: int, verdicts: list[Verdict]) -> list[Verdict]:
        for v in verdicts:
            prev = self.last(v.comment.id)
            entry = {"cycle": cycle, "status": v.status, "reason": v.reason, "at": datetime.now(UTC).isoformat(timespec="seconds"),
                     "old_page": v.evidence.old_place.page, "new_page": v.evidence.new_place.page}
            if v.status not in ALLOWED[prev]:
                entry["regression"] = True
                entry["from"] = prev
            self.data.setdefault(v.comment.id, []).append(entry)
            v.history = list(self.data[v.comment.id])
        return verdicts

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")


def carry_forward(verdicts: list[Verdict]) -> list[Comment]:
    """The comments for the next cycle: the ones not resolved, moved to where they now are (sheet number, page, box)."""
    out = []
    for v in verdicts:
        if v.status == RESOLVED:
            continue
        c = v.comment
        np_ = v.evidence.new_place
        if v.status in (MOVED, NOT_ADDRESSED, CHANGED_NOT_SETTLED) and np_.page:
            c = Comment(c.id, c.text, c.code, np_.sheet or c.sheet, np_.page, np_.bbox or c.bbox)
        out.append(c)
    return out
