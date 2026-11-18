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
