"""One producer of fact graphs: the existing plan reader's BuildingModel.

Other producers (a schedule reader, an IFC reader, a person typing facts) write the same format directly.
Trust follows the interpreter's existing adapter: measurements are trusted only on an exact-vector plan with
a verified scale, openings below that need a confirmed element, labels read by a language model are untrusted.
"""

from __future__ import annotations

from pathlib import Path

from ..annotate.notes import DESCRIPTIONS, note_counts
from ..annotate.text_classify import tag_key
from ..interpreter.schema import Binding, Fact
from ..schema import BuildingModel
from .schema import Edge, FactGraph, Inventory, Node, Provenance

NOTE_BINDINGS = {name: Binding(
    kind="number", unit="count",
    description=f"How many times the sheet's text mentions {what} (notes, legend entries, callouts). A mention, not a measurement: "
                "it does not say where the item is or that it is of the right kind")
    for name, what in DESCRIPTIONS.items()}
BINDINGS = {**NOTE_BINDINGS,
    "room_type": Binding(kind="string", description="Room classification from its label"),
    "area_m2": Binding(kind="number", unit="m2", description="Measured net floor area"),
    "min_width_m": Binding(kind="number", unit="m", description="Measured minimum width of a room, hallway or other space"),
    "width_m": Binding(kind="number", unit="m", description="Clear width of a door or window opening, never of a room"),
    "has_window": Binding(kind="boolean", description="The room has a window"),
    "has_label": Binding(kind="boolean", description="The room is named on the drawing (its use is shown)"),
    "tag": Binding(kind="string", description="Schedule tag of the element"),
    "height_m": Binding(kind="number", unit="m", description="Height of the opening, from the door and window schedule"),
    "sill_height_m": Binding(kind="number", unit="m", description="Height of the window sill above the floor, from the schedule"),
    "opening_area_m2": Binding(kind="number", unit="m2", description="Area of the opening: its width times its scheduled height"),
    "window_area_m2": Binding(kind="number", unit="m2", description="Total area of the windows of the room (from the schedule)"),
    "window_area_ratio": Binding(kind="number", unit="1", description="Window area divided by the floor area of the room"),
    "scale_stated": Binding(kind="boolean", description="The sheet states its scale, or its scale could be found (the drawing is to scale)"),
    "is_dimensioned": Binding(kind="boolean", description="The drawing carries dimension annotations (it is dimensioned)"),
    "dimension_count": Binding(kind="number", unit="count", description="Number of dimension annotations on the sheet"),
    "leads_to_exit": Binding(kind="boolean", description="The door leads to the outside of the building (an exit door)"),
    "tread_depth_m": Binding(kind="number", unit="m", description="Stair tread depth (pitch of the tread lines)"),
    "stair_width_m": Binding(kind="number", unit="m", description="Stair flight width (length of the tread lines)"),
    "exit_distance_m": Binding(kind="number", unit="m",
                               description="Travel distance from the farthest point of the room to the outside"),
    "fire_rating_min": Binding(kind="number", unit="min", description="Fire resistance rating of the door, in minutes, from the door schedule"),
    "tread_lines": Binding(kind="number", unit="count", description="Number of tread lines drawn in the stair flight"),
}
STAIR_TRUST = 0.8                                   # calibrated probability a detected flight must reach to be trusted
SCALE_METHODS = ("dxf_units", "dimension_consensus", "user", "scale_bar")
BOUNDARY = {"EXIT": "exit", "EXTERIOR": "exterior"}
LOOKED_FOR = ("room", "door", "window", "opening", "stair")      # what this plan reader searches for


def room_labels(types: set[str]) -> dict[str, list[str]]:
    """Words documents use for each room type, any language, from the curated lexicon (short abbreviations dropped)."""
    import yaml

    path = Path(__file__).resolve().parents[1] / "annotate" / "lexicon" / "curated.yaml"
    table = yaml.safe_load(path.read_text(encoding="utf-8"))["types"]
    out = {}
    for kind in sorted(types):
        words = {kind.replace("_", " ")}
        for entries in (table.get(kind) or {}).values():
            for word in entries:
                if len(word) >= 4:
                    words |= {word, word + "s", word + "x"}
        out[kind] = sorted(words)
    return out


