"""Data contracts shared by the Reader, the Interpreter and the Judge.

The three roles meet only at three files: ``sheet_<n>.json`` (what was drawn),
``building_<n>.json`` (what it means) and ``findings.json`` (what is wrong).

Conventions (see docs/DECISIONS.md, D6):
- geometry is stored in sheet space, y axis up;
- units are paper millimetres for PDF/raster and drawing units for DXF;
- real metres only through ``Sheet.scale.metres_per_unit`` (None = unknown).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1"

Point = tuple[float, float]
Tier = Literal["T1", "T2", "T3"]


def F(default=..., d: str = "", **kw):
    """Field with a description. The descriptions are the documented contract: docs/extraction_schema.md
    and schemas/*.schema.json are generated from them (scripts/gen_docs.py)."""
    return Field(default, description=d, **kw)


class Prov(BaseModel):
    """Where a value came from and how sure the stage that produced it is."""
    source: Literal["vector", "raster", "ocr", "user", "derived"] = F(d="Kind of input the value was read or derived from.")
    stage: str = F(d="Producing stage and version, e.g. `pdf_extract`, `walls_pairs_v1`.")
    confidence: float = F(1.0, d="Stage confidence in [0, 1]; a calibrated probability only where the stage says so.")
    evidence: dict = F(default_factory=dict, d='Stage-specific evidence, e.g. `{"layer": "A-WALL"}`; classifier '
                       "probabilities `p_wall`, `p_door`; dataset ground truth under `gt` (evaluation only).")


class Primitive(BaseModel):
    """One drawn mark as found in the file: line, arc, polyline, polygon or circle."""
    id: str = F(d="Stable id, unique within the sheet.")
    kind: Literal["line", "arc", "polyline", "polygon", "circle"] = F(d="Geometry kind.")
    pts: list[Point] = F([], d="Line: 2 points; polyline / polygon: n points (a polygon is implicitly closed).")
    center: Point | None = F(None, d="Arc / circle centre.")
    radius: float | None = F(None, d="Arc / circle radius, sheet units.")
    a0: float | None = F(None, d="Arc start angle, degrees counter-clockwise from +x.")
    a1: float | None = F(None, d="Arc end angle, degrees counter-clockwise from +x.")
    layer: str | None = F(None, d="CAD layer, PDF optional-content group or SVG group, when the file has one.")
    width: float | None = F(None, d="Stroke width, sheet units.")
    color: str | None = F(None, d="Stroke colour as written in the file.")
    dashed: bool = F(False, d="Drawn with a dash pattern.")
    filled: bool = F(False, d="Filled region (solid hatch, filled PDF path).")
    block: str | None = F(None, d="DXF block name, or `dim:<id>` for dimension graphics.")
    hidden: bool = F(False, d="Superseded by a derived primitive (e.g. segments replaced by a fitted arc).")
    prov: Prov


class TextItem(BaseModel):
    """A text run (vector text or OCR) with its classification."""
    id: str
    text: str = F(d="Text as read.")
    bbox: tuple[float, float, float, float] = F(d="(x0, y0, x1, y1), sheet units.")
    rotation_deg: float = F(0.0, d="Baseline rotation, degrees counter-clockwise.")
    height: float | None = F(None, d="Character height, sheet units.")
    layer: str | None = None
    kind: Literal["room_label", "area", "dimension", "tag", "note", "title_block", "unknown"] = F(
        "unknown", d="Role assigned by the text classifier (R6).")
    value: float | None = F(None, d="Parsed number, in `unit`.")
    unit: Literal["mm", "cm", "m", "m2"] | None = None
    norm: str | None = F(None, d="Normalised value: room type (`bedroom`), tag key (`D1`) or title-block field.")
    prov: Prov


class Scale(BaseModel):
    """Drawing-to-metres conversion. Metres exist only through this object (D6)."""
    metres_per_unit: float | None = F(None, d="Metres per sheet unit; None = unknown.")
    method: Literal["dxf_units", "dimension_consensus", "title_block", "scale_bar", "user",
                    "symbol_prior", "none"] = F("none", d="How the scale was obtained. `dxf_units`, "
                                                "`dimension_consensus`, `user` and `scale_bar` count as verified.")
    confidence: float = F(0.0, d="Confidence of the scale estimate in [0, 1].")
    n_candidates: int = F(0, d="Dimension candidates considered.")
    n_inliers: int = F(0, d="Candidates agreeing with the chosen scale.")


class Dimension(BaseModel):
    """A dimension: its stated value, what it measures and what was drawn."""
    id: str
    text_id: str | None = F(None, d="TextItem holding the value.")
    value_m: float | None = F(None, d="Stated value in metres (parsed text or DXF override).")
    measured_m: float | None = F(None, d="Drawn length x scale, metres.")
    p1: Point = F(d="First measured feature point (extension-line end).")
    p2: Point = F(d="Second measured feature point.")
    line_ids: list[str] = F([], d="Primitives forming the dimension graphic.")
    measured_ids: list[str] = F([], d="Elements the ends touch.")
    chain_id: str | None = F(None, d="Dimension chain this belongs to.")
    prov: Prov


class Layout(BaseModel):
    """Regions of the sheet, (x0, y0, x1, y1) in sheet units."""
    frame: tuple[float, float, float, float] | None = F(None, d="Drawing frame.")
    plan_box: tuple[float, float, float, float] | None = F(None, d="Area holding the plan itself.")
    title_block: tuple[float, float, float, float] | None = None
    tables: list[tuple[float, float, float, float]] = F([], d="Schedules and other tables.")


class Sheet(BaseModel):
    """`sheet_<n>.json`: what was drawn on one page or layout (the Reader's output)."""
    schema_version: str = SCHEMA_VERSION
    id: str
    source_file: str
    page: int = F(0, d="Page (PDF) or layout index, from 0.")
    mode: Literal["vector", "raster", "mixed"] = F(d="Whether geometry came from vector content, pixels, or both.")
    coord_unit: Literal["paper_mm", "drawing_unit"] = F(d="Sheet units: paper millimetres (PDF, raster, SVG) or "
                                                        "drawing units (DXF).")
    width: float = F(d="Sheet width, sheet units.")
    height: float = F(d="Sheet height, sheet units.")
    rotation: int = F(0, d="Page rotation applied at extraction, degrees.")
    sheet_type: Literal["floor_plan", "schedule", "structural", "site", "other", "unknown"] = "unknown"
    scale: Scale = Scale()
    layout: Layout = Layout()
    primitives: list[Primitive] = []
    texts: list[TextItem] = []
    dimensions: list[Dimension] = []
    layers: list[str] = []
    warnings: list[str] = F([], d="Human-readable notes from every stage (fallbacks taken, data missing).")


class Element(BaseModel):
    """A building element interpreted from primitives. Keys of `attrs` per class: ELEMENT_ATTRS."""
    id: str
    cls: Literal["wall", "door", "window", "opening", "stair", "column", "fixture", "other"] = F(
        d="Element class; `other` holds wall candidates below the acceptance score.")
    geom: list[Point] = F(d="Wall: centreline (2 points); other classes: footprint polygon.")
    thickness: float | None = F(None, d="Wall thickness, sheet units.")
    attrs: dict = F(default_factory=dict, d="Class-specific attributes, see ELEMENT_ATTRS.")
    member_ids: list[str] = F([], d="Primitives this element was built from.")
    tag: str | None = F(None, d="Schedule tag (`D1`, `P02`) associated with the element.")
    confirmed: bool = F(False, d="Confirmed by a user or a calibrated threshold; a FAIL below T1 needs this.")
    prov: Prov


class Room(BaseModel):
    """An enclosed space."""
    id: str
    polygon: list[Point] = F(d="Outer boundary, sheet units.")
    holes: list[list[Point]] = []
    label: str | None = F(None, d="Label text as drawn.")
    type: str | None = F(None, d="Normalised room type (rules/vocab.yaml): bedroom, bathroom, kitchen...")
    stated_area_m2: float | None = F(None, d="Area written on the drawing.")
    area_m2: float | None = F(None, d="Measured area; None when the scale is unknown.")
    min_width_m: float | None = F(None, d="Smallest clear width.")
    is_corridor: bool = False
    has_window: bool | None = None
    prov: Prov


class Edge(BaseModel):
    """A connection between two rooms, or from a room to the outside."""
    a: str = F(d="Room id.")
    b: str = F(d="Room id, `EXIT` (leads out of the building) or `EXTERIOR` (outdoor annex, vehicle door).")
    kind: Literal["door", "opening", "window", "adjacent"]
    via: str | None = F(None, d="Element id of the door or opening.")
    width_m: float | None = None
    prov: Prov


class BuildingModel(BaseModel):
    """`building_<n>.json`: what the sheet means (the Interpreter's output)."""
    schema_version: str = SCHEMA_VERSION
    sheet: Sheet
    elements: list[Element] = []
    rooms: list[Room] = []
    edges: list[Edge] = []
    schedules: list[dict] = F([], d='Parsed tables, e.g. `{"name": "doors", "rows": [{"tag": "P1", "width_m": 0.9}]}`.')
    tier: Tier = F("T3", d="Evidence tier: T1 exact vector with a verified scale, T2 vector with estimated parts "
                   "or a scan with a verified scale, T3 estimated.")


class Finding(BaseModel):
    """One rule result (the Judge's output, `findings.json`)."""
    rule_id: str
    verdict: Literal["PASS", "WARNING", "FAIL", "NOT_EVALUATED"]
    severity: Literal["critical", "major", "minor", "info"]
    subject_ids: list[str] = F(d="Rooms or elements the finding is about.")
    message: str
    detected: str | None = F(None, d="What was measured, e.g. `0.70 m`.")
    required: str | None = F(None, d="What the rule requires, e.g. `>= 0.80 m`.")
    tier: Tier
    evidence: dict = F(default_factory=dict, d="Witness path, dimension chain, polygons to draw.")
    source: dict = F(default_factory=dict, d="Requirement source: `{doc, clause, span}`.")


# ---------------------------------------------------------------------------
# Element.attrs contract: key -> (accepted types, meaning). Enforced on pipeline output by check_attrs.

# keys every class may carry (set by core/tiers.py)
_COMMON = {
    "confirmed_by": ((str,), "`user`, or the calibrated threshold that confirmed the element."),
    "needs_confirmation": ((bool,), "Estimated element: findings on it stay WARNING until confirmed."),
}
_OPENING = {
    "width_m": ((float, int, type(None)), "Clear width in metres (None when the scale is unknown)."),
    "mid": ((tuple, list), "Opening midpoint on the wall axis, sheet units."),
    "normal": ((tuple, list), "Unit normal of the host wall at the opening."),
    "thickness": ((float, int), "Host wall thickness, sheet units."),
    "wall_id": ((str, type(None)), "Host wall element."),
    "wall_ids": ((list,), "Walls on both sides of the gap."),
    "jambs": ((list,), "The two jamb points of the gap."),
    "block": ((str,), "DXF block the opening was inserted as."),
    "glazing_lines": ((int,), "Glazing lines found across the gap (windows)."),
    "rooms": ((list,), "[room on one side, room on the other] (None = outside), set by R10."),
    "tag_text_id": ((str,), "Text item of the associated schedule tag."),
    "source": ((str,), "Producer when not the vector rules: `raster`, `learned`."),
    "carried": ((bool,), "Kept from the rule pass and re-hosted on the learned-pass walls."),
    **_COMMON,
}
_DOOR = dict(_OPENING, **{
    "hinge": ((tuple, list), "Hinge point, sheet units."),
    "hinges": ((list,), "Both hinge points of a double door."),
    "radius": ((float, int), "Swing radius, sheet units."),
    "double": ((bool,), "Double-leaf door."),
    "swing_polygon": ((list,), "Area swept by the leaf (or leaves), sheet units."),
    "leaf_swings": ((list,), "Area swept by each leaf of a double door."),
    "swing_side": ((int,), "+1 / -1: side of the wall normal the door opens to."),
    "width_source": ((str,), "`arc_radius` / `arc_radii`: how the width was measured."),
    "no_gap": ((bool,), "Door symbol found with no wall gap (wall drawn through)."),
})
_WALL = {
    "candidate": ((bool,), "Below the acceptance score (cls `other`)."),
    "source": ((str,), "`pairs`, `filled`, `thick_line`, `learned_face`, `raster`..."),
    "thickness_m": ((float, int), "Thickness in metres."),
    "thickness_px": ((float, int), "Thickness in pixels (raster)."),
    "connected": ((list,), "[start, end]: joined to another wall."),
    **_COMMON,
}
ELEMENT_ATTRS: dict[str, dict[str, tuple]] = {
    "wall": _WALL, "other": _WALL, "door": _DOOR, "window": _OPENING, "opening": _OPENING,
    "column": _COMMON, "stair": _COMMON, "fixture": _COMMON,
}


def check_attrs(model: BuildingModel) -> list[str]:
    """Contract violations in element attrs: unknown keys and wrong value types."""
    out = []
    for e in model.elements:
        spec = ELEMENT_ATTRS.get(e.cls, {})
        for k, v in e.attrs.items():
            if k not in spec:
                out.append(f"{e.cls} {e.id}: unknown attrs key {k!r}")
            elif not isinstance(v, spec[k][0]):
                out.append(f"{e.cls} {e.id}: attrs[{k!r}] is {type(v).__name__}")
    return out


# ---------------------------------------------------------------------------
# JSON helpers. Loaders refuse an unknown major schema version (rule 6).

M = TypeVar("M", bound=BaseModel)


class SchemaVersionError(ValueError):
    pass


def _check_version(data: dict) -> None:
    v = str(data.get("schema_version", SCHEMA_VERSION))
    if v.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise SchemaVersionError(f"unsupported schema_version {v} (this build reads {SCHEMA_VERSION})")


def save(model: BaseModel, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=1), encoding="utf-8")
    return path


def load(cls: type[M], path: str | Path) -> M:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "schema_version" in data:
        _check_version(data)
    return cls.model_validate(data)


def save_findings(findings: list[Finding], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([f.model_dump() for f in findings], indent=1), encoding="utf-8")
    return path


def load_findings(path: str | Path) -> list[Finding]:
    return [Finding.model_validate(d) for d in json.loads(Path(path).read_text(encoding="utf-8"))]
