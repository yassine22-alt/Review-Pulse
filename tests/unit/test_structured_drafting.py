import copy

import pytest

from reviewpulse.interpreter.checked import catalogue_from, checked_draft
from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.schema import Inputs
from reviewpulse.interpreter.structured import SlotDraft, SlotFailure, compile_slots, slot_schema
from reviewpulse.rules.clauses import Clause


def case():
    text = "Each panel needs an area of at least 4 m2 and width of at least 80 cm."
    context = ContextBundle(document="fixture", text=text, target="r",
                            clauses=[Clause("r", "", text, 0, 0, len(text))])
    inputs = Inputs.model_validate({
        "bindings": {"area": {"kind": "number", "unit": "m2", "description": "panel area"},
                     "width": {"kind": "number", "unit": "m", "description": "panel width"}},
        "facts": {"panel": {"area": {"source": "fixture"}, "width": {"source": "fixture"}}},
        "collections": {"panels": {"items": ["panel"]}}})
    frame = {
        "id": "r", "title": "Panel dimensions", "subject": "panel",
        "sources": [{"clause": "r", "quote": text}], "nodes": [
            {"id": "a", "op": "fact", "entity": "$p", "name": "area"},
            {"id": "v", "op": "literal", "value": 4, "unit": "m2"},
            {"id": "area", "op": "ge", "left": "a", "right": "v"},
            {"id": "w", "op": "fact", "entity": "$p", "name": "width"},
            {"id": "u", "op": "literal", "value": 80, "unit": "cm"},
            {"id": "width", "op": "ge", "left": "w", "right": "u"},
            {"id": "both", "op": "all", "args": ["area", "width"]},
            {"id": "all", "op": "forall", "collection": "panels", "variable": "$p", "body": "both"}],
        "requirement": "all",
    }
    return context, inputs, frame


def test_structured_dimensions_convert_units_and_preserve_both_constraints():
    context, inputs, raw = case()
    program = compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    assert len(program.requirement.body.args) == 2
    assert program.requirement.body.args[1].right.value == 0.8
    assert program.requirement.body.args[1].right.unit == "m"
    assert program.status == "draft" and program.approved_by is None


def test_generation_schema_has_only_fields_relevant_to_each_slot():
    context, inputs, _ = case()
    schema = slot_schema(catalogue_from(inputs, None), context)
    choices = schema["$defs"]["FlatNode"]["oneOf"]
    fact = next(choice for choice in choices if choice["properties"]["op"]["enum"] == ["fact"])
    assert set(fact["properties"]) == {"id", "op", "entity", "name"}
    assert fact["additionalProperties"] is False
    assert schema["$defs"]["FlatSpan"]["properties"]["clause"]["enum"] == ["r"]


def test_repeated_node_records_are_rejected_even_if_generation_finishes():
    context, inputs, raw = case()
    raw["nodes"].append(copy.deepcopy(raw["nodes"][0]))
    with pytest.raises(SlotFailure, match="unique|duplicate"):
        compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))


@pytest.mark.parametrize("mutation,stage", [
    ("unused_constraint", "compile"), ("fake_quote", "source_span"), ("incompatible_unit", "types_or_units"),
    ("wrong_number", "verifier"), ("unknown_fact", "binding"), ("unused_condition", "compile")])
def test_bad_slots_cannot_produce_an_approvable_rule(mutation, stage):
    context, inputs, raw = case()
    raw = copy.deepcopy(raw)
    if mutation == "unused_constraint":
        raw["nodes"][-1]["body"] = "area"
    elif mutation == "fake_quote":
        raw["sources"][0]["quote"] = "absent source quotation"
    elif mutation == "incompatible_unit":
        raw["nodes"][4]["unit"] = "m2"
    elif mutation == "wrong_number":
        raw["nodes"][4]["value"] = 90
    elif mutation == "unknown_fact":
        raw["nodes"][3]["name"] = "undeclared"
    else:
        raw["nodes"][0]["where"] = "area"
    with pytest.raises(SlotFailure) as error:
        compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    assert error.value.stage == stage


def test_triage_decline_is_advisory(monkeypatch):
    context, inputs, raw = case()
    monkeypatch.setattr("reviewpulse.interpreter.triage.triage", lambda *_: (False, "not visible"))

    class Model:
        model = "fixture"

        def complete(self, system, user, schema):
            assert "nodes" in schema["properties"]
            return raw

    result = checked_draft(context, inputs, None, Model(), triage=True)
    assert result["status"] == "DRAFTED"
    assert result["triage"] == {"checkable": False, "reason": "not visible", "advisory": True}
    assert result["review_status"] == "HUMAN_APPROVAL_REQUIRED"


def test_dimensionless_multiplier_does_not_become_a_count():
    text = "Qualified units multiplied by 5 must reach the number of units."
    context = ContextBundle(document="fixture", text=text, target="r",
                            clauses=[Clause("r", "", text, 0, 0, len(text))])
    inputs = Inputs.model_validate({"bindings": {
        "qualified": {"kind": "number", "unit": "count", "description": "qualified units"},
        "units": {"kind": "number", "unit": "count", "description": "units"}},
        "facts": {"building": {"qualified": {"source": "fixture"}, "units": {"source": "fixture"}}}})
    frame = SlotDraft.model_validate({
        "id": "r", "title": "Qualified units", "subject": "units", "sources": [{"clause": "r", "quote": text}],
        "nodes": [{"id": "q", "op": "fact", "entity": "building", "name": "qualified"},
                  {"id": "u", "op": "fact", "entity": "building", "name": "units"},
                  {"id": "five", "op": "literal", "value": 5},
                  {"id": "scaled", "op": "mul", "left": "q", "right": "five"},
                  {"id": "limit", "op": "ge", "left": "scaled", "right": "u"}],
        "requirement": "limit",
    })
    program = compile_slots(frame, context, catalogue_from(inputs, None))
    assert program.requirement.left.right.unit == "1"


def test_wire_schema_excludes_sentences_and_quantities_as_references():
    import re

    from reviewpulse.interpreter.structured import slot_schema

    context, inputs, _ = case()
    schema = slot_schema(catalogue_from(inputs, None), context)
    assert schema["properties"]["nodes"]["maxItems"] == 64
    pattern = schema["properties"]["requirement"]["pattern"]
    assert re.fullmatch(pattern, "n12")
    assert not re.fullmatch(pattern, "1.4 m")
    assert not re.fullmatch(pattern, "The full source sentence")
    for form in schema["$defs"]["FlatNode"]["oneOf"]:
        assert form["properties"]["id"]["pattern"] == pattern
        for name in ("left", "right", "body", "where", "node_filter", "edge_filter"):
            if name in form["properties"]:
                assert form["properties"][name]["pattern"] == pattern
