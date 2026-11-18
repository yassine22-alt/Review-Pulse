"""Project scope is declared evidence, separate from measured requirement facts."""
from __future__ import annotations

import operator
from pathlib import Path
from typing import Literal

import yaml

from .evidence import EvidenceRequest
from .schema import Inputs, MetadataCondition, scalar_kind
from .units import convert

COMPARATORS = {"eq": operator.eq, "ne": operator.ne, "lt": operator.lt,
               "le": operator.le, "gt": operator.gt, "ge": operator.ge}


class MetadataRequest(EvidenceRequest):
    request_type: Literal["project_metadata"] = "project_metadata"
    kind: Literal["number", "boolean", "string"]
    reason: Literal["missing", "conflicting", "unverified", "type_mismatch", "unit_mismatch"]


def metadata_vocabulary() -> dict:
    return yaml.safe_load(Path(__file__).with_name("metadata.yaml").read_text(encoding="utf-8"))


def evaluate_metadata(conditions: list[MetadataCondition], inputs: Inputs) -> dict:
    values, requests, provenance = [], {}, {}
    for condition in conditions:
        fact = inputs.project_metadata.get(condition.field)
        reason, value = None, None
        if fact is None or fact.value is None:
            reason = "missing"
        elif fact.conflicting:
            reason = "conflicting"
        elif not fact.trusted:
            reason = "unverified"
        elif scalar_kind(fact.value) != condition.kind:
            reason = "type_mismatch"
        else:
            try:
                value = convert(fact.value, fact.unit, condition.unit) if condition.kind == "number" else fact.value
                if condition.kind != "number" and fact.unit != "1":
                    raise ValueError("nonnumeric metadata has units")
            except ValueError:
                reason = "unit_mismatch"
        values.append(None if reason else COMPARATORS[condition.operator](value, condition.value))
        if fact is not None:
            provenance[condition.field] = {"field": condition.field, **fact.model_dump(mode="json")}
        if reason:
            requests.setdefault((condition.field, reason), MetadataRequest(
                entity="project", fact=condition.field, kind=condition.kind, unit=condition.unit,
                reason=reason, clause=condition.source.clause,
                why="This metadata determines whether the obligation applies.",
                where_to_look="Project brief, approved project schedule or named reviewer attestation").model_dump(mode="json"))
    return {"value": False if False in values else None if None in values else True,
            "requests": list(requests.values()), "provenance": list(provenance.values()),
            "dependencies": sorted({f"metadata:{condition.field}" for condition in conditions})}
