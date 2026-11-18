"""Conservative candidate agreement, never automatic rule approval."""
from __future__ import annotations

import json

from .schema import Program
from .units import parse_unit


def semantic_key(program: Program) -> str:
    def node(value, variables=None):
        variables = variables or {}
        if isinstance(value, list):
            return [node(child, variables) for child in value]
        if not isinstance(value, dict):
            return variables.get(value, value) if isinstance(value, str) else value
        value = dict(value)
        if value.get("variable"):
            original = value["variable"]
            variables = {**variables, original: f"$v{len(variables)}"}
        if value.get("node") == "literal" and type(value.get("value")) in (int, float):
            unit = parse_unit(value.get("unit", "1"))
            return {"node": "literal", "value": round(value["value"] * unit.factor + unit.offset, 9),
                    "dimensions": unit.dims}
        result = {key: node(child, variables) for key, child in value.items()}
        if value.get("node") in ("all", "any"):
            result["args"] = sorted(result["args"], key=lambda item: json.dumps(item, sort_keys=True))
        return result

    data = program.model_dump(exclude={"id", "title", "document", "status", "approved_by"})
    # Citations may choose different subspans. Keep their clause identities; each span must already be grounded.
    data["sources"] = sorted({source.clause for source in program.sources})
    data["metadata_applicability"] = sorted(data["metadata_applicability"], key=lambda item: json.dumps(item, sort_keys=True))
    return json.dumps(node(data), sort_keys=True, ensure_ascii=False)


def agreement_gate(left: dict, right: dict) -> dict:
    result = {"status": "NEEDS_REVIEW", "proposals": [left, right], "approved": False}
    if not left.get("model") or not right.get("model") or left["model"] == right["model"]:
        return result | {"reason": "Two different drafting models are required"}
    if not left.get("retained") or not right.get("retained"):
        return result | {"reason": "At least one draft is unavailable or failed validation"}
    programs = [Program.model_validate(item["program"]) for item in (left, right)]
    if any(program.unresolved or program.not_checked for program in programs):
        return result | {"reason": "Incomplete meaning is not an agreed candidate"}
    subjects = [" ".join(item["raw"].get("subject", "").casefold().split()) for item in (left, right)]
    if not subjects[0] or subjects[0] != subjects[1] or semantic_key(programs[0]) != semantic_key(programs[1]):
        return result | {"reason": "Subject, scope, facts or connected predicates disagree"}
    return result | {"status": "CANDIDATE", "reason": "Validated drafts agree; human source review and approval still required",
                     "program": programs[0].model_dump(mode="json")}
