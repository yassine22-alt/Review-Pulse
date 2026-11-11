"""Turn an approved rule's result into findings a reviewer can act on: which elements, what was measured, where on the plan.

`run_program` answers for the whole rule (SATISFIED, VIOLATED, UNRESOLVED ...). A reviewer needs more: which door, which
room, what value against what limit, and where to look. For a rule that says "every X ..." the members are evaluated one by
one; for any other shape (a total, a count, a route) the answer is one finding for the whole plan.

The outcome keeps its full three-valued meaning. A rule that could not be decided is never a pass: it becomes NOT_EVALUATED
with the facts that were missing. A rule that does not apply, or is exempt, produces no finding (the coverage report lists it).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..outcomes import Assessment, EvidenceIssue, IssueCode
from ..schema import BuildingModel, Finding
from .runtime import Evaluator, Trace, run_program
from .schema import BinaryExpr, FactExpr, Inputs, LogicExpr, Program, SetExpr

SYMBOL = {"ge": ">=", "le": "<=", "gt": ">", "lt": "<", "eq": "==", "ne": "!="}
FACT_LIMIT = 3          # facts listed per unresolved member


@dataclass
class MemberResult:
    entity: str
    state: str                          # violated | satisfied | unknown
    detected: str | None = None
    required: str | None = None
    missing: list[str] = field(default_factory=list)
    fails: list[dict] = field(default_factory=list)      # one per failed comparison: {what, detected, required}


@dataclass
class Explained:
    outcome: str
    missing: list[str]
    members: list[MemberResult]
    selected: int                       # members the rule applied to (a filter may leave some out)
    issues: list[EvidenceIssue] = field(default_factory=list)      # why a decisive answer is not possible
    dependencies: list[str] = field(default_factory=list)          # facts and inventories the answer rests on


def _fmt(value, unit: str | None) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text} {unit}" if unit and unit not in ("1", "count") else text


def _unit(expr: BinaryExpr, inputs: Inputs) -> str | None:
    for side in (expr.left, expr.right):
        if isinstance(side, FactExpr) and side.name in inputs.bindings:
            return inputs.bindings[side.name].unit
    return None


def _what(expr: BinaryExpr, inputs: Inputs) -> str:
    for side in (expr.left, expr.right):
        if isinstance(side, FactExpr):
            binding = inputs.bindings.get(side.name)
            return (binding.description if binding and binding.description else side.name).split(" (")[0].lower()
    return "value"


def failing_comparisons(expr, trace: Trace, inputs: Inputs) -> list[dict]:
    """Every comparison inside `expr` that came out False, read from the evaluation trace: what, detected, required."""
    if isinstance(expr, BinaryExpr) and expr.node in SYMBOL:
        if trace.value is False and len(trace.children) == 2:
            unit = _unit(expr, inputs)
            left, right = trace.children[0].value, trace.children[1].value
            if isinstance(expr.left, FactExpr):
                return [{"what": _what(expr, inputs), "detected": _fmt(left, unit),
                         "required": f"{SYMBOL[expr.node]} {_fmt(right, unit)}"}]
            return [{"what": _what(expr, inputs), "detected": _fmt(right, unit),
                     "required": f"{SYMBOL[expr.node]} {_fmt(left, unit)}"}]
        return []
    if isinstance(expr, LogicExpr) and len(trace.children) == len(expr.args):
        out = []
        for arg, child in zip(expr.args, trace.children, strict=True):
            if child.value is False:
                out += failing_comparisons(arg, child, inputs)
        return out
    return []


def explain(program: Program, inputs: Inputs, graph=None) -> Explained:
    result = run_program(program, inputs, include_drafts=program.status != "approved", graph=graph)
    outcome = result["outcome"]
    missing = list(result["trace"].get("missing", []))
    req = program.requirement
    members: list[MemberResult] = []
    selected = 0
    if isinstance(req, SetExpr) and req.node == "forall" and req.collection in inputs.collections:
        evaluator = Evaluator(inputs, graph)
        for entity in inputs.collections[req.collection].items:
            scope = {req.variable: entity}
            if req.where is not None and evaluator.evaluate(req.where, scope).value is not True:
                continue
            selected += 1
            body = evaluator.evaluate(req.body, scope)
            if body.value is True:
                members.append(MemberResult(entity, "satisfied"))
            elif body.value is False:
                fails = failing_comparisons(req.body, body, inputs)
                members.append(MemberResult(
                    entity, "violated", detected="; ".join(f["detected"] for f in fails) or None,
                    required="; ".join(f["required"] for f in fails) or None, fails=fails))
            else:
                members.append(MemberResult(entity, "unknown", missing=body.missing[:FACT_LIMIT]))
    issues = [EvidenceIssue.model_validate(i) for i in result.get("evidence_issues", [])]
    issues += [i for i in _issues_from_missing(missing) if i.code not in {x.code for x in issues}]
    return Explained(outcome, missing, members, selected, issues, list(result.get("dependencies", [])))


def _issues_from_missing(missing: list[str]) -> list[EvidenceIssue]:
    """The reason codes of the shared verdict policy, read from the facts a rule could not use."""
    out: dict[IssueCode, str] = {}
    for item in missing:
        text = item.lower()
        if "room graph" in text or "connection" in text or "path endpoint" in text:
            out.setdefault(IssueCode.MISSING_CONNECTION, item)
        elif "room_type" in text and ("unverified" in text or "missing" in text):
            out.setdefault(IssueCode.UNKNOWN_CLASS, item)
        elif "(unverified)" in text or "(conflicting)" in text:
            out.setdefault(IssueCode.UNVERIFIED_GEOMETRY, item)
        elif "unverified member" in text or "incomplete" in text:
            out.setdefault(IssueCode.INCOMPLETE_INVENTORY, item)
        else:
            out.setdefault(IssueCode.MISSING_INPUT, item)
    return [EvidenceIssue(code=code, detail=detail) for code, detail in out.items()]


# ---- geometry and wording ------------------------------------------------------------------------------------------


def _collection(program: Program) -> str:
    req = program.requirement
    return req.collection if isinstance(req, SetExpr) else "members"


def geometry_of(model: BuildingModel, entity: str) -> dict:
    """Where an entity is on the sheet, in the evidence format the viewer draws."""
    for room in model.rooms:
        if room.id == entity:
            return {"polygons": [room.polygon], "label_at": _centre(room.polygon), "name": room.label or room.type or entity}
    for element in model.elements:
        if element.id == entity:
            polygons = [element.geom] + ([element.attrs["swing_polygon"]] if element.attrs.get("swing_polygon") else [])
            return {"polygons": polygons, "label_at": _centre(element.geom),
                    "name": element.tag or f"{element.cls} {entity}"}
    return {"polygons": [], "label_at": None, "name": entity}


def _centre(points) -> tuple[float, float] | None:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)) if points else None


def _source(program: Program) -> dict:
    span = program.sources[0] if program.sources else None
    return {"doc": program.document, "clause": span.clause if span else None,
            "span": [span.start, span.end] if span else None}


def to_findings(program: Program, inputs: Inputs, graph, model: BuildingModel | None = None, tier: str = "T1",
                locate=None) -> tuple[list[Finding], Explained]:
    """`locate(entity) -> {polygons, label_at, name}` says where a member is drawn. The building plan reader's locator is
    used when `model` is given; any other producer passes its own, or none (findings then carry no outline)."""
    if locate is None:
        if model is not None:
            def locate(entity):
                return geometry_of(model, entity)
        else:
            def locate(entity):
                return {"polygons": [], "label_at": None, "name": entity}
    explained = explain(program, inputs, graph)
    assessment = Assessment(outcome=explained.outcome, evidence_issues=explained.issues, severity="MAJOR",
                            rule_authority="APPROVED_REQUIREMENT", dependencies=explained.dependencies)
    base = {"rule_id": program.id, "severity": "major", "tier": tier, "source": _source(program),
            "assessment": assessment}
    meta = {"outcome": explained.outcome, "program_id": program.id, "interpreted": True,
            "approved_by": program.approved_by, "title": program.title}
    findings: list[Finding] = []
    if explained.outcome == "VIOLATED":
        violated = [m for m in explained.members if m.state == "violated"]
        for m in violated:
            geo = locate(m.entity)
            labels = [{"at": geo["label_at"], "text": m.detected}] if geo["label_at"] and m.detected else []
            said = "; ".join(f"{f['what']} is {f['detected']} ({f['required']} required)" for f in m.fails)
            findings.append(Finding(
                **base, verdict="FAIL", subject_ids=[m.entity], detected=m.detected, required=m.required,
                message=f"{program.title}: {geo['name']}: {said or 'does not comply'}.",
                evidence={"polygons": geo["polygons"], "labels": labels, "deciding_ids": [m.entity], **meta}))
        if not violated:      # a total, a count or a route: the whole plan is the subject
            findings.append(Finding(**base, verdict="FAIL", subject_ids=[], message=f"{program.title}: not satisfied.",
                                    evidence=meta))
    elif explained.outcome == "SATISFIED":
        n = explained.selected
        findings.append(Finding(**base, verdict="PASS", subject_ids=[m.entity for m in explained.members],
                                message=f"{program.title}: satisfied" + (f" by all {n} checked." if n else "."),
                                evidence={**meta, "checked": n}))
    elif explained.outcome == "UNRESOLVED":
        unknown = [m for m in explained.members if m.state == "unknown"]
        only_inventory = (not unknown and explained.members and all(x.startswith("incomplete") for x in explained.missing)
                          and all(m.state == "satisfied" for m in explained.members))
        if only_inventory:      # nothing wrong among what was found, but the list was not confirmed complete
            findings.append(Finding(
                **base, verdict="WARNING", subject_ids=[m.entity for m in explained.members],
                message=f"{program.title}: no violation among the {explained.selected} found; not confirmed, because the "
                        f"nobody confirmed that the list of {_collection(program)} is complete.",
                evidence={**meta, "checked": explained.selected}))
        else:
            reason = ", ".join(explained.missing[:FACT_LIMIT]) or "facts the plan does not provide"
            findings.append(Finding(**base, verdict="NOT_EVALUATED", subject_ids=[m.entity for m in unknown],
                                    message=f"{program.title}: not decided, missing {reason}.",
                                    evidence={**meta, "missing": explained.missing[:10]}))
    return findings, explained
