"""Readers for the fact graph: the judge's inputs, the routing graph, and the extractor's catalogue."""

from __future__ import annotations

import networkx as nx

from ..interpreter.schema import Collection, Inputs
from .schema import FactGraph, collection_name


def to_inputs(fg: FactGraph) -> Inputs:
    """Facts by node id, collections by node kind: exactly what `interpreter.runtime` evaluates."""
    facts = {n.id: dict(n.attrs) for n in fg.nodes if n.attrs}
    collections = {}
    for kind in sorted(set(fg.kinds()) | set(fg.inventory)):
        members = [n.id for n in fg.nodes if n.kind == kind and n.role == "member"]
        inv = fg.inventory.get(kind)
        collections[collection_name(kind)] = Collection(
            items=members, complete=bool(inv and inv.complete), trusted=bool(inv and inv.trusted))
    return Inputs(bindings=fg.bindings, facts=facts, collections=collections, graph_complete=fg.graph_complete)


def to_graph(fg: FactGraph) -> nx.MultiGraph:
    """The room graph used by path_exists: nodes carry kind and role, edges carry kind, via, width and trust."""
    g = nx.MultiGraph()
    for node in fg.nodes:
        data = {"kind": node.kind, "role": node.role, "label": node.label}
        g.add_node(node.id, **data)
    for edge in fg.edges:
        width = edge.attrs.get("width_m")
        g.add_edge(edge.a, edge.b, kind=edge.kind, via=edge.via, trusted=edge.trusted,
                   width_m=width.value if width else None)
    return g


def to_catalogue(fg: FactGraph) -> dict:
    """What the rule drafter is told it may refer to: collections, their facts, building-level facts, categories."""
    per_kind: dict[str, set[str]] = {}
    building: set[str] = set()
    values: dict[str, set] = {}
    for node in fg.nodes:
        if node.role == "whole":
            building |= set(node.attrs)
        elif node.role == "member":
            per_kind.setdefault(node.kind, set()).update(node.attrs)
        for name, fact in node.attrs.items():
            if fg.bindings[name].kind == "string" and fact.value is not None:
                values.setdefault(name, set()).add(fact.value)
    return {
        "collections": {collection_name(k): {"facts": sorted(v)} for k, v in sorted(per_kind.items())},
        "building": sorted(building),
        "whole": fg.whole().id if fg.whole() else None,
        "bindings": {n: b.model_dump() for n, b in fg.bindings.items()},
        # a text fact is a category (something documents name in words) when the producer gave words for its values;
        # identifiers such as schedule tags are text too, but a rule must never be restricted to one of them
        "kinds": {n: sorted(v) for n, v in values.items() if n in fg.value_labels},
        "kind_labels": {n: {k: v for k, v in labels.items() if k in values.get(n, ())}
                        for n, labels in fg.value_labels.items()},
    }
