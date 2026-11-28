"""Plain data of the back check: a previous comment, the evidence for it, and the verdict. All of it saves as JSON."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

RESOLVED = "RESOLVED"
NOT_ADDRESSED = "NOT ADDRESSED"
CHANGED_NOT_SETTLED = "CHANGED BUT NOT SETTLED"
MOVED = "MOVED"
CANNOT_TELL = "CANNOT TELL"
STATUSES = (RESOLVED, NOT_ADDRESSED, CHANGED_NOT_SETTLED, MOVED, CANNOT_TELL)

BBox = tuple[float, float, float, float]


@dataclass
class Comment:
    """A comment of the previous cycle. `page` is 1 based (as a person counts), `bbox` is in the page frame of the old PDF in
    points (x right, y down, origin top left of the unrotated page, as PyMuPDF reports text and annotation boxes)."""
    id: str
    text: str
    code: str = ""
    sheet: str | None = None
    page: int | None = None
    bbox: BBox | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Place:
    """Where a comment's subject is, in one version: page (1 based), sheet number as printed, view title, box."""
    page: int | None = None
    sheet: str | None = None
    view: str = ""
    bbox: BBox | None = None


@dataclass
class Evidence:
    old_place: Place = field(default_factory=Place)
    new_place: Place = field(default_factory=Place)
    old_value: str = ""
    new_value: str = ""
    diff: str = ""                  # a small description of what changed there
    demand: str = ""                # what the comment asks for, as understood ("minimum 0.8 m", "note: ...")
    checks: list[str] = field(default_factory=list)
    person_must_check: str = ""     # what a person has to look at when the tools could not settle it
    crops: dict = field(default_factory=dict)   # old, new: PNG file names

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Verdict:
    comment: Comment
    status: str
    reason: str
    evidence: Evidence = field(default_factory=Evidence)
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"comment": self.comment.to_dict(), "status": self.status, "reason": self.reason,
                "evidence": self.evidence.to_dict(), "history": self.history}


@dataclass
class Region:
    """One place where the two versions differ, after alignment."""
    id: str
    sheet_old: str
    sheet_new: str
    page_old: int
    page_new: int
    bbox_old: BBox
    bbox_new: BBox
    view: str = ""
    n_removed: int = 0
    n_added: int = 0
    words_removed: list[str] = field(default_factory=list)
    words_added: list[str] = field(default_factory=list)
    clouded: bool | None = None     # None when the new PDF carries no revision cloud at all
    linked: list[str] = field(default_factory=list)   # comment ids this change answers

    def describe(self) -> str:
        parts = []
        if self.words_removed or self.words_added:
            parts.append(f"text '{' '.join(self.words_removed[:8])}' -> '{' '.join(self.words_added[:8])}'")
        parts.append(f"{self.n_removed} drawn objects removed, {self.n_added} added")
        return "; ".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)
