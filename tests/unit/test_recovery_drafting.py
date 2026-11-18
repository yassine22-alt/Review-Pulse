import json

import pytest
from pydantic import ValidationError

from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.decomposed import (
    ExpressionFrame,
    formal_request,
    reading_request,
    repair_field,
    repair_request,
    schema_contract,
)
from reviewpulse.interpreter.structured import SlotFailure
from reviewpulse.rules.clauses import Clause


def context():
    text = "A requirement needing review."
    return ContextBundle(document="research", text=text, target="target",
                         clauses=[Clause("target", "", text, 1, 0, len(text))])


def test_reading_has_source_only_and_advisory_opinion_cannot_remove_target():
    ctx = context()
    _, source, _ = reading_request(ctx)
    assert set(source) == {"target", "context"}
    formal = formal_request(ctx, {"catalogue": {}}, {"is_requirement": False})
    assert formal["target_clause"]["text"] == ctx.text
    assert formal["semantic_reading"]["is_requirement"] is False


def test_expression_frame_rejects_uncompiled_extra_constraints():
    with pytest.raises(ValidationError):
        ExpressionFrame.model_validate({"title": "x", "subject": "x", "applies_when": None,
            "unless": None, "require": "true", "sources": [], "metadata_applicability": [],
            "fact_declarations": [], "unresolved": [], "extra_constraint": "false"})


def test_contract_omits_unreachable_definitions_but_keeps_recursive_references():
    schema = {"type": "object", "properties": {"root": {"$ref": "#/$defs/Node"}},
              "$defs": {"Node": {"properties": {"next": {"$ref": "#/$defs/Node"}}}, "Unused": {}}}
    assert set(schema_contract(schema)["$defs"]) == {"Node"}


def test_repair_cites_actual_diagnostic_and_cannot_rewrite_other_fields():
    ctx = context()
    raw = {"sources": [{"clause": "target", "quote": "absent text"}], "require": "true"}
    error = SlotFailure("source_span", "quote has no occurrence")
    field = repair_field(raw, ctx, error)
    assert field == "sources"
    _, payload, schema = repair_request(raw, field, {"properties": {field: {"type": "array"}}}, {}, error)
    assert json.loads(payload)["failed_check"] == {"stage": "source_span", "detail": str(error)}
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"sources"}
