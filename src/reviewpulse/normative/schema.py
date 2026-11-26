"""The span grounded obligation tree.

A clause is cut into atomic obligations. Each obligation is a tree with five parts, every node tied to the words of the clause by a
character span (`text[start:end]` is the quote):

    scope          "for every <collection> where <cond>"            (optional)
    applicability  when the obligation applies at all               (a condition tree)
    requirement    what must hold (alternatives are an `any` node)  (a condition tree)
    exceptions     defeaters: when they hold the obligation is lifted, each one with its cue words
    facts          the facts every test reads, declared once for the whole clause

Applicability and exceptions are kept apart from the requirement, so that a plan that is out of scope is "not applicable" and a plan
that is excepted is "exempt", never "violated". The tree compiles to the existing interpreter `Program` (compile.py).
"""

from __future__ import annotations

from typing import Literal

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

from ..interpreter.schema import Unit

Scalar = StrictBool | StrictInt | StrictFloat | StrictStr


class M(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SpanRef(M):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("a span must be nonempty")
        return self


class FactSpec(M):
    """A fact a test may read. `owner` says whether it hangs on the whole (the building) or on a member of the scope."""
    name: str = Field(min_length=1)
    kind: Literal["boolean", "number", "string"]
    unit: Unit = "1"
    owner: Literal["building", "member"] = "building"
    collection: str | None = None            # for a member fact: the collection it belongs to
    label: dict[str, str] = Field(default_factory=dict)   # language -> words ("en": "floor area")
    values: list[str] = Field(default_factory=list)       # the declared values of a string fact

    @model_validator(mode="after")
    def coherent(self):
        if self.kind != "number" and self.unit != "1":
            raise ValueError("only numbers have units")
        if self.owner == "member" and not self.collection:
            raise ValueError("a member fact names its collection")
        return self

    def words(self, lang: str) -> str:
        return self.label.get(lang) or self.label.get("en") or self.name.replace("_", " ")


class Cond(M):
    """One node of a condition tree: a test of a fact against a value, or all / any / not over children."""
    kind: Literal["test", "all", "any", "not"]
    fact: str | None = None
    op: Literal["ge", "le", "gt", "lt", "eq", "ne"] | None = None
    value: Scalar | None = None
    unit: Unit = "1"                          # the unit the value is WRITTEN in (converted to the fact's unit on compile)
    args: list[Cond] = Field(default_factory=list)
    span: SpanRef | None = None

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "test":
            if not self.fact or self.op is None or self.value is None or self.args:
                raise ValueError("a test names a fact, an operator and a value, and has no children")
            if type(self.value) in (bool, str) and self.unit != "1":
                raise ValueError("text and booleans have no unit")
        else:
            if self.fact or self.op or self.value is not None:
                raise ValueError("a combinator has children only")
            if not self.args or (self.kind == "not" and len(self.args) != 1):
                raise ValueError("all / any need children; not needs exactly one")
        return self


Cond.model_rebuild()


class Scope(M):
    quantifier: Literal["forall", "exists"] = "forall"   # every member must satisfy the rest, or at least one member must
    collection: str = Field(min_length=1)
    variable: str = Field(pattern=r"^\$[A-Za-z][A-Za-z0-9_]*$")
    where: Cond | None = None
    span: SpanRef | None = None


class Exc(M):
    """A defeater. `cue` is the word that introduced it ("unless", "sauf si"); it is lifted when `when` holds."""
    when: Cond
    cue: str = ""
    span: SpanRef | None = None


class Obligation(M):
    id: str = Field(min_length=1)
    modality: Literal["obligation", "prohibition"] = "obligation"   # a prohibition forbids the requirement
    scope: Scope | None = None
    applicability: Cond | None = None
    requirement: Cond
    exceptions: list[Exc] = Field(default_factory=list)
    span: SpanRef | None = None
    unresolved: list[str] = Field(default_factory=list)     # parts the drafter could not decide: the rule then never says "satisfied"


class NormTree(M):
    clause_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    language: str = "en"
    document: str = "unknown"
    facts: list[FactSpec] = Field(default_factory=list)
    obligations: list[Obligation] = Field(min_length=1)

    @model_validator(mode="after")
    def grounded_and_declared(self):
        names = [f.name for f in self.facts]
        if len(set(names)) != len(names):
            raise ValueError("fact names must be distinct")
        for ref, where in self.spans():
            if ref.end > len(self.text):
                raise ValueError(f"span outside the clause at {where}")
        for ob in self.obligations:
            for c in cond_nodes(ob):
                if c.kind == "test" and c.fact not in names:
                    raise ValueError(f"undeclared fact {c.fact} in {ob.id}")
        return self

    def fact(self, name: str) -> FactSpec:
        return next(f for f in self.facts if f.name == name)

    def quote(self, ref: SpanRef | None) -> str:
        return "" if ref is None else self.text[ref.start:ref.end]

    def spans(self):
        for ob in self.obligations:
            if ob.span:
                yield ob.span, f"{ob.id}"
            if ob.scope and ob.scope.span:
                yield ob.scope.span, f"{ob.id}.scope"
            for e in ob.exceptions:
                if e.span:
                    yield e.span, f"{ob.id}.exception"
            for c in cond_nodes(ob):
                if c.span:
                    yield c.span, f"{ob.id}.cond"

    def ungrounded(self) -> list[str]:
        """Paths of nodes that carry no span (a tree drafted from a sentence should have none)."""
        out = []
        for ob in self.obligations:
            if ob.span is None:
                out.append(f"{ob.id}")
            for path, c in cond_paths(ob):
                if c.span is None:
                    out.append(f"{ob.id}.{path}")
            for i, e in enumerate(ob.exceptions):
                if e.span is None:
                    out.append(f"{ob.id}.exceptions[{i}]")
        return out


def walk_cond(c: Cond | None):
    if c is None:
        return
    yield c
    for a in c.args:
        yield from walk_cond(a)


def cond_nodes(ob: Obligation):
    for root in (ob.scope.where if ob.scope else None, ob.applicability, ob.requirement, *[e.when for e in ob.exceptions]):
        yield from walk_cond(root)


def cond_paths(ob: Obligation):
    """(path, node) for every condition node of an obligation. Paths read like 'requirement.args[1]'."""
    def rec(prefix: str, c: Cond | None):
        if c is None:
            return
        yield prefix, c
        for i, a in enumerate(c.args):
            yield from rec(f"{prefix}.args[{i}]", a)

    if ob.scope:
        yield from rec("scope.where", ob.scope.where)
    yield from rec("applicability", ob.applicability)
    yield from rec("requirement", ob.requirement)
    for i, e in enumerate(ob.exceptions):
        yield from rec(f"exceptions[{i}].when", e.when)


def leaf(fact: str, op: str, value, unit: str = "1", span: SpanRef | None = None) -> Cond:
    return Cond(kind="test", fact=fact, op=op, value=value, unit=unit, span=span)


def all_of(*args: Cond, span: SpanRef | None = None) -> Cond:
    return Cond(kind="all", args=list(args), span=span)


def any_of(*args: Cond, span: SpanRef | None = None) -> Cond:
    return Cond(kind="any", args=list(args), span=span)


def not_(arg: Cond, span: SpanRef | None = None) -> Cond:
    return Cond(kind="not", args=[arg], span=span)


def sp(text: str, quote: str, nth: int = 0) -> SpanRef:
    """The span of the nth occurrence of `quote` in `text` (hand built trees: the quote is what a person marked)."""
    pos = -1
    for _ in range(nth + 1):
        pos = text.find(quote, pos + 1)
        if pos < 0:
            raise ValueError(f"quote not in the text: {quote!r}")
    return SpanRef(start=pos, end=pos + len(quote))
