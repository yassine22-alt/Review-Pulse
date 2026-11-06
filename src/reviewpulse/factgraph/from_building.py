"""One producer of fact graphs: the existing plan reader's BuildingModel.

Other producers (a schedule reader, an IFC reader, a person typing facts) write the same format directly.
Trust follows the interpreter's existing adapter: measurements are trusted only on an exact-vector plan with
a verified scale, openings below that need a confirmed element, labels read by a language model are untrusted.
"""

from __future__ import annotations

from pathlib import Path

from ..interpreter.schema import Binding, Fact
from ..schema import BuildingModel
from .schema import Edge, FactGraph, Inventory, Node, Provenance

BINDINGS = {
    "room_type": Binding(kind="string", description="Room classification from its label"),
    "area_m2": Binding(kind="number", unit="m2", description="Measured net floor area"),
    "min_width_m": Binding(kind="number", unit="m", description="Measured minimum width"),
    "width_m": Binding(kind="number", unit="m", description="Clear width of an opening"),
    "has_window": Binding(kind="boolean", description="The room has a window"),
    "tag": Binding(kind="string", description="Schedule tag of the element"),
    "tread_depth_m": Binding(kind="number", unit="m", description="Stair tread depth (pitch of the tread lines)"),
    "stair_width_m": Binding(kind="number", unit="m", description="Stair flight width (length of the tread lines)"),
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


def from_building(model: BuildingModel, *, complete: bool = False) -> FactGraph:
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

    for room in model.rooms:
        src = f"{model.sheet.id}:{room.id}"
        label_ok = t1 and room.prov.evidence.get("label_source") not in ("llm", "vlm")
        attrs = {k: v for k, v in {
            "room_type": fact("room_type", room.type, src, label_ok),
            "area_m2": fact("area_m2", room.area_m2, src, measured),
            "min_width_m": fact("min_width_m", room.min_width_m, src, measured),
            "has_window": fact("has_window", room.has_window, src, measured),
        }.items() if v is not None}
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
        attrs = {k: v for k, v in {
            "width_m": fact("width_m", el.attrs.get("width_m"), src, trusted),
            "tag": fact("tag", el.tag, src, t1 or el.confirmed),
        }.items() if v is not None}
        nodes.append(Node(id=el.id, kind=el.cls, label=el.tag, attrs=attrs))
    nodes.append(Node(id="building", kind="building", role="whole"))
    boundary = {e.b for e in model.edges if e.b in BOUNDARY} | {e.a for e in model.edges if e.a in BOUNDARY}
    nodes += [Node(id=b, kind=BOUNDARY[b], role="boundary") for b in sorted(boundary)]

    confirmed = {e.id for e in model.elements if e.confirmed}
    edges = []
    for i, e in enumerate(model.edges):
        attrs = {}
        if e.width_m is not None:
            used.add("width_m")
            attrs["width_m"] = Fact(value=e.width_m, source=f"{model.sheet.id}:{e.via or i}", trusted=measured)
        edges.append(Edge(id=f"e{i}", a=e.a, b=e.b, kind=e.kind, via=e.via, attrs=attrs,
                          trusted=t1 or (e.via in confirmed)))
    known = {n.kind for n in nodes if n.role == "member"} | set(LOOKED_FOR)
    inventory = {k: Inventory(complete=complete, trusted=t1 or complete) for k in known}
    # the stair finder reaches about half of drawn stairs (see docs/progress/M7): its list is never claimed complete,
    # so a rule over stairs reads UNRESOLVED instead of passing because none were found
    inventory["stair"] = Inventory(complete=False, trusted=False)
    return FactGraph(
        provenance=Provenance(document=model.sheet.source_file, sheet=model.sheet.id, tier=model.tier,
                              scale=model.sheet.scale.method, producer="reviewpulse.building_model"),
        bindings={k: v for k, v in BINDINGS.items() if k in used}, nodes=nodes, edges=edges,
        inventory=inventory, graph_complete=complete,
        value_labels={"room_type": room_labels({n.attrs["room_type"].value for n in nodes if "room_type" in n.attrs})})
