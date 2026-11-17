"""Bind the existing BuildingModel without re-running or changing perception."""

from __future__ import annotations

from ..engine.context import build_graph
from ..schema import BuildingModel
from .schema import Binding, Collection, Fact, Inputs


def building_inputs(model: BuildingModel, *, complete: bool = False) -> Inputs:
    bindings = {
        "room_type": Binding(kind="string", description="Room classification from its label"),
        "area_m2": Binding(kind="number", unit="m2", description="Measured net room floor area"),
        "min_width_m": Binding(kind="number", unit="m", description="Measured minimum room width"),
        "width_m": Binding(kind="number", unit="m", description="Extracted opening clear width"),
    }
    facts = {}
    scale_known = model.sheet.scale.method in ("dxf_units", "dimension_consensus", "user", "scale_bar")
    for room in model.rooms:
        measured = model.tier == "T1" and scale_known
        label_known = model.tier == "T1" and room.prov.evidence.get("label_source") not in ("llm", "vlm")
        source = f"{model.sheet.id}:{room.id}"
        facts[room.id] = {
            "room_type": Fact(value=room.type, source=source, trusted=label_known),
            "area_m2": Fact(value=room.area_m2, source=source, trusted=measured),
            "min_width_m": Fact(value=room.min_width_m, source=source, trusted=measured),
        }
    for element in model.elements:
        facts[element.id] = {
            "width_m": Fact(
                value=element.attrs.get("width_m"),
                source=f"{model.sheet.id}:{element.id}",
                trusted=scale_known and (model.tier == "T1" or element.confirmed),
            )
        }
    membership_known = model.tier == "T1" or complete
    collections = {
        "rooms": Collection(
            items=[room.id for room in model.rooms], complete=complete, trusted=membership_known
        )
    }
    for kind in ("door", "window", "opening"):
        collections[f"{kind}s"] = Collection(
            items=[e.id for e in model.elements if e.cls == kind], complete=complete, trusted=membership_known
        )
    return Inputs(bindings=bindings, facts=facts, collections=collections, graph_complete=complete)


def building_graph(model: BuildingModel):
    graph = build_graph(model)
    for _node, data in graph.nodes(data=True):     # the evaluator knows boundaries by role, whatever the domain
        if data.get("kind") in ("exit", "exterior"):
            data["role"] = "boundary"
    confirmed = {element.id for element in model.elements if element.confirmed}
    for _a, _b, data in graph.edges(data=True):
        data["trusted"] = model.tier == "T1" or data.get("via") in confirmed
    return graph
