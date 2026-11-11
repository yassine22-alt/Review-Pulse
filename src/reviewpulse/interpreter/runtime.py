"""Conservative partial evaluation with a serializable evidence tree."""

from __future__ import annotations

import math
import operator
from dataclasses import asdict, dataclass, field

import networkx as nx

from ..outcomes import EvidenceIssue, IssueCode, Outcome
from .schema import (
    BinaryExpr,
    Expr,
    FactExpr,
    Inputs,
    LinkExpr,
    LiteralExpr,
    LogicExpr,
    PathExpr,
    Program,
    Scalar,
    SetExpr,
)
from .validate import validate_program

OPERATIONS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "div": operator.truediv,
}


@dataclass
class Trace:
    node: str
    value: Scalar | None = None
    missing: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    children: list[Trace] = field(default_factory=list)

    @classmethod
    def combine(cls, node: str, value: Scalar | None, children: list[Trace], missing=()) -> Trace:
        return cls(
            node,
            value,
            sorted(set(missing) | {m for c in children for m in c.missing}),
            sorted({e for c in children for e in c.evidence}),
            children,
        )


def _logic(node: str, children: list[Trace]) -> Trace:
    values = [c.value for c in children]
    if node == "not":
        value = None if values[0] is None else not values[0]
    elif node == "all":
        value = False if False in values else None if None in values else True
    else:
        value = True if True in values else None if None in values else False
    return Trace.combine(node, value, children)


