import importlib.util
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("slot_pilot", SCRIPT_DIR / "run_slot_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_partial_or_unavailable_thermal_samples_cannot_trigger_a_decision():
    scores = {slot: {"eligible": True, "exact": False, "matched_atoms": 0,
                     "gold_atoms": 1, "predicted_atoms": 0} for slot in pilot.SLOTS}
    rows = [{"id": "a", "arm": "structured", "status": "NEEDS_REVIEW", "slots": scores},
            {"id": "b", "arm": "structured", "status": "API_UNAVAILABLE"}]
    report = pilot.summarize(rows, ["a", "b"], ["a", "b"])
    assert report["decision"]["status"] == "NOT_YET_MEASURED"
    assert report["arms"]["structured"]["completed"] == [1, 2]
    assert report["arms"]["structured"]["slot_scores"]["subject"]["denominator"] == 1


def test_threshold_uses_raw_slots_even_when_no_rule_is_retained():
    scores = {slot: {"eligible": True, "exact": slot != "subject", "matched_atoms": 1,
                     "gold_atoms": 1, "predicted_atoms": 1} for slot in pilot.SLOTS}
    rows = [{"id": "a", "arm": "structured", "status": "NEEDS_REVIEW", "slots": scores}]
    report = pilot.summarize(rows, ["a"], ["a"])
    assert report["decision"]["correct_slots"] == [6, 7]
    assert report["decision"]["status"] == "PROPOSE_NEXT_MEASUREMENT"
    assert report["arms"]["structured"]["retained"] == [0, 1]


def test_rejected_request_is_not_a_model_failure_or_completed_case():
    rows = [{"id": "a", "arm": "structured", "status": "REQUEST_REJECTED"}]
    report = pilot.summarize(rows, ["a"], ["a"])
    assert report["arms"]["structured"]["completed"] == [0, 1]
    assert report["decision"]["correct_slots"] == [0, 0]


def test_expression_interface_uses_the_same_metadata_and_requirement_gate():
    from test_project_metadata import scoped_rule

    context, inputs, slots = scoped_rule()
    raw = {"title": "Capacity", "subject": slots["subject"], "require": "building.capacity >= 6 count",
           "applies_when": None, "unless": None, "sources": slots["sources"], "unresolved": [],
           "metadata_applicability": slots["metadata_applicability"], "fact_declarations": []}
    case = {"context": context, "inputs": inputs, "graph": None}
    program = pilot.compile_response(raw, case, pilot.catalogue_from(inputs, None), "original_expression")
    assert program.requirement.node == "ge" and program.requirement.right.value == 6
    assert len(program.metadata_applicability) == 2


def test_hosted_payload_contains_no_project_observations_or_gold_labels():
    from test_project_metadata import scoped_rule

    context, inputs, _ = scoped_rule()
    data = inputs.model_dump()
    data["project_metadata"] = {"occupancy": {"value": 867, "trusted": True,
                                             "source": "private project citation", "unit": "count"}}
    case = {"context": context, "inputs": type(inputs).model_validate(data), "graph": None}
    for arm in ("structured", "original_expression"):
        _, payload, _, _ = pilot.request_for(case, arm)
        serialized = pilot.json.dumps(payload)
        assert "867" not in serialized and "private project citation" not in serialized
        assert "frozen_reading" not in serialized and "reference_expression" not in serialized
