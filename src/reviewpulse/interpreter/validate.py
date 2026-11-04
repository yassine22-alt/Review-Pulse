"""Check variable scope and dimensional consistency before execution or approval."""

from __future__ import annotations

from .schema import (
    BinaryExpr,
    Binding,
    Expr,
    FactExpr,
    LiteralExpr,
    LogicExpr,
    PathExpr,
    Program,
    SetExpr,
    scalar_kind,
    walk,
)


def expression_type(
    expr: Expr, bindings: dict[str, Binding], variables: frozenset[str] = frozenset()
) -> tuple[str, str]:
    if isinstance(expr, LiteralExpr):
        return scalar_kind(expr.value), expr.unit
    if isinstance(expr, FactExpr):
        if expr.entity.startswith("$") and expr.entity not in variables:
            raise ValueError(f"unbound variable {expr.entity}")
        if expr.name == "id":
            return "string", "1"
        if expr.name not in bindings:
            raise ValueError(f"unsupported fact {expr.name}")
        spec = bindings[expr.name]
        return spec.kind, spec.unit
    if isinstance(expr, LogicExpr):
        if any(expression_type(arg, bindings, variables) != ("boolean", "1") for arg in expr.args):
            raise ValueError("logical operators require booleans")
        return "boolean", "1"
    if isinstance(expr, PathExpr):
        for endpoint in (expr.origin, expr.destination):
            if endpoint.startswith("$") and endpoint not in variables:
                raise ValueError(f"unbound path endpoint {endpoint}")
        if variables & {"$node", "$edge"}:
            raise ValueError("$node and $edge are reserved for path filters")
        for predicate, variable in ((expr.node_filter, "$node"), (expr.edge_filter, "$edge")):
            if predicate and expression_type(predicate, bindings, variables | {variable}) != ("boolean", "1"):
                raise ValueError("path filters require booleans")
        return "boolean", "1"
    if isinstance(expr, SetExpr):
        if expr.variable in variables:
            raise ValueError(f"variable shadowing is not allowed: {expr.variable}")
        scope = variables | {expr.variable}
        if expr.where and expression_type(expr.where, bindings, scope) != ("boolean", "1"):
            raise ValueError("collection filter requires a boolean")
        if expr.node == "count":
            return "number", "count"
        body = expression_type(expr.body, bindings, scope)
        expected = "boolean" if expr.node in ("forall", "exists") else "number"
        if body[0] != expected:
            raise ValueError(f"{expr.node} requires a {expected} body")
        return body
    left = expression_type(expr.left, bindings, variables)
    right = expression_type(expr.right, bindings, variables)
    if expr.node in ("eq", "ne", "lt", "le", "gt", "ge", "add", "sub"):
        if left != right:
            raise ValueError(f"{expr.node} has incompatible types/units: {left} and {right}")
        if expr.node not in ("eq", "ne") and left[0] != "number":
            raise ValueError(f"{expr.node} requires numbers")
        return left if expr.node in ("add", "sub") else ("boolean", "1")
    if not isinstance(expr, BinaryExpr) or left[0] != "number" or right[0] != "number":
        raise ValueError("arithmetic requires numbers")
    if expr.node == "mul":
        if "1" in (left[1], right[1]):
            return "number", right[1] if left[1] == "1" else left[1]
        if left[1] == right[1] == "m":
            return "number", "m2"
    elif left[1] == right[1]:
        return "number", "1"
    elif right[1] == "1":
        return left
    elif left[1] == "m2" and right[1] == "m":
        return "number", "m"
    raise ValueError(f"unsupported dimensional arithmetic: {left[1]} {expr.node} {right[1]}")


def validate_program(
    program: Program, bindings: dict[str, Binding], collections: list[str] | None = None
) -> None:
    for name in ("applicability", "exemption", "requirement"):
        expr = getattr(program, name)
        nodes = list(walk(expr))
        if len(nodes) > 1000:
            raise ValueError("expression exceeds 1000 nodes")
        if collections is not None:
            for node in nodes:
                if isinstance(node, SetExpr) and node.collection not in collections:
                    raise ValueError(f"unsupported collection {node.collection}")
        if expression_type(expr, bindings) != ("boolean", "1"):
            raise ValueError(f"{name} must produce a boolean")
