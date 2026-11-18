"""Compact source reading and focused repair; the existing expression compiler remains the gate."""
from __future__ import annotations

import json

from ..xeval.flat import FlatSpan
from .schema import Model
from .structured import MetadataSlot, ProposedFact, ground_span


class ExpressionFrame(Model):
    title: str
    subject: str
    applies_when: str | None
    unless: str | None
    require: str
    sources: list[FlatSpan]
    metadata_applicability: list[MetadataSlot]
    fact_declarations: list[ProposedFact]
    unresolved: list[str]

READING_SCHEMA = {"type": "object", "additionalProperties": False,
                  "properties": {"is_requirement": {"type": "boolean"}, **{
                      field: {"type": "string"} for field in ("subject",)}, **{
                      field: {"type": "array", "items": {"type": "string"}}
                      for field in ("constraints", "applicability", "exceptions", "relationships", "references", "uncertain")}},
                  "required": ["is_requirement", "subject", "constraints", "applicability", "exceptions", "relationships", "references", "uncertain"]}
READING_SYSTEM = """Read only the target requirement. Return terse semantic fields, not a program.
Preserve subjects, properties, obligation/permission, comparator, every quantity and unit,
quantifiers, conditions, exceptions, relationships and references. Copy explicit information;
put interpretations requiring assumptions in uncertain. Context explains the target, it is not
an additional obligation. is_requirement is advisory and never suppresses formalization."""


def reading_request(context):
    target = next(clause for clause in context.clauses if clause.id == context.target)
    return READING_SYSTEM, {"target": {"id": target.id, "text": target.text, "kind": target.kind},
                            "context": [{"id": clause.id, "text": clause.text, "kind": clause.kind}
                                        for clause in context.clauses if clause.id != target.id]}, READING_SCHEMA


def formal_request(context, payload, reading=None):
    target = next(clause for clause in context.clauses if clause.id == context.target)
    return {**payload, "target_clause": {"id": target.id, "text": target.text, "kind": target.kind},
            "semantic_reading": reading}


def schema_contract(schema):
    """Expose the output meaning to the model, not just the decoding engine."""
    result = {key: value for key, value in schema.items() if key != "$defs"}
    found = {}

    def refs(value):
        if isinstance(value, dict):
            if "$ref" in value:
                name = value["$ref"].rsplit("/", 1)[-1]
                if name not in found:
                    found[name] = schema["$defs"][name]
                    refs(found[name])
            for child in value.values():
                refs(child)
        elif isinstance(value, list):
            for child in value:
                refs(child)

    refs(result)
    return result | {"$defs": found}


def repair_field(raw, context, error, reading=None):
    """Return the smallest root field justified by a diagnostic, without gold answers."""
    for field in ("sources", "metadata_applicability", "fact_declarations"):
        for entry in raw.get(field, []):
            source = entry if field == "sources" else entry.get("source")
            if not source:
                return field
            try:
                ground_span(FlatSpan.model_validate(source), context)
            except ValueError:
                return field
    stage = getattr(error, "stage", "")
    if stage.startswith("metadata"):
        return "metadata_applicability"
    if stage in ("declaration", "entity_binding", "binding"):
        return "unresolved"
    if stage == "verifier" and (reading or {}).get("applicability") and "never uses" in str(error):
        return "metadata_applicability"
    return "require"


def repair_request(raw, field, schema, payload, error):
    return (
        "Correct only the requested field using the source and the failed check. Preserve all other meaning. "
        "If context or computation is unavailable, do not invent it. Use short exact unique source quotations.",
        json.dumps({**payload, "candidate": raw, "repair_field": field,
                    "failed_check": {"stage": getattr(error, "stage", type(error).__name__), "detail": str(error)}}, ensure_ascii=False),
        {"type": "object", "properties": {field: schema["properties"][field]}, "required": [field],
         "additionalProperties": False, "$defs": schema.get("$defs", {})})
