"""Relational facts derived from ANY fact graph: how members connect, and whether a route reaches each boundary.

Requirements often ask about connections rather than measurements: "every room has a door", "a room with a single door
has a window", "every space reaches an exit", "no pipe joins the two networks". These answers follow from the graph
itself, whatever it describes, so they are derived here from the fact graph's own nodes and edges, not from a building
model. A producer only declares which edge kinds a route may follow (`FactGraph.passable`); nothing here knows what a
room, a door or a pipe is.

For every member node:
  links_<kind>        number of edges of that kind touching it (one fact per edge kind present in the graph)
  links_passable      number of passable edges touching it (all edge kinds when the producer declared none)
  reaches_<boundary>  a route over passable edges reaches that boundary node (one fact per boundary, e.g. reaches_exit)
For the whole (if any):
  links_to_<boundary> number of passable edges touching that boundary

Trust follows the edges: a count is trusted when every edge it counts is trusted; a route that exists is trusted when a
route over trusted edges exists; "no route" is trusted only when the graph is declared complete. Anything else is reported
untrusted, so the judge reads it as unknown, never as a pass.

Measurements that need geometry (a travel distance in metres) are not derivable from the graph and stay with the producer.
"""

from __future__ import annotations

import re

import networkx as nx

from ..interpreter.schema import Binding, Fact
from .schema import FactGraph


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"


def derive_relations(fg: FactGraph) -> FactGraph:
    """A copy of `fg` with the relational facts added to its member nodes (and its whole, if any)."""
    fg = fg.model_copy(deep=True)
    kinds = sorted({e.kind for e in fg.edges})
    passable = set(fg.passable) if fg.passable is not None else set(kinds)
    boundaries = [n for n in fg.nodes if n.role == "boundary"
                  and (fg.route_targets is None or n.id in fg.route_targets)]
    trusted_graph, any_graph = nx.Graph(), nx.Graph()
    trusted_graph.add_nodes_from(n.id for n in fg.nodes)
    any_graph.add_nodes_from(n.id for n in fg.nodes)
    for e in fg.edges:
        if e.kind in passable:
            any_graph.add_edge(e.a, e.b)
            if e.trusted:
                trusted_graph.add_edge(e.a, e.b)
    bindings = dict(fg.bindings)
    by_id = {n.id: n for n in fg.nodes}
    member_kinds = {by_id[end].kind for e in fg.edges for end in (e.a, e.b)
                    if end in by_id and by_id[end].role == "member"}
    noun = next(iter(member_kinds)) if len(member_kinds) == 1 else "member"
    for kind in kinds:
        bindings[f"links_{_slug(kind)}"] = Binding(kind="number", unit="count",
                                                   description=f"Number of {kind} connections of the {noun}")
    bindings["links_passable"] = Binding(kind="number", unit="count",
                                         description=f"Number of connections of the {noun} that a route can follow")
    for b in boundaries:
        # described by what it reaches, not by how: the words of a description are what a rule is checked against
        bindings[f"reaches_{_slug(b.id)}"] = Binding(kind="boolean", description=f"The {noun} has a route to the {b.id.lower()}")
        bindings[f"links_to_{_slug(b.id)}"] = Binding(
            kind="number", unit="count", description=f"Number of direct connections to the {b.id.lower()}")
    incident: dict[str, list] = {}
    for e in fg.edges:
        for end in (e.a, e.b):
            incident.setdefault(end, []).append(e)
    for node in fg.nodes:
        if node.role != "member" or node.kind not in member_kinds:
            continue
        edges = incident.get(node.id, [])
        source = f"derived:{node.id}"
        for kind in kinds:
            mine = [e for e in edges if e.kind == kind]
            node.attrs[f"links_{_slug(kind)}"] = Fact(value=len(mine), source=source,
                                                     trusted=all(e.trusted for e in mine) or fg.graph_complete)
        mine = [e for e in edges if e.kind in passable]
        node.attrs["links_passable"] = Fact(value=len(mine), source=source,
                                            trusted=all(e.trusted for e in mine) or fg.graph_complete)
        for b in boundaries:
            if nx.has_path(trusted_graph, node.id, b.id):
                value, trusted = True, True
            elif nx.has_path(any_graph, node.id, b.id):
                value, trusted = True, False          # only through connections nobody confirmed
            else:
                value, trusted = False, fg.graph_complete
            node.attrs[f"reaches_{_slug(b.id)}"] = Fact(value=value, source=source, trusted=trusted)
    whole = fg.whole()
    if whole is not None:
        for b in boundaries:
            touching = [e for e in incident.get(b.id, []) if e.kind in passable]
            whole.attrs[f"links_to_{_slug(b.id)}"] = Fact(value=len(touching), source=f"derived:{b.id}",
                                                         trusted=all(e.trusted for e in touching) or fg.graph_complete)
    fg.bindings = bindings
    return fg
