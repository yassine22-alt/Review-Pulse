"""The checklist benchmark scores a rule by its numbers and facts, never by wording."""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("checklist_benchmark", SCRIPTS / "checklist_benchmark.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

HALL = {"numbers": [0.9144], "facts_all": ["min_width_m"]}


def test_right_rule_is_right():
    assert bench.judge(HALL, "forall rooms v where v.room_type == 'corridor': v.min_width_m >= 0.9144 m")[0]


def test_wrong_number_fact_or_extra_number_is_wrong():
    assert not bench.judge(HALL, "forall rooms v: v.min_width_m >= 0.8 m")[0]
    assert not bench.judge(HALL, "forall rooms v: v.width_m >= 0.9144 m")[0]
    assert not bench.judge(HALL, "forall rooms v: v.min_width_m >= 0.9144 m and v.area_m2 >= 7.5 m2")[0]


def test_digits_in_fact_names_are_not_numbers():
    assert bench.judge({"numbers": [6.5], "facts_all": ["area_m2"]}, "v.area_m2 >= 6.5 m2")[0]


def test_every_label_has_a_known_kind():
    import json

    labels = json.loads(bench.LABELS.read_text(encoding="utf-8"))
    kinds = {x["label"] for d in labels.values() for x in d.values()}
    assert kinds <= {"rule_now", "needs_fact", "not_plan", "bundle"}
