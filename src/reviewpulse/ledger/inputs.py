"""From the ledger back to the interpreter: requests read from a rule, resolutions turned into `Inputs`.

The rules and the evaluator do not change. A resolution becomes the same `Fact` they already read (value, source, trusted,
conflicting), so a rule runs on what the ledger decided, and a fact that is conflicting or unverified stays unusable as before.
"""

from __future__ import annotations

from ..factgraph.convert import to_inputs as graph_inputs
from ..factgraph.schema import FactGraph
from ..interpreter.schema import FactExpr, Inputs, PathExpr, Program, SetExpr
from .adapters import Attestations, binding_request, fact_graph_producers
from .fuse import Ledger, Resolution
from .request import FactRequest


def _scan(expr, scope: dict[str, str], out: list[tuple[str, str, str | None]]) -> None:
    """(entity or collection, fact, kind-of-entity) for every fact the expression reads; a bound variable maps to its collection."""
    if isinstance(expr, FactExpr):
        if expr.name != "id":
            var = expr.entity
            out.append((var, expr.name, scope.get(var)))
        return
    if isinstance(expr, SetExpr):
        inner = {**scope, expr.variable: expr.collection}
        for child in (expr.where, expr.body):
            if child is not None:
                _scan(child, inner, out)
        return
    if isinstance(expr, PathExpr):
        inner = {**scope, "$node": "nodes"}
        for child in (expr.node_filter, expr.edge_filter):
            if child is not None:
                _scan(child, inner, out)
        return
    for child in _children(expr):
        _scan(child, scope, out)


def _children(expr):
    if hasattr(expr, "args"):
        return list(expr.args)
    return [c for c in (getattr(expr, "left", None), getattr(expr, "right", None)) if c is not None]


def requests_for_program(program: Program, base: Inputs) -> list[FactRequest]:
    """The typed questions a rule asks: one per (entity or kind of entity, fact), with the clause's own words attached."""
    found: list[tuple[str, str, str | None]] = []
    for part in (program.applicability, program.exemption, program.requirement):
        _scan(part, {}, found)
    quote = " ".join(s.quote for s in program.sources)
    clause = program.sources[0].clause if program.sources else ""
    requests, seen = [], set()
    for entity, fact, collection in found:
        if (entity, fact) in seen or fact not in base.bindings:
            continue
        seen.add((entity, fact))
        requests.append(binding_request(None if collection else entity, fact, base.bindings[fact], entity_kind=collection,
                                        words=quote, clause=clause))
    return requests


def inputs_from_resolutions(resolutions: list[Resolution], base: Inputs) -> Inputs:
    """`base` supplies bindings, collections and graph completeness (what the ledger does not decide); facts come from the ledger."""
    facts: dict[str, dict] = {}
    for res in resolutions:
        fact = res.fact()
        if fact is not None:
            facts.setdefault(res.entity, {})[res.request.fact] = fact
    return Inputs(bindings=base.bindings, facts=facts, collections=base.collections, graph_complete=base.graph_complete)


def ledger_inputs(fg: FactGraph, attestations: Attestations | None = None, *, extra=()) -> tuple[Inputs, list[Resolution]]:
    """Every fact of a fact graph resolved through the ledger. With one family answering each fact, the result equals
    `factgraph.convert.to_inputs(fg)`; more producers (`extra`) and attestations add to it."""
    base = graph_inputs(fg)
    ledger = Ledger([*fact_graph_producers(fg), *([attestations] if attestations else []), *extra])
    resolutions: list[Resolution] = []
    for node in fg.nodes:
        names = set(node.attrs) | {e.fact for e in (attestations.entries if attestations else []) if e.entity == node.id}
        for name in names:
            if name in base.bindings:
                resolutions.append(ledger.resolve(binding_request(node.id, name, base.bindings[name], entity_kind=node.kind)))
    return inputs_from_resolutions(resolutions, base), resolutions


def inputs_for_program(program: Program, fg: FactGraph, ledger: Ledger) -> tuple[Inputs, list[Resolution]]:
    """Demand driven: ask only what the rule reads, of every entity it can read it for, and build the inputs from the answers."""
    base = graph_inputs(fg)
    resolutions: list[Resolution] = []
    for request in requests_for_program(program, base):
        if request.entity is None and request.entity_kind in base.collections:
            for entity in base.collections[request.entity_kind].items:
                resolutions.append(ledger.resolve(request.model_copy(update={"entity": entity})))
        elif request.entity is not None:
            resolutions.append(ledger.resolve(request))
        else:      # a variable over graph nodes (a route filter): every node a producer holds the fact for
            resolutions += ledger.resolve_all(request.model_copy(update={"entity_kind": None}))
    return inputs_from_resolutions(resolutions, base), resolutions