def schedule_rows(model) -> dict:
    """The rows of the door and window schedules by tag: what a plan view cannot show (the height of an opening, its sill)."""
    rows = {}
    for sched in getattr(model, "schedules", None) or []:
        for row in sched.get("rows", []):
            if row.get("tag"):
                rows[tag_key(str(row["tag"]))] = row
        for tag, minutes in (sched.get("fire_rows") or {}).items():      # door fire ratings of the general sheet table reader
            rows.setdefault(tag_key(str(tag)), {"tag": tag}).setdefault("fire_rating_min", minutes)
    return rows


def opening_areas(model, rows: dict) -> dict:
    """Area of each door and window whose height the schedule gives: width (drawn, else scheduled) times height."""
    out = {}
    for el in model.elements:
        row = rows.get(tag_key(el.tag)) if el.tag and el.cls in ("door", "window") else None
        width = el.attrs.get("width_m") if el.attrs.get("width_m") is not None else (row or {}).get("width_m")
        if row and row.get("height_m") is not None and width is not None:
            out[el.id] = float(width) * float(row["height_m"])
    return out


def window_area(model, room_id: str, areas: dict) -> float | None:
    """Total window area of a room, from the windows on its edges to the outside. Unknown (None) as soon as one of them has no
    scheduled height: a total with a window missing would pass a rule it should fail."""
    windows = [e for e in model.edges if e.kind == "window" and room_id in (e.a, e.b) and e.via]
    if not windows:
        return 0.0 if any(e.cls == "window" for e in model.elements) else None
    if any(e.via not in areas for e in windows):
        return None
    return sum(areas[e.via] for e in windows)


def set_notes(models) -> tuple[dict[str, int], bool] | None:
    """Mentions of safety provisions over every sheet of one submission (floor plans, general notes, schedules, details), and
    whether the text of every sheet was read. General notes usually sit on their own sheet, so a floor plan alone would say
    "no smoke alarm is mentioned" about a set that mentions it four times. None when no sheet had any text."""
    total: dict[str, int] = {}
    read_all, any_read = True, False
    for m in models:
        counts = note_counts(m.sheet.texts)
        if counts is None:
            read_all = False
            continue
        any_read = True
        for name, n in counts.items():
            total[name] = total.get(name, 0) + n
    return (total, read_all) if any_read else None