class Evaluator:
    def __init__(self, inputs: Inputs, graph: nx.MultiGraph | None = None, max_steps: int = 100_000):
        self.inputs = inputs
        self.graph = graph
        self.remaining = max_steps
        self.dependencies: set[str] = set()
        self.evidence_issues: dict[str, EvidenceIssue] = {}

    def evaluate(self, expr: Expr, variables: dict[str, str] | None = None) -> Trace:
        self.remaining -= 1
        if self.remaining < 0:
            raise ValueError("expression evaluation budget exceeded")
        variables = variables or {}
        if isinstance(expr, LiteralExpr):
            return Trace(expr.node, expr.value)
        if isinstance(expr, FactExpr):
            entity = variables.get(expr.entity, expr.entity)
            if expr.name == "id":
                return Trace(expr.node, entity)
            key = f"{entity}.{expr.name}"
            self.dependencies.add(key)
            fact = self.inputs.facts.get(entity, {}).get(expr.name)
            if fact is None:
                return Trace(expr.node, missing=[key])
            if fact.value is None or not fact.trusted or fact.conflicting:
                reason = (
                    "conflicting" if fact.conflicting else "unverified" if not fact.trusted else "missing"
                )
                return Trace(expr.node, missing=[f"{key} ({reason})"], evidence=[fact.source])
            return Trace(expr.node, fact.value, evidence=[fact.source])
        if isinstance(expr, LogicExpr):
            return _logic(expr.node, [self.evaluate(arg, variables) for arg in expr.args])
        if isinstance(expr, BinaryExpr):
            children = [self.evaluate(arg, variables) for arg in (expr.left, expr.right)]
            left, right = (child.value for child in children)
            if left is None or right is None:
                return Trace.combine(expr.node, None, children)
            if expr.node == "div" and right == 0:
                return Trace.combine(expr.node, None, children, ["division by zero"])
            try:
                value = OPERATIONS[expr.node](left, right)
            except OverflowError:
                return Trace.combine(expr.node, None, children, ["arithmetic overflow"])
            if isinstance(value, float) and not math.isfinite(value):
                return Trace.combine(expr.node, None, children, ["non-finite arithmetic result"])
            return Trace.combine(expr.node, value, children)
        if isinstance(expr, PathExpr):
            return self._path(expr, variables)
        if isinstance(expr, LinkExpr):
            return self._link(expr, variables)
        return self._set(expr, variables)

    def _path(self, expr: PathExpr, variables: dict[str, str]) -> Trace:
        self.dependencies.add("connections")
        if not self.inputs.graph_complete:
            self.evidence_issues["connections"] = EvidenceIssue(
                code=IssueCode.INCOMPLETE_INVENTORY, detail="connection inventory is incomplete")
        if self.graph is None:
            return Trace(expr.node, missing=["room graph"])
        origin = variables.get(expr.origin, expr.origin)
        target = variables.get(expr.destination, expr.destination)
        if origin not in self.graph or target not in self.graph:
            return Trace(expr.node, missing=["path endpoint not present in graph"])
        self.remaining -= len(self.graph) + self.graph.number_of_edges()
        if self.remaining < 0:
            raise ValueError("path evaluation budget exceeded")
        known, possible = nx.Graph(), nx.Graph()
        known.add_nodes_from([origin, target])
        possible.add_nodes_from([origin, target])
        children, node_truth = [], {}
        for node in self.graph:
            # a route filter ("not through a bathroom") limits the rooms passed through; the room the route starts
            # from and the place it ends are never excluded by it (the legacy engine behaves the same way)
            exempt = origin != target and node in (origin, target)
            result = (
                self.evaluate(expr.node_filter, {**variables, "$node": node})
                if (expr.node_filter and self.graph.nodes[node].get("role") != "boundary" and not exempt)
                else Trace("literal", True)
            )
            node_truth[node] = result.value
            children.append(result)
        for a, b, data in self.graph.edges(data=True):
            if data.get("kind") not in expr.via_edges:
                continue
            via = data.get("via")
            result = (
                self.evaluate(expr.edge_filter, {**variables, "$edge": via})
                if (expr.edge_filter and via)
                else Trace("literal", None if expr.edge_filter else True)
            )
            if result.value is not False and not data.get("trusted", False):
                result = Trace.combine(
                    "connection", None, [result], [f"unverified connection:{via or (a, b)}"]
                )
            children.append(result)
            truths = [node_truth[a], node_truth[b], result.value]
            if False not in truths:
                possible.add_edge(a, b)
                if None not in truths:
                    known.add_edge(a, b)
        if origin == target:
            value = node_truth[origin]
        elif nx.has_path(known, origin, target):
            value = True
        elif self.inputs.graph_complete and not nx.has_path(possible, origin, target):
            value = False
        else:
            value = None
        missing = [] if self.inputs.graph_complete else ["incomplete room graph"]
        return Trace.combine(expr.node, value, children, missing)

    def _link(self, expr: LinkExpr, variables: dict[str, str]) -> Trace:
        """True when a door or opening joins the two nodes directly; unknown when the connections may be incomplete."""
        self.dependencies.add("connections")
        if not self.inputs.graph_complete:
            self.evidence_issues["connections"] = EvidenceIssue(
                code=IssueCode.INCOMPLETE_INVENTORY, detail="connection inventory is incomplete")
        if self.graph is None:
            return Trace(expr.node, missing=["room graph"])
        a, b = variables.get(expr.a, expr.a), variables.get(expr.b, expr.b)
        if a not in self.graph or b not in self.graph:
            return Trace(expr.node, missing=["link endpoint not present in graph"])
        edges = [d for d in (self.graph.get_edge_data(a, b) or {}).values()
                 if not expr.via_edges or d.get("kind") in expr.via_edges]
        if any(d.get("trusted", False) for d in edges):
            return Trace(expr.node, True)
        if edges:
            return Trace(expr.node, missing=[f"unverified connection:{edges[0].get('via') or (a, b)}"])
        if self.inputs.graph_complete:
            return Trace(expr.node, False)
        return Trace(expr.node, missing=["incomplete room graph"])

    def _set(self, expr: SetExpr, variables: dict[str, str]) -> Trace:
        self.dependencies.add(f"inventory:{expr.collection}")
        collection = self.inputs.collections.get(expr.collection)
        if collection is None:
            return Trace(expr.node, missing=[f"collection:{expr.collection}"])
        self.remaining -= len(collection.items)
        if self.remaining < 0:
            raise ValueError("collection evaluation budget exceeded")
        children, selected = [], []
        uncertain = not collection.complete
        if not collection.complete:
            self.evidence_issues[expr.collection] = EvidenceIssue(
                code=IssueCode.INCOMPLETE_INVENTORY, detail=f"incomplete collection:{expr.collection}")
        for entity in collection.items:
            scope = {**variables, expr.variable: entity}
            condition = self.evaluate(expr.where, scope) if expr.where else Trace("literal", True)
            if not collection.trusted:
                condition = _logic(
                    "all", [condition, Trace("membership", missing=[f"unverified member:{entity}"])]
                )
            if condition.value is False:
                children.append(_logic("not", [condition]) if expr.node == "forall" else condition)
                continue
            if expr.node in ("forall", "exists"):
                body = self.evaluate(expr.body, scope)
                # Quantification over a filtered set: an unknown filter is not a selected member.
                branch = (
                    _logic("all", [condition, body])
                    if expr.node == "exists"
                    else _logic("any", [_logic("not", [condition]), body])
                )
                children.append(branch)
            else:
                children.append(condition)
                if condition.value is None:
                    uncertain = True
                    continue
                body = Trace("literal", 1) if expr.node == "count" else self.evaluate(expr.body, scope)
                children.append(body)
                if body.value is None:
                    uncertain = True
                else:
                    selected.append(body.value)
        missing = [] if collection.complete else [f"incomplete collection:{expr.collection}"]
        if expr.node in ("forall", "exists"):
            if not collection.complete:
                children.append(Trace("unknown_members", missing=missing))
            # Do not certify an obligation over an empty, possibly misbound scope.
            if expr.node == "forall" and not collection.items:
                return Trace.combine(expr.node, None, children, [f"empty scope:{expr.collection}"])
            result = _logic("all" if expr.node == "forall" else "any", children)
            result.node = expr.node
            return result
        if uncertain:
            return Trace.combine(expr.node, None, children, missing)
        if expr.node in ("min", "max") and not selected:
            return Trace.combine(expr.node, None, children, [f"empty aggregate:{expr.collection}"])
        fn = {"count": len, "sum": sum, "min": min, "max": max}[expr.node]
        value = fn(selected)
        if isinstance(value, float) and not math.isfinite(value):
            return Trace.combine(expr.node, None, children, ["non-finite aggregate result"])
        return Trace.combine(expr.node, value, children)


