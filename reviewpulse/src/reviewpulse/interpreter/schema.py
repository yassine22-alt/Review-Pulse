"""A finite expression language. No generated code is evaluated or imported."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

Unit = Literal["1", "m", "m2", "count"]
Scalar = StrictBool | StrictInt | StrictFloat | StrictStr


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class LiteralExpr(Model):
    node: Literal["literal"]
    value: Scalar
    unit: Unit = "1"

    @model_validator(mode="after")
    def valid_unit(self):
        if type(self.value) in (bool, str) and self.unit != "1":
            raise ValueError("text and booleans cannot have physical units")
        return self


class FactExpr(Model):
    node: Literal["fact"]
    entity: str = Field(min_length=1, description="An entity id or a bound variable, e.g. $room")
    name: str = Field(min_length=1)


class LogicExpr(Model):
    node: Literal["all", "any", "not"]
    args: list[Expr] = Field(min_length=1)

    @model_validator(mode="after")
    def arity(self):
        if self.node == "not" and len(self.args) != 1:
            raise ValueError("not requires exactly one argument")
        return self


class BinaryExpr(Model):
    node: Literal["eq", "ne", "lt", "le", "gt", "ge", "add", "sub", "mul", "div"]
    left: Expr
    right: Expr


class SetExpr(Model):
    node: Literal["forall", "exists", "count", "sum", "min", "max"]
    collection: str = Field(min_length=1)
    variable: str = Field(pattern=r"^\$[A-Za-z][A-Za-z0-9_]*$")
    where: Expr | None = None
    body: Expr | None = None

    @model_validator(mode="after")
    def body_required(self):
        if (self.node == "count") != (self.body is None):
            raise ValueError("count has no body; all other set operators require one")
        return self


class PathExpr(Model):
    node: Literal["path_exists"]
    origin: str
    destination: str = "EXIT"
    via_edges: list[Literal["door", "opening"]] = Field(default_factory=lambda: ["door", "opening"])
    node_filter: Expr | None = None
    edge_filter: Expr | None = None


Expr = Annotated[
    LiteralExpr | FactExpr | LogicExpr | BinaryExpr | SetExpr | PathExpr, Field(discriminator="node")
]
for _cls in (LogicExpr, BinaryExpr, SetExpr, PathExpr):
    _cls.model_rebuild()


class Span(Model):
    clause: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("source span must be nonempty")
        return self


class Program(Model):
    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    document: str = Field(min_length=1)
    status: Literal["draft", "approved"] = "draft"
    approved_by: str | None = None
    # An exemption defeats this obligation; alternative compliance belongs in requirement.any.
    applicability: Expr = Field(default_factory=lambda: LiteralExpr(node="literal", value=True))
    exemption: Expr = Field(default_factory=lambda: LiteralExpr(node="literal", value=False))
    requirement: Expr
    sources: list[Span] = Field(min_length=1)
    unresolved: list[str] = Field(default_factory=list)


class Binding(Model):
    kind: Literal["boolean", "number", "string"]
    unit: Unit = "1"
    description: str = ""

    @model_validator(mode="after")
    def numeric_units(self):
        if self.kind != "number" and self.unit != "1":
            raise ValueError("only numbers have units")
        return self


class Fact(Model):
    value: Scalar | None = None
    source: str = Field(min_length=1)
    trusted: bool = False
    conflicting: bool = False


class Collection(Model):
    items: list[str] = Field(default_factory=list)
    complete: bool = False
    trusted: bool = False

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.items)) != len(self.items):
            raise ValueError("collection ids must be distinct")
        return self


class Inputs(Model):
    bindings: dict[str, Binding]
    facts: dict[str, dict[str, Fact]] = Field(default_factory=dict)
    collections: dict[str, Collection] = Field(default_factory=dict)
    graph_complete: bool = False

    @model_validator(mode="after")
    def typed_facts(self):
        for entity, facts in self.facts.items():
            for name, fact in facts.items():
                if name == "id" or name not in self.bindings:
                    raise ValueError(f"undeclared or reserved fact: {entity}.{name}")
                value = fact.value
                if value is None:
                    continue
                kind = scalar_kind(value)
                if kind != self.bindings[name].kind:
                    raise ValueError(f"wrong type for {entity}.{name}: {kind}")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError(f"non-finite fact: {entity}.{name}")
        return self


def scalar_kind(value: Scalar) -> str:
    if type(value) is bool:
        return "boolean"
    return "string" if isinstance(value, str) else "number"


def walk(expr: Expr):
    """One traversal shared by source compilation and execution validation."""
    yield expr
    if isinstance(expr, LogicExpr):
        children = expr.args
    elif isinstance(expr, BinaryExpr):
        children = [expr.left, expr.right]
    elif isinstance(expr, SetExpr):
        children = [child for child in (expr.where, expr.body) if child is not None]
    elif isinstance(expr, PathExpr):
        children = [child for child in (expr.node_filter, expr.edge_filter) if child is not None]
    else:
        children = []
    for child in children:
        yield from walk(child)
