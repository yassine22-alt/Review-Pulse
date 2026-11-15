"""A non-recursive form of the program: a flat table of nodes that refer to each other by id.

Constrained decoding engines handle recursive schemas badly (JSONSchemaBench), and a 7B model has to
nest correctly while it also reads the sentence. A node table is built bottom-up (children first), has
no recursion in its schema, and compiles deterministically to the interpreter's `Program`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..interpreter.schema import Model, Scalar, Unit

Op = Literal[
    "literal", "fact", "all", "any", "not",
    "eq", "ne", "lt", "le", "gt", "ge", "add", "sub", "mul", "div",
    "forall", "exists", "count", "sum", "min", "max",
]
BINARY = {"eq", "ne", "lt", "le", "gt", "ge", "add", "sub", "mul", "div"}
LOGIC = {"all", "any", "not"}
SETS = {"forall", "exists", "count", "sum", "min", "max"}


class FlatNode(Model):
    id: str = Field(min_length=1)
    op: Op
    value: Scalar | None = None
    unit: Unit = "1"
    entity: str | None = None
    name: str | None = None
    args: list[str] = Field(default_factory=list)
    left: str | None = None
    right: str | None = None
    collection: str | None = None
    variable: str | None = None
    where: str | None = None
    body: str | None = None


class FlatSpan(Model):
    clause: str
    quote: str = Field(min_length=1)


class FlatProgram(Model):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    nodes: list[FlatNode] = Field(min_length=1)
    applicability: str | None = None
    exemption: str | None = None
    requirement: str
    sources: list[FlatSpan] = Field(min_length=1)
    unresolved: list[str] = Field(default_factory=list)


def compile_flat(flat: FlatProgram, document: str) -> dict:
    """Resolve node ids into the interpreter's expression tree; reject dangling ids and cycles."""
    table = {node.id: node for node in flat.nodes}
    if len(table) != len(flat.nodes):
        raise ValueError("duplicate node ids")

    def build(ref: str | None, trail: tuple[str, ...]) -> dict:
        if ref not in table:
            raise ValueError(f"unknown node id {ref!r}")
        if ref in trail:
            raise ValueError(f"cycle through node {ref!r}")
        node, trail = table[ref], trail + (ref,)

        def sub(child):
            return build(child, trail)

        if node.op == "literal":
            if node.value is None:
                raise ValueError(f"literal {ref} has no value")
            return {"node": "literal", "value": node.value, "unit": node.unit}
        if node.op == "fact":
            if not node.entity or not node.name:
                raise ValueError(f"fact {ref} needs entity and name")
            return {"node": "fact", "entity": node.entity, "name": node.name}
        if node.op in LOGIC:
            return {"node": node.op, "args": [sub(a) for a in node.args]}
        if node.op in BINARY:
            return {"node": node.op, "left": sub(node.left), "right": sub(node.right)}
        out = {"node": node.op, "collection": node.collection, "variable": node.variable}
        if node.where:
            out["where"] = sub(node.where)
        if node.body:
            out["body"] = sub(node.body)
        return out

    true = {"node": "literal", "value": True, "unit": "1"}
    program = {
        "id": flat.id,
        "title": flat.title,
        "document": document,
        "requirement": build(flat.requirement, ()),
        "sources": [{"clause": s.clause, "start": 0, "end": 1, "quote": s.quote} for s in flat.sources],
        "unresolved": flat.unresolved,
    }
    if flat.applicability:
        program["applicability"] = build(flat.applicability, ())
    else:
        program["applicability"] = true
    if flat.exemption:
        program["exemption"] = build(flat.exemption, ())
    return program
