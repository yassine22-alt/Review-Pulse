"""The data classes of the drawing set model. Everything is plain data so it can be saved as JSON and compared in tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .scale import Scale

BBox = tuple[float, float, float, float]


@dataclass
class View:
    id: str                      # "<sheet index>.<n>"
    sheet: int                   # page index
    kind: str                    # plan, section, elevation, detail, schedule, legend, notes, site, index, unknown
    title: str
    labels: list[str]            # numbers or letters other views can call it by ("4", "A-A")
    bbox: BBox                   # the view's own coordinate frame: this box in page points
    title_bbox: BBox | None = None
    scale: Scale | None = None
    scale_source: str = "none"   # title, own line, region, sheet, none
    level: str | None = None     # label of the level (plan views)
    level_rank: int | None = None
    n_lines: int = 0
    n_paths: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scale"] = self.scale.to_dict() if self.scale else None
        return d


@dataclass
class Sheet:
    index: int                   # page index in the file
    number: str | None           # as printed in the title block
    number_source: str           # title block, page index (fallback), none
    title: str | None
    width: float
    height: float
    title_block: BBox | None = None
    default_scale: Scale | None = None
    has_text_layer: bool = True
    views: list[View] = field(default_factory=list)
    unassigned_lines: int = 0
    n_lines: int = 0

    @property
    def key(self) -> str:
        from .vocab import norm_id
        return norm_id(self.number) if self.number else f"P{self.index + 1}"

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if k not in ("views", "default_scale")}
        d["default_scale"] = self.default_scale.to_dict() if self.default_scale else None
        d["views"] = [v.to_dict() for v in self.views]
        return d


@dataclass
class Callout:
    sheet: int                   # page the callout is drawn on
    text: str
    grammar: str
    view_label: str | None
    target_sheet: str | None     # as written
    kind: str | None             # detail, section, elevation if the words said so
    where: BBox
    source_view: str | None = None
    status: str = "unresolved"   # view, sheet, partial, unresolved_sheet, unresolved_view, ambiguous, rejected_shape, in_legend
    target_view: str | None = None
    target_sheet_index: int | None = None
    reason: str = ""
    alt: tuple[str, str] | None = None   # the other reading of a bubble: (view label, sheet)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LegendEntry:
    sheet: int
    view: str
    words: str
    symbol_bbox: BBox | None     # region of the drawn symbol on the page; None for a words-only entry
    n_paths: int
    row_bbox: BBox

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IndexEntry:
    number: str
    title: str
    sheet: int                   # page the index is on
    status: str = ""             # match, title differs, not in set
    matched_sheet: int | None = None
    similarity: float | None = None
    view: str = ""               # the index view the entry was read from

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DrawingSet:
    name: str
    method: str
    sheets: list[Sheet]
    callouts: list[Callout]
    legend: list[LegendEntry]
    index: list[IndexEntry]
    index_missing: list[str] = field(default_factory=list)   # sheets with a title block number not listed in the index
    shapes: list[str] = field(default_factory=list)

    def views(self) -> list[View]:
        return [v for s in self.sheets for v in s.views]

    def sheet_by_key(self) -> dict[str, Sheet]:
        out: dict[str, Sheet] = {}
        for s in self.sheets:
            out.setdefault(s.key, s)
        return out

    def to_dict(self) -> dict:
        return {"name": self.name, "method": self.method, "shapes": self.shapes,
                "sheets": [s.to_dict() for s in self.sheets], "callouts": [c.to_dict() for c in self.callouts],
                "legend": [e.to_dict() for e in self.legend], "index": [i.to_dict() for i in self.index],
                "index_missing": self.index_missing}