def from_building(model: BuildingModel, *, complete: bool = False, part_of_set: bool = False,
                  notes: tuple[dict[str, int], bool] | None = None) -> FactGraph:
    """`notes`: the result of `set_notes` over the whole submission; without it only this sheet's own text is counted.

    `part_of_set`: the sheet is one of several floor plans of one building. A level with no door to the outside leaves the
    building by stairs this sheet does not show, so "no route to the exit" is not proven there even when every room, door
    and window was found (the rooms are still complete; the routes are not)."""
    t1 = model.tier == "T1"
    scale_known = model.sheet.scale.method in SCALE_METHODS
    measured = t1 and scale_known
    nodes: list[Node] = []
    used: set[str] = set()

    def fact(name, value, source, trusted):
        if value is None:
            return None
        used.add(name)
        return Fact(value=value, source=source, trusted=trusted)

    distances = _exit_distances(model)
    rows = schedule_rows(model)
    opening_area = opening_areas(model, rows)
    labels_read = any(r.label for r in model.rooms)
    exit_openings = {e.via for e in model.edges if e.via and (e.a in BOUNDARY or e.b in BOUNDARY)}
    for room in model.rooms:
        src = f"{model.sheet.id}:{room.id}"
        label_ok = t1 and room.prov.evidence.get("label_source") not in ("llm", "vlm")
        # a room whose edges were placed from room names, not from drawn walls, has a size that is a guess: it can raise a warning,
        # never a failure
        sure = measured and room.prov.evidence.get("boundary") != "inferred_from_labels"
        attrs = {k: v for k, v in {
            "room_type": fact("room_type", room.type, src, label_ok),
            "area_m2": fact("area_m2", room.area_m2, src, sure),
            "min_width_m": fact("min_width_m", room.min_width_m, src, sure),
            "has_window": fact("has_window", room.has_window, src, measured),
            # a room with no name is a finding only when the sheet names rooms at all: when no name was read, the text was
            # probably not read (outlined text, no OCR), and that is not the same as a drawing that names no room
            "has_label": fact("has_label", bool(room.label), src, label_ok and labels_read),
            # a walked distance needs the geometry and the scale; how rooms connect is derived from the graph below
        }.items() if v is not None}
        glazing = window_area(model, room.id, opening_area)
        if glazing is not None:
            used.update(("window_area_m2",))
            attrs["window_area_m2"] = Fact(value=round(glazing, 4), source=src, trusted=measured)
            if room.area_m2:
                used.add("window_area_ratio")
                attrs["window_area_ratio"] = Fact(value=round(glazing / room.area_m2, 4), source=src, trusted=sure)
        if model.sheet.scale.metres_per_unit:
            # with a scale the distance is a fact of every room; where no route reaches the outside its value is unknown
            # (not absent), so a rule about it is undecided instead of impossible to write
            used.add("exit_distance_m")
            attrs["exit_distance_m"] = Fact(value=distances.get(room.id), source=src,
                                            trusted=sure and room.id in distances)
        nodes.append(Node(id=room.id, kind="room", label=room.label, attrs=attrs))
    for el in model.elements:
        if el.cls in ("wall", "other", "fixture"):
            continue
        src = f"{model.sheet.id}:{el.id}"
        if el.cls == "stair":
            ev = el.prov.evidence
            from ..perception.stairs import calibrated

            conf = calibrated(ev)
            sure = scale_known and bool(ev.get("trusted")) and (conf is None or conf >= STAIR_TRUST) or el.confirmed
            attrs = {k: v for k, v in {
                "tread_depth_m": fact("tread_depth_m", ev.get("tread_depth_m"), src, sure),
                "stair_width_m": fact("stair_width_m", ev.get("width_m"), src, sure),
                "tread_lines": fact("tread_lines", float(ev["n_levels"]) if "n_levels" in ev else None, src, sure),
            }.items() if v is not None}
            nodes.append(Node(id=el.id, kind="stair", attrs=attrs))
            continue
        trusted = scale_known and (t1 or el.confirmed)
        row = rows.get(tag_key(el.tag)) if el.tag else None
        height, sill = (row or {}).get("height_m"), (row or {}).get("sill_m")
        attrs = {k: v for k, v in {
            "width_m": fact("width_m", el.attrs.get("width_m"), src, trusted),
            "height_m": fact("height_m", height, src, t1 or el.confirmed),
            "sill_height_m": fact("sill_height_m", sill if el.cls == "window" else None, src, t1 or el.confirmed),
            "opening_area_m2": fact("opening_area_m2", opening_area.get(el.id), src, trusted),
            "tag": fact("tag", el.tag, src, t1 or el.confirmed),
            "fire_rating_min": fact("fire_rating_min", (row or {}).get("fire_rating_min") if el.cls == "door" else None, src,
                                    t1 or el.confirmed),
            # an exit door (egress door, entrance) is one whose far side is the outside; only a door has the property
            "leads_to_exit": fact("leads_to_exit", el.id in exit_openings, src, t1 or el.confirmed) if el.cls == "door" else None,
        }.items() if v is not None}
        nodes.append(Node(id=el.id, kind=el.cls, label=el.tag, attrs=attrs))
    # what the sheet itself says about the drawing: plan reviewers ask whether it is to scale and whether it is dimensioned
    whole = f"{model.sheet.id}:building"
    if not notes_enabled():
        counts, zero_ok = {}, False
    elif notes is not None:
        counts, zero_ok = notes                   # the whole set was searched: a zero counts when every sheet's text was read
    else:
        # words found are evidence wherever they sit; no words found is evidence only when this sheet is the whole submission
        # (a note on another sheet of the set would be missed), so a zero on a sheet that is part of a set stays untrusted
        counts, zero_ok = note_counts(model.sheet.texts) or {}, not part_of_set
    note_facts = {name: fact(name, float(n), whole, t1 and (n > 0 or zero_ok)) for name, n in counts.items()}
    nodes.append(Node(id="building", kind="building", role="whole", attrs={k: v for k, v in {
        **note_facts,
        "scale_stated": fact("scale_stated", model.sheet.scale.method != "none", whole, t1),
        "dimension_count": fact("dimension_count", float(len(model.sheet.dimensions)), whole, t1),
        "is_dimensioned": fact("is_dimensioned", len(model.sheet.dimensions) > 0, whole, t1),
    }.items() if v is not None}))
    # the outside is always declared: a plan with no door to it is a plan where "no route" is true, not a plan that
    # never mentioned an exit
    nodes += [Node(id=b, kind=kind, role="boundary") for b, kind in sorted(BOUNDARY.items())]

    confirmed = {e.id for e in model.elements if e.confirmed}
    edges = []
    for i, e in enumerate(model.edges):
        attrs = {}
        if e.width_m is not None:
            used.add("width_m")
            attrs["width_m"] = Fact(value=e.width_m, source=f"{model.sheet.id}:{e.via or i}", trusted=measured)
        inferred = bool(e.prov.evidence.get("inferred"))          # joined by label-seeded splitting, not by a drawn opening
        edges.append(Edge(id=f"e{i}", a=e.a, b=e.b, kind=e.kind, via=e.via, attrs=attrs,
                          trusted=(t1 or (e.via in confirmed)) and not inferred))
    known = {n.kind for n in nodes if n.role == "member"} | set(LOOKED_FOR)
    inventory = {k: Inventory(complete=complete, trusted=t1 or complete) for k in known}
    # the stair finder reaches about half of drawn stairs (see docs/progress/M7): its list is never claimed complete,
    # so a rule over stairs reads UNRESOLVED instead of passing because none were found
    inventory["stair"] = Inventory(complete=False, trusted=False)
    from .relations import derive_relations

    return derive_relations(FactGraph(
        provenance=Provenance(document=model.sheet.source_file, sheet=model.sheet.id, tier=model.tier,
                              scale=model.sheet.scale.method, producer="reviewpulse.building_model"),
        bindings={k: v for k, v in BINDINGS.items() if k in used}, nodes=nodes, edges=edges,
        inventory=inventory, graph_complete=complete and not (part_of_set and not any(
            e.a in BOUNDARY or e.b in BOUNDARY for e in model.edges)),
        value_labels={"room_type": room_labels(_room_vocabulary() | {n.attrs["room_type"].value for n in nodes
                                                                     if "room_type" in n.attrs})},
        passable=["door", "opening"], route_targets=["EXIT"]))


