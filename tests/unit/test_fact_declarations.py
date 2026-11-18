import copy

import pytest
from pydantic import ValidationError

from reviewpulse.interpreter.checked import catalogue_from
from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.declarations import apply_declarations
from reviewpulse.interpreter.evidence import EvidenceEntry, apply_evidence
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Inputs
from reviewpulse.interpreter.structured import (
    SlotDraft,
    SlotFailure,
    compile_slots,
    draft_structured,
    slot_schema,
)
from reviewpulse.interpreter.units import compatible, convert
from reviewpulse.rules.clauses import Clause


def fixture():
    text = "Panel heat transfer shall be at most 0.8 W/m²/K."
    context = ContextBundle(document="synthetic", text=text, target="r",
                            clauses=[Clause("r", "", text, 0, 0, len(text))])
    inputs = Inputs(bindings={})
    frame = {"id": "r", "title": "Panel transfer", "subject": "Panel heat transfer",
             "sources": [{"clause": "r", "quote": text}],
             "fact_declarations": [{"name": "transfer", "kind": "number", "unit": "W/m²/K",
                                    "entity": "building", "definition": "Panel heat transfer",
                                    "source": {"clause": "r", "quote": text}}],
             "nodes": [{"id": "property", "op": "fact", "entity": "building", "name": "transfer"},
                       {"id": "limit", "op": "literal", "value": 0.8, "unit": "W/m²/K"},
                       {"id": "comparison", "op": "le", "left": "property", "right": "limit"}],
             "requirement": "comparison"}
    return context, inputs, frame


def test_declaration_retains_ir_but_cannot_supply_a_value_or_a_verdict():
    context, inputs, raw = fixture()
    catalogue = catalogue_from(inputs, None)
    program = compile_slots(SlotDraft.model_validate(raw), context, catalogue)
    assert inputs.bindings == {} and catalogue["bindings"] == {}
    assert program.fact_declarations[0].status == "declared"
    result = run_program(program, inputs, include_drafts=True)
    assert result["outcome"] == "UNRESOLVED"
    assert result["fact_provenance"][0]["value"] is None
    assert result["fact_provenance"][0]["origin"] is None
    assert result["evidence_requests"][0]["fact"] == "transfer"

    class Model:
        model = "fixture"

        def complete(self, *_):
            return raw

    drafted = draft_structured(context, catalogue, context.text, Model())
    assert drafted["status"] == "UNRESOLVED" and drafted["retained"]
    assert drafted["review_status"] == "NEEDS_EVIDENCE"


def test_only_named_reviewer_evidence_can_resolve_a_declared_property():
    context, inputs, raw = fixture()
    program = compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    declared = apply_declarations(inputs, program.fact_declarations)
    assert apply_declarations(declared, program.fact_declarations) == declared
    with pytest.raises(ValueError, match="reviewer"):
        apply_evidence(declared, [EvidenceEntry(entity="building", fact="transfer", value=0.7, unit="W/m2/K",
                                               origin="computed", source="model claim", trusted=True)])
    evidence = EvidenceEntry(entity="building", fact="transfer", value=0.7, unit="W/m2/K",
                             origin="reviewer-attested", source="Synthetic signed certificate",
                             reviewer="Synthetic reviewer", trusted=True)
    observed = apply_evidence(declared, [evidence])
    assert run_program(program, observed, include_drafts=True)["outcome"] == "SATISFIED"
    conflict = evidence.model_copy(update={"value": 0.9, "source": "Synthetic conflicting certificate"})
    disputed = apply_evidence(observed, [conflict])
    assert run_program(program, disputed, include_drafts=True)["outcome"] == "UNRESOLVED"


@pytest.mark.parametrize("mutation,stage", [("entity", "entity_binding"), ("quote", "source_span"),
                                            ("dimension", "types_or_units")])
def test_invalid_declarations_cannot_produce_a_retained_rule(mutation, stage):
    context, inputs, raw = fixture()
    proposal = raw["fact_declarations"][0]
    if mutation == "entity":
        proposal["entity"] = "unknown_inventory"
    elif mutation == "quote":
        proposal["source"]["quote"] = "not in the source"
    else:
        proposal["unit"] = "m"
    with pytest.raises(SlotFailure) as error:
        compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    assert error.value.stage == stage


