"""J1 - Engine context: the building model, its room graph and lookups."""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
from shapely.geometry import Polygon

from ..schema import BuildingModel, Element, Room

EXIT = "EXIT"
EXTERIOR = "EXTERIOR"


def build_graph(model: BuildingModel) -> nx.MultiGraph:
    g = nx.MultiGraph()
    for r in model.rooms:
        g.add_node(r.id, kind="room", type=r.type, label=r.label)
    g.add_node(EXIT, kind="exit")
    g.add_node(EXTERIOR, kind="exterior")
    for e in model.edges:
        g.add_edge(e.a, e.b, kind=e.kind, via=e.via, width_m=e.width_m)
    return g


@dataclass
class Context:
    model: BuildingModel
    graph: nx.MultiGraph
    tier: str
    confirmed_ids: set = field(default_factory=set)

    @classmethod
    def of(cls, model: BuildingModel, confirmed: set | None = None) -> Context:
        return cls(model, build_graph(model), model.tier, set(confirmed or ()))

    # ---- availability (rule.needs) -------------------------------------------------
    def has(self, need: str) -> bool:
        m = self.model
        if need == "scale":
            return m.sheet.scale.metres_per_unit is not None
        if need == "room_graph":
            return bool(m.rooms) and any(e.kind in ("door", "opening") for e in m.edges)
        if need == "rooms":
            return bool(m.rooms)
        if need == "schedule":
            return any(s.get("rows") for s in m.schedules if s.get("name") != "programme")
        if need == "programme":
            return any(s.get("rows") for s in m.schedules if s.get("name") == "programme")
        if need == "dimensions":
            return True          # the absence of dimensions is itself checked by P-2
        if need == "windows":
            return any(e.cls == "window" for e in m.elements)
        if need == "doors":
            return any(e.cls == "door" for e in m.elements)
        if need == "layout":
            return any(t.kind == "title_block" for t in m.sheet.texts)
        if need == "labels":
            return any(r.label for r in m.rooms)
        if need == "swing_polygons":
            return any(e.cls == "door" and e.attrs.get("swing_polygon") for e in m.elements)
        return False

    # ---- lookups -------------------------------------------------------------------
    @property
    def mpu(self) -> float | None:
        return self.model.sheet.scale.metres_per_unit

    def room(self, rid: str) -> Room | None:
        return next((r for r in self.model.rooms if r.id == rid), None)

    def element(self, eid: str) -> Element | None:
        return next((e for e in self.model.elements if e.id == eid), None)

    def is_confirmed(self, eid: str) -> bool:
        if eid in self.confirmed_ids:
            return True
        el = self.element(eid)
        return bool(el and el.confirmed)

    def rooms_for(self, applies_to: dict) -> list[Room]:
        types = applies_to.get("room_type")
        if isinstance(types, str):
            types = [types]
        out = []
        for r in self.model.rooms:
            if types and r.type not in types:
                continue
            if applies_to.get("is_corridor") is True and not r.is_corridor:
                continue
            out.append(r)
        return out

    def elements_for(self, applies_to: dict) -> list[Element]:
        cls = applies_to.get("element")
        return [e for e in self.model.elements if e.cls == cls]

    def centroid(self, node: str):
        r = self.room(node)
        if r is None:
            return None
        c = Polygon(r.polygon).centroid
        return (round(c.x, 4), round(c.y, 4))

    def name(self, node: str) -> str:
        r = self.room(node)
        if r is None:
            return node
        return r.label or f"room {r.id[-4:]} ({r.type or 'unlabelled'})"