def run_program(
    program: Program, inputs: Inputs, *, include_drafts: bool = False, graph: nx.MultiGraph | None = None
) -> dict:
    """Detailed outcomes stay separate from the legacy four-verdict Finding contract."""
    validate_program(program, inputs.bindings)
    if program.status != "approved" and not include_drafts:
        raise ValueError("draft programs require explicit preview; approve before execution")
    if program.status == "approved" and not program.approved_by:
        raise ValueError("approved programs require a named reviewer")
    evaluator = Evaluator(inputs, graph)
    applicability = evaluator.evaluate(program.applicability)
    exemption = evaluator.evaluate(program.exemption)
    requirement = evaluator.evaluate(program.requirement)
    outcome: Outcome
    if program.unresolved:
        outcome = "UNRESOLVED"
    elif applicability.value is False:
        outcome = "NOT_APPLICABLE"
    elif exemption.value is True:
        outcome = "EXEMPT"
    elif applicability.value is None:
        outcome = "UNRESOLVED"
    elif requirement.value is True:
        outcome = "SATISFIED"
    elif requirement.value is None or exemption.value is None:
        outcome = "UNRESOLVED"
    else:
        outcome = "VIOLATED"
    root = Trace.combine("program", None, [applicability, exemption, requirement], program.unresolved)
    return {
        "rule_id": program.id,
        "outcome": outcome,
        "dependencies": sorted(evaluator.dependencies),
        "evidence_issues": [i.model_dump(mode="json") for i in evaluator.evidence_issues.values()],
        "preview": program.status == "draft",
        "document": program.document,
        "sources": [source.model_dump() for source in program.sources],
        "trace": asdict(root),
    }
