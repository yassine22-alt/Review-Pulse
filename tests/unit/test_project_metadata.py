import copy

import pytest

from reviewpulse.interpreter.checked import catalogue_from
from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Inputs
from reviewpulse.interpreter.structured import SlotDraft, SlotFailure, compile_slots, slots_from_program
from reviewpulse.rules.clauses import Clause


def scoped_rule():
    text = "For occupancy from 11 to 19, capacity must be at least 6."
    context = ContextBundle(document="synthetic", text=text, target="s",
                            clauses=[Clause("s", "", text, 0, 0, len(text))])
    source = {"clause": "s", "quote": text}
    frame = {"id": "s", "title": "Capacity", "subject": "capacity", "sources": [source],
             "metadata_applicability": [
                 {"field": "occupancy", "kind": "number", "unit": "count", "operator": op,
                  "value": value, "source": source} for op, value in [("ge", 11), ("le", 19)]],
             "nodes": [{"id": "n0", "op": "fact", "entity": "building", "name": "capacity"},
                       {"id": "n1", "op": "literal", "value": 6, "unit": "count"},
                       {"id": "n2", "op": "ge", "left": "n0", "right": "n1"}], "requirement": "n2"}
    inputs = Inputs.model_validate({"bindings": {"capacity": {"kind": "number", "unit": "count"}},
                                    "facts": {"building": {"capacity": {
                                        "value": 8, "trusted": True, "source": "Synthetic schedule"}}}})
    return context, inputs, frame


def test_scope_numbers_are_covered_without_entering_requirement():
    context, inputs, raw = scoped_rule()
    program = compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    assert program.requirement.right.value == 6
    assert len(program.metadata_applicability) == 2
    round_trip = compile_slots(SlotDraft.model_validate(slots_from_program(program, raw["subject"])),
                               context, catalogue_from(inputs, None))
    assert round_trip.metadata_applicability == program.metadata_applicability
    result = run_program(program, inputs, include_drafts=True)
    assert result["outcome"] == "UNRESOLVED"
    assert result["metadata_requests"][0]["request_type"] == "project_metadata"
    assert result["metadata_requests"][0]["fact"] == "occupancy"
    assert "metadata:occupancy" in result["dependencies"]


@pytest.mark.parametrize("value,trusted,conflicting,unit,outcome", [
    (15, True, False, "count", "SATISFIED"), (22, True, False, "count", "NOT_APPLICABLE"),
    (15, False, False, "count", "UNRESOLVED"), (15, True, True, "count", "UNRESOLVED"),
    ("15", True, False, "count", "UNRESOLVED"), (15, True, False, "m", "UNRESOLVED")])
def test_metadata_is_never_assumed(value, trusted, conflicting, unit, outcome):
    context, inputs, raw = scoped_rule()
    program = compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    data = inputs.model_dump()
    data["project_metadata"] = {"occupancy": {"value": value, "trusted": trusted,
                                             "conflicting": conflicting, "unit": unit,
                                             "source": "Synthetic attestation", "reviewer": "Synthetic reviewer",
                                             "origin": "reviewer-attested"}}
    result = run_program(program, Inputs.model_validate(data), include_drafts=True)
    assert result["outcome"] == outcome
    assert result["metadata_provenance"][0]["origin"] == "reviewer-attested"


def test_scope_does_not_hide_a_dropped_requirement_quantity():
    context, inputs, raw = scoped_rule()
    changed = copy.deepcopy(raw)
    changed["metadata_applicability"] = []
    with pytest.raises(SlotFailure, match="never uses"):
        compile_slots(SlotDraft.model_validate(changed), context, catalogue_from(inputs, None))
    changed = copy.deepcopy(raw)
    changed["nodes"][1]["value"] = 99
    with pytest.raises(SlotFailure):
        compile_slots(SlotDraft.model_validate(changed), context, catalogue_from(inputs, None))


def test_metadata_cannot_invent_scope_values():
    context, inputs, raw = scoped_rule()
    raw["metadata_applicability"][0]["value"] = 98
    with pytest.raises(SlotFailure, match="not traceable"):
        compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))


def test_fieldwise_assembly_uses_field_schemas_and_the_same_compiler():
    import json

    from reviewpulse.interpreter.structured import draft_structured

    context, inputs, raw = scoped_rule()
    skeleton = copy.deepcopy(raw)
    for node in skeleton["nodes"]:
        for key in ("name", "value", "unit"):
            node.pop(key, None)
    answers = {"subject": raw["subject"], "metadata_applicability": raw["metadata_applicability"],
               "structure": {"nodes": skeleton["nodes"], "requirement": raw["requirement"]},
               "facts": {"n0": "capacity"}, "operators": {"n2": "ge"},
               "values": {"n1": 6}, "units": {"n1": "count"}, "sources": raw["sources"], "unresolved": []}

    class Client:
        fieldwise = True
        model = "fixture"
        calls = []

        def complete(self, system, user, schema):
            field = json.loads(user)["requested_field"]
            assert schema["required"] == [field]
            assert list(schema["properties"]) == [field]
            self.calls.append(field)
            return {field: answers[field]}

    client = Client()
    drafted = draft_structured(context, catalogue_from(inputs, None), context.text, client)
    assert drafted["retained"]
    assert drafted["program"]["requirement"]["right"]["value"] == 6
    assert len(drafted["program"]["metadata_applicability"]) == 2
    assert len(client.calls) == len(answers)
    assert drafted["raw_slot_attempts"][0]["subject"] == raw["subject"]