def notes_enabled() -> bool:
    """REVIEWPULSE_NOTES=0 leaves the note facts out (used to measure what they change)."""
    import os

    return os.environ.get("REVIEWPULSE_NOTES", "1") != "0"


def _exit_distances(model: BuildingModel) -> dict[str, float]:
    """Travel distance from the farthest point of each room to the outside, walked around corners, door to door: the
    same computation the rule engine uses for its travel-distance check. Empty when the scale is unknown or it fails."""
    if not model.sheet.scale.metres_per_unit:
        return {}
    try:
        from ..engine.context import Context
        from ..engine.traversal import _EscapeField

        ctx = Context.of(model)
        field = _EscapeField(ctx, ["door", "opening"])
        out = {}
        for room in model.rooms:
            far = field.farthest(room.id)
            if far is not None:
                out[room.id] = round(far[0] * ctx.mpu, 3)
        return out
    except Exception:  # noqa: BLE001 - a geometry problem leaves distances unknown; it never loses the plan
        return {}


def _room_vocabulary() -> set[str]:
    """Every room type the plan reader can name, so a rule may speak of a type this plan happens not to contain."""
    import yaml

    path = Path(__file__).resolve().parents[1] / "annotate" / "lexicon" / "curated.yaml"
    return set(yaml.safe_load(path.read_text(encoding="utf-8"))["types"])
