"""A finite expression language. No generated code is evaluated or imported."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)


def _valid_unit(text: str) -> str:
    """Any unit the dimensional-analysis table can parse (m, kPa, L/min, kg/m3 ...); see units.yaml."""
    from .units import UnitError, parse_unit

    try:
        parse_unit(text)
    except UnitError as exc:
        raise ValueError(str(exc)) from exc
    return text


Unit = Annotated[str, AfterValidator(_valid_unit)]
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
    via_edges: list[str] = Field(default_factory=lambda: ["door", "opening"])
    node_filter: Expr | None = None
    edge_filter: Expr | None = None


class LinkExpr(Model):
    """An edge of one of `via_edges` kinds directly between two nodes (nothing in between); empty: any kind."""
    node: Literal["linked"]
    a: str
    b: str
    via_edges: list[str] = Field(default_factory=list)


Expr = Annotated[
    LiteralExpr | FactExpr | LogicExpr | BinaryExpr | SetExpr | PathExpr | LinkExpr, Field(discriminator="node")
]
for _cls in (LogicExpr, BinaryExpr, SetExpr, PathExpr, LinkExpr):
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


class FactType(Model):
    kind: Literal["boolean", "number", "string"]
    unit: Unit = "1"

    @model_validator(mode="after")
    def numeric_units(self):
        if self.kind != "number" and self.unit != "1":
            raise ValueError("only numbers have units")
        return self


class DeclarationDescription(FactType):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    entity: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class FactDeclaration(DeclarationDescription):
    source: Span
    status: Literal["declared"] = "declared"


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
    # Parts of the sentence the plan cannot show (a riser height, a handrail). The rule covers the rest: a violation of the covered
    # part is a violation whatever the uncovered part says, but the rule can never report "satisfied" while a part is unchecked.
    not_checked: list[str] = Field(default_factory=list)
    fact_declarations: list[FactDeclaration] = Field(default_factory=list)


class Binding(FactType):
    description: str = ""
    declaration: FactDeclaration | None = None

    @model_validator(mode="after")
    def declaration_type(self):
        from .units import same_unit

        if self.declaration and (self.kind != self.declaration.kind or
                                 not same_unit(self.unit, self.declaration.unit)):
            raise ValueError("binding and fact declaration have incompatible types or units")
        return self


EvidenceOrigin = Literal["extracted", "computed", "schedule", "reviewer-attested"]


class Fact(Model):
    value: Scalar | None = None
    source: str = Field(min_length=1)
    trusted: bool = False
    conflicting: bool = False
    origin: EvidenceOrigin | None = None
    reviewer: str | None = None

    @model_validator(mode="after")
    def named_attestation(self):
        if self.origin == "reviewer-attested" and (not (self.reviewer or "").strip() or not self.source.strip()):
            raise ValueError("an attestation requires a named reviewer and source citation")
        return self


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
    evidence_locations: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def typed_facts(self):
        for name, binding in self.bindings.items():
            if binding.declaration and name != binding.declaration.name:
                raise ValueError("declaration name does not match binding")
        for entity, facts in self.facts.items():
            for name, fact in facts.items():
                if name == "id" or name not in self.bindings:
                    raise ValueError(f"undeclared or reserved fact: {entity}.{name}")
                value = fact.value
                declaration = self.bindings[name].declaration
                if declaration:
                    scope = self.collections.get(declaration.entity)
                    if entity not in (scope.items if scope else [declaration.entity]):
                        raise ValueError(f"wrong entity for declared fact: {entity}.{name}")
                    if fact.origin not in (None, "reviewer-attested") or (
                        value is not None and fact.origin != "reviewer-attested"
                    ) or (value is None and fact.trusted):
                        raise ValueError("declared facts require reviewer evidence, never extracted or computed values")
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
