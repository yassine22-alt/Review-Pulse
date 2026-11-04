"""I5: a correct rule is approved, a deliberately wrong one is refused by its own test."""

import yaml

from reviewpulse.rules.review import approve, selftest
from reviewpulse.rules.schema import Rule

BASE = {"id": "D-door", "title": "Door width", "family": "C", "class": "threshold",
        "applies_to": {"element": "door"}, "check": {"fn": "width_m", "op": ">=", "value": 0.80, "unit": "m"},
        "severity": "major", "needs": [], "source": {"doc": "d", "clause": "Art. 6.1"},
        "message": "{detected} / {required}", "status": "draft"}


def test_correct_rule_passes_selftest_and_is_written(tmp_path):
    ok, msg = approve(BASE, tmp_path, "tester")
    assert ok, msg
    saved = yaml.safe_load((tmp_path / "D-door.yaml").read_text())
    assert saved["status"] == "approved" and saved["approved_by"] == "tester"
    ok2, _ = approve(BASE, tmp_path, "tester")
    assert ok2 and yaml.safe_load((tmp_path / "D-door.yaml").read_text())["version"] == 2


def test_deliberately_wrong_rule_is_refused(tmp_path):
    wrong = dict(BASE, id="D-wrong", applies_to={"element": "window"},
                 check={"fn": "area_m2", "op": ">=", "value": 9.0, "unit": "m2"})
    # area_m2 is a room function: applied to windows it selects no room -> untested, not approved silently
    r = Rule.model_validate(wrong)
    assert selftest(r).status in ("untested", "failing")
    ok, msg = approve(wrong, tmp_path, "tester", force_untested=False)
    assert not ok and "self-test" in msg
    assert not (tmp_path / "D-wrong.yaml").exists()


def test_upper_bound_rule_selftest_flips():
    upper = dict(BASE, id="D-max", check={"fn": "width_m", "op": "<=", "value": 1.20, "unit": "m"})
    st = selftest(Rule.model_validate(upper))
    assert st.status == "ok", st.detail


def test_area_rule_is_approvable_and_incomplete_threshold_is_refused(tmp_path):
    # the self-test probes outside the 5 % area band, so a correct area rule passes
    living = dict(BASE, id="D-living", applies_to={"room_type": ["living"]},
                  check={"fn": "area_m2", "op": ">=", "value": 14.0, "unit": "m2"})
    assert selftest(Rule.model_validate(living)).status == "ok"
    # a threshold without a limit is refused with the reason, not a crash
    ok, msg = approve(dict(BASE, id="D-nolimit", check={"fn": "width_m"}), tmp_path, "tester")
    assert not ok and "check.value" in msg and not (tmp_path / "D-nolimit.yaml").exists()
