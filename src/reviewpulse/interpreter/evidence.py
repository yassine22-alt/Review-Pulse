"""Typed evidence for existing rules. This module does not infer or synthesize values."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

from .schema import EvidenceOrigin, Fact, Inputs, Model, Scalar, Unit, scalar_kind
from .units import convert


class EvidenceRequest(Model):
    entity: str
    fact: str
    unit: Unit
    reason: Literal["missing", "conflicting", "unverified"]
    why: str
    where_to_look: str
    clause: str


class EvidenceEntry(Model):
    entity: str
    fact: str
    value: Scalar
    unit: Unit = "1"
    origin: EvidenceOrigin
    source: str
    reviewer: str | None = None
    trusted: bool = False


def apply_evidence(inputs: Inputs, entries: list[EvidenceEntry]) -> Inputs:
    """Add scoped values with citations. Different values stay conflicting after merging."""
    grouped = defaultdict(list)
    for entry in entries:
        if entry.fact not in inputs.bindings:
            raise ValueError(f"undeclared evidence fact: {entry.fact}")
        if entry.entity != "building" and not any(
            entry.entity in collection.items for collection in inputs.collections.values()
        ) and entry.entity not in inputs.facts:
            raise ValueError(f"unknown evidence entity: {entry.entity}")
        if not entry.source.strip():
            raise ValueError("evidence requires a source citation")
        binding = inputs.bindings[entry.fact]
        value = entry.value
        if scalar_kind(value) != binding.kind:
            raise ValueError(f"wrong type for evidence fact: {entry.fact}")
        if entry.unit != binding.unit:
            if type(value) not in (int, float):
                raise ValueError("only numeric evidence can be converted")
            value = convert(value, entry.unit, binding.unit)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"non-finite evidence fact: {entry.fact}")
        grouped[entry.entity, entry.fact].append(Fact(
            value=value, source=entry.source, trusted=entry.trusted, origin=entry.origin, reviewer=entry.reviewer
        ))
    result = inputs.model_dump()
    for (entity, name), facts in grouped.items():
        old = inputs.facts.get(entity, {}).get(name)
        if old and (old.value is not None or old.conflicting):
            facts.insert(0, old)
        preferred = next((fact for fact in facts if fact.trusted), facts[0])
        conflicting = any(
            fact.conflicting or (type(fact.value) is bool) != (type(preferred.value) is bool)
            or fact.value != preferred.value for fact in facts
        )
        merged = preferred.model_dump()
        if conflicting:
            merged.update(value=None, trusted=False, conflicting=True,
                          source=" | ".join(dict.fromkeys(fact.source for fact in facts)))
        result["facts"].setdefault(entity, {})[name] = merged
    return Inputs.model_validate(result)
