from reviewpulse.interpreter.agreement import agreement_gate, semantic_key
from reviewpulse.interpreter.schema import Program


def proposal(model, requirement):
    program = Program.model_validate({"id": "x", "title": "x", "document": "source",
        "sources": [{"clause": "x", "start": 0, "end": 1, "quote": "x"}], "requirement": requirement})
    return {"model": model, "retained": True, "raw": {"subject": "source subject"},
            "program": program.model_dump(mode="json")}


def comparison(name, value, unit="m"):
    return {"node": "ge", "left": {"node": "fact", "entity": "building", "name": name},
            "right": {"node": "literal", "value": value, "unit": unit}}


def test_agreement_preserves_associations_not_only_field_sets():
    left = proposal("first", {"node": "all", "args": [comparison("width", 3), comparison("depth", 4)]})
    right = proposal("second", {"node": "all", "args": [comparison("width", 4), comparison("depth", 3)]})
    assert agreement_gate(left, right)["status"] == "NEEDS_REVIEW"


def test_equivalent_units_and_conjunction_order_agree_but_never_approve():
    left = proposal("first", {"node": "all", "args": [comparison("width", 3), comparison("depth", 4)]})
    right = proposal("second", {"node": "all", "args": [comparison("depth", 400, "cm"), comparison("width", 300, "cm")]})
    result = agreement_gate(left, right)
    assert result["status"] == "CANDIDATE" and result["approved"] is False


def test_same_model_and_failed_draft_cannot_supply_independent_agreement():
    left = proposal("same", comparison("width", 3))
    assert agreement_gate(left, left)["status"] == "NEEDS_REVIEW"
    assert agreement_gate(left, {"model": "other", "retained": False})["status"] == "NEEDS_REVIEW"


def test_exemption_difference_prevents_agreement():
    left = proposal("first", comparison("width", 3))
    right = proposal("second", comparison("width", 3))
    right["program"]["exemption"] = {"node": "literal", "value": True}
    assert semantic_key(Program.model_validate(left["program"])) != semantic_key(Program.model_validate(right["program"]))


def test_boolean_fact_and_equality_to_true_have_the_same_meaning():
    fact = {"node": "fact", "entity": "building", "name": "two_way"}
    left = proposal("first", fact)
    right = proposal("second", {"node": "eq", "left": fact, "right": {"node": "literal", "value": True}})
    assert agreement_gate(left, right)["status"] == "CANDIDATE"
