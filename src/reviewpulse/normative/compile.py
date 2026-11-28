"""A deterministic compiler from the obligation tree to the interpreter's `Program`.

The `Program` already has the two slots this needs (`applicability` and `exemption`), so nothing in interpreter/ is touched. What this
module adds is the rule for where each part of a tree goes:

  * A part that reads only building level facts goes to the program slot of its own name: applicability to `applicability`, the
    exceptions to `exemption` (an `any` of them), so the outcome is NOT_APPLICABLE or EXEMPT, never VIOLATED.
  * A part that reads a member fact (a fact of one room, one door) cannot be decided for the whole, so it moves INTO the scope filter:
    `forall coll v where (scope.where and applicability and not any(exceptions)): requirement` (or `exists`). A member that is out of scope or
    excepted is simply not checked. Recorded loss: for those parts the outcome is SATISFIED / VIOLATED over the remaining members,
    not NOT_APPLICABLE / EXEMPT.
  * A prohibition checks `not requirement`.
  * Numbers written in another unit are converted to the unit of the fact; an incompatible unit is a CompileError, not a guess.
"""

from __future__ import annotations

from ..interpreter import units
from ..interpreter.schema import Binding, Program
from .schema import Cond, NormTree, Obligation, walk_cond

BUILDING = "building"


class CompileError(ValueError):
    pass


def bindings_of(tree: NormTree) -> dict[str, Binding]:
    return {f.name: Binding(kind=f.kind, unit=f.unit, description=f.words("en")) for f in tree.facts}


def _literal(value, unit: str = "1") -> dict:
    return {"node": "literal", "value": value, "unit": unit}


def _true() -> dict:
    return _literal(True)


def cond_to_expr(c: Cond, tree: NormTree, variable: str | None) -> dict:
    if c.kind == "test":
        spec = tree.fact(c.fact)
        if spec.owner == "member":
            if variable is None:
                raise CompileError(f"member fact {spec.name} read outside a scope")
            entity = variable
        else:
            entity = BUILDING
        left = {"node": "fact", "entity": entity, "name": spec.name}
        value = c.value
        if spec.kind == "number":
            if type(value) in (bool, str):
                raise CompileError(f"{spec.name} is a number, compared with {value!r}")
            if c.unit not in ("1", spec.unit):
                try:
                    if not units.compatible(c.unit, spec.unit):
                        raise CompileError(f"{c.value} {c.unit} cannot be compared with {spec.name} in {spec.unit}")
                    value = round(units.convert(float(value), c.unit, spec.unit), 9)
                except units.UnitError as exc:
                    raise CompileError(str(exc)) from exc
            right = _literal(value, spec.unit)
        elif spec.kind == "boolean":
            if type(value) is not bool or c.op not in ("eq", "ne"):
                raise CompileError(f"{spec.name} is a yes/no fact")
            right = _literal(value)
        else:
            if type(value) is not str or c.op not in ("eq", "ne"):
                raise CompileError(f"{spec.name} is a text fact")
            right = _literal(value)
        return {"node": c.op, "left": left, "right": right}
    return {"node": c.kind, "args": [cond_to_expr(a, tree, variable) for a in c.args]}


def _member(c: Cond, tree: NormTree) -> bool:
    return any(n.kind == "test" and tree.fact(n.fact).owner == "member" for n in walk_cond(c))


def _all(parts: list[dict]) -> dict:
    return parts[0] if len(parts) == 1 else {"node": "all", "args": parts}


def _any(parts: list[dict]) -> dict:
    return parts[0] if len(parts) == 1 else {"node": "any", "args": parts}


def _conjuncts(c: Cond | None) -> list[Cond]:
    if c is None:
        return []
    return list(c.args) if c.kind == "all" else [c]


def compile_obligation(tree: NormTree, ob: Obligation) -> Program:
    scope = ob.scope
    var = scope.variable if scope else None
    building_app, member_filter = [], []
    if scope and scope.where is not None:
        member_filter.append(cond_to_expr(scope.where, tree, var))
    for c in _conjuncts(ob.applicability):
        (member_filter if _member(c, tree) else building_app).append(cond_to_expr(c, tree, var))
    building_exc, member_exc = [], []
    for exc in ob.exceptions:
        for c in (exc.when.args if exc.when.kind == "any" else [exc.when]):
            (member_exc if _member(c, tree) else building_exc).append(cond_to_expr(c, tree, var))
    if member_exc:
        member_filter.append({"node": "not", "args": [_any(member_exc)]})
    body = cond_to_expr(ob.requirement, tree, var)
    if ob.modality == "prohibition":
        body = {"node": "not", "args": [body]}
    if scope:
        quant = {"node": scope.quantifier, "collection": scope.collection, "variable": scope.variable, "body": body}
        if member_filter:
            quant["where"] = _all(member_filter)
        requirement = quant
    else:
        if member_filter:
            raise CompileError("a member level condition needs a scope")
        requirement = body
    source = ob.span
    if source is None:
        source = next((s for s, _ in tree.spans()), None)
    start, end = (source.start, source.end) if source else (0, len(tree.text))
    data = {
        "id": f"{tree.clause_id}:{ob.id}", "title": f"{tree.clause_id} {ob.id}", "document": tree.document,
        "requirement": requirement,
        "sources": [{"clause": tree.clause_id, "start": start, "end": end, "quote": tree.text[start:end]}],
        "unresolved": list(ob.unresolved),
    }
    if building_app:
        data["applicability"] = _all(building_app)
    if building_exc:
        data["exemption"] = _any(building_exc)
    try:
        program = Program.model_validate(data)
    except ValueError as exc:
        raise CompileError(str(exc)) from exc
    from ..interpreter.validate import validate_program

    try:
        validate_program(program, bindings_of(tree))
    except ValueError as exc:
        raise CompileError(str(exc)) from exc
    return program


def compile_tree(tree: NormTree) -> list[Program]:
    return [compile_obligation(tree, ob) for ob in tree.obligations]
