"""The facts layer as a graph: what the plan shows, with a source and a trust flag on every value.

One file per building. Nodes are things on the plan (rooms, doors, windows, stairs, the building itself, the
outside); edges are relations between them (door, opening, adjacency). Attributes hold measured facts. A value
that could not be measured is `null` or untrusted, and the judge treats it as unknown, never as a pass.

The format makes no assumption about the building type: node kinds, attribute names and their meaning are
declared in `bindings`, so any producer (plan reading, schedules, a human) can add its own.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ..interpreter.schema import Binding, Fact, Model, scalar_kind

FORMAT_VERSION = "1.0"


class Node(Model):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1, description="Any name the producer declares: room, stair, duct, span, sheet, ...")
    role: Literal["member", "whole", "boundary"] = Field(
        default="member",
        description="member: one of many things of its kind (listed in a collection); whole: the subject as a "
                    "whole (building, site, structure) carrying global facts; boundary: where things lead to "
                    "(outside, an exit) rather than a thing to measure")
    label: str | None = Field(default=None, description="Text as drawn, or a schedule tag")
    attrs: dict[str, Fact] = Field(default_factory=dict, description="Measured facts, each with source and trust")


class Edge(Model):
    id: str = Field(min_length=1)
    a: str
    b: str
    kind: str = Field(min_length=1, description="door, opening, window, adjacent, ...")
    via: str | None = Field(default=None, description="Node id of the door or opening that realises the relation")
    trusted: bool = Field(default=False, description="The relation itself is established, not just plausible")
    attrs: dict[str, Fact] = Field(default_factory=dict)


class Inventory(Model):
    complete: bool = Field(default=False, description="Every member of this kind is listed (reviewed or exact)")
    trusted: bool = Field(default=False, description="Membership is established, so a listed member really exists")


class Provenance(Model):
    document: str = ""
    sheet: str = ""
    tier: Literal["T1", "T2", "T3", "unknown"] = "unknown"
    scale: str = Field(default="unknown", description="Method that fixed the scale, or unknown")
    producer: str = ""


class FactGraph(Model):
    format_version: Literal["1.0"] = FORMAT_VERSION
    provenance: Provenance = Field(default_factory=Provenance)
    bindings: dict[str, Binding] = Field(description="Meaning, type and unit of every attribute name used")
    nodes: list[Node]
    edges: list[Edge] = Field(default_factory=list)
    inventory: dict[str, Inventory] = Field(
        default_factory=dict,
        description="Per node kind the producer looked for, including kinds with no member found (an empty "
                    "collection is different from a kind nobody looked for)")
    value_labels: dict[str, dict[str, list[str]]] = Field(
        default_factory=dict,
        description="Per string attribute, per value, the words documents use for it in any language "
                    "(room_type -> bedroom -> [chambre, bedroom, ...]); lets a sentence be matched to a value")
    graph_complete: bool = Field(default=False, description="Every relation is listed, so 'no route' can be proven")

    @model_validator(mode="after")
    def consistent(self):
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate node ids")
        known = set(ids)
        for edge in self.edges:
            for end in (edge.a, edge.b):
                if end not in known:
                    raise ValueError(f"edge {edge.id} refers to unknown node {end!r}")
            if edge.via is not None and edge.via not in known:
                raise ValueError(f"edge {edge.id} refers to unknown node {edge.via!r} as its door or opening")
        for holder in [*self.nodes, *self.edges]:
            for name, fact in holder.attrs.items():
                if name not in self.bindings:
                    raise ValueError(f"{holder.id}.{name} is not declared in bindings")
                if fact.value is not None and scalar_kind(fact.value) != self.bindings[name].kind:
                    raise ValueError(f"{holder.id}.{name} should be {self.bindings[name].kind}")
        return self

    def kinds(self) -> list[str]:
        return sorted({n.kind for n in self.nodes if n.role == "member"})

    def whole(self) -> Node | None:
        return next((n for n in self.nodes if n.role == "whole"), None)


def collection_name(kind: str) -> str:
    return kind if kind.endswith("s") else kind + "s"