def test_model_values_and_illegal_units_are_rejected():
    _, _, raw = fixture()
    proposed = copy.deepcopy(raw)
    proposed["fact_declarations"][0]["value"] = 0.7
    with pytest.raises(ValidationError, match="Extra inputs"):
        SlotDraft.model_validate(proposed)
    raw["fact_declarations"][0]["unit"] = "invented_unit"
    with pytest.raises(ValidationError) as error:
        SlotDraft.model_validate(raw)
    assert error.value.errors()[0]["loc"][-1] == "unit"


def test_thermal_spellings_and_generation_choices_come_from_unit_data():
    context, inputs, _ = fixture()
    assert compatible("W/m²/K", "W/m2/K")
    assert convert(0.75, "m²·K/W", "m2.K/W") == 0.75
    schema = slot_schema(catalogue_from(inputs, None), context)
    choices = schema["$defs"]["ProposedFact"]["properties"]["unit"]["enum"]
    assert "W/m²/K" in choices and "m²·K/W" in choices and "count" in choices


def test_direct_input_injection_cannot_call_a_declared_fact_extracted():
    context, inputs, raw = fixture()
    program = compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    data = apply_declarations(inputs, program.fact_declarations).model_dump()
    data["facts"]["building"]["transfer"].update(value=0.7, trusted=True, origin="extracted")
    with pytest.raises(ValidationError, match="reviewer evidence"):
        Inputs.model_validate(data)


def test_declaration_cannot_replace_existing_binding_or_give_units_to_boolean():
    context, _, raw = fixture()
    existing = Inputs(bindings={"transfer": {"kind": "number", "unit": "W/m2/K"}})
    with pytest.raises(SlotFailure, match="replace an existing"):
        compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(existing, None))
    raw["fact_declarations"][0]["kind"] = "boolean"
    with pytest.raises(ValidationError, match="only numbers"):
        SlotDraft.model_validate(raw)


def test_new_declaration_requires_evidence_before_any_decisive_verdict():
    context, _, raw = fixture()
    text = context.text + " Approval must be recorded."
    context = ContextBundle(document="synthetic", text=text, target="r",
                            clauses=[Clause("r", "", text, 0, 0, len(text))])
    raw["sources"][0]["quote"] = raw["fact_declarations"][0]["source"]["quote"] = text
    raw["nodes"] += [{"id": "approval", "op": "fact", "entity": "building", "name": "approval"},
                     {"id": "both", "op": "all", "args": ["comparison", "approval"]}]
    raw["requirement"] = "both"
    inputs = Inputs.model_validate({"bindings": {"approval": {"kind": "boolean", "description": "recorded approval"}},
                                    "facts": {"building": {"approval": {"value": False, "trusted": True,
                                                                         "source": "Synthetic observation"}}}})
    program = compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    assert run_program(program, inputs, include_drafts=True)["outcome"] == "UNRESOLVED"


def test_declarations_do_not_make_an_incomplete_inventory_complete():
    context, _, raw = fixture()
    text = "Each panel shall have heat transfer at most 0.8 W/m²/K."
    context = ContextBundle(document="synthetic", text=text, target="r",
                            clauses=[Clause("r", "", text, 0, 0, len(text))])
    raw["subject"] = "panel"
    raw["sources"][0]["quote"] = raw["fact_declarations"][0]["source"]["quote"] = text
    raw["fact_declarations"][0]["entity"] = "panels"
    raw["nodes"][0]["entity"] = "$p"
    raw["nodes"].append({"id": "every", "op": "forall", "collection": "panels", "variable": "$p", "body": "comparison"})
    raw["requirement"] = "every"
    inputs = Inputs.model_validate({"bindings": {}, "collections": {
        "panels": {"items": ["p1", "p2"], "complete": False, "trusted": True}}})
    program = compile_slots(SlotDraft.model_validate(raw), context, catalogue_from(inputs, None))
    declared = apply_declarations(inputs, program.fact_declarations)
    observed = apply_evidence(declared, [EvidenceEntry(
        entity=entity, fact="transfer", value=value, unit="W/m2/K", origin="reviewer-attested",
        source="Synthetic certificate", reviewer="Synthetic reviewer", trusted=True)
        for entity, value in [("p1", 0.9), ("p2", 0.7)]])
    assert not observed.collections["panels"].complete
    assert run_program(program, observed, include_drafts=True)["outcome"] == "VIOLATED"
