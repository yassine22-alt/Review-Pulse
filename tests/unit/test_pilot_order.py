from scripts import continue_free_quota as worker


def plan_and_summary(tmp_path):
    cases, order = tmp_path / "cases.json", tmp_path / "order.json"
    worker.write(cases, {"cases": [{"id": key} for key in ("alpha", "beta", "gamma")]})
    worker.write(order, {"phases": [
        {"name": "first", "ids": ["beta", "alpha"], "pause_if_zero_retained": True},
        {"name": "rest", "remaining": True}]})
    plan = {"case_manifest": str(cases), "phase_manifest": str(order), "run_directory": str(tmp_path),
            "model": "fixed-model", "arms": {name: {"code_fingerprint": name} for name in ("original", "structured")}}
    summary = {name: {"completed_ids": ["alpha", "beta"], "retained_ids": []} for name in plan["arms"]}
    return plan, summary


def test_phase_order_is_data_and_remaining_ids_are_not_lost(tmp_path):
    plan, _ = plan_and_summary(tmp_path)
    assert [phase["ids"] for phase in worker.phases(plan)] == [["beta", "alpha"], ["gamma"]]


def test_zero_retention_gate_waits_for_both_arms_and_needs_a_bound_diagnosis(tmp_path):
    plan, summary = plan_and_summary(tmp_path)
    summary["structured"]["completed_ids"] = ["alpha"]
    assert worker.next_phase(plan, summary)[1] is None
    summary["structured"]["completed_ids"].append("beta")
    assert worker.next_phase(plan, summary)[1] == "WAITING_FOR_DIAGNOSIS"
    worker.write(tmp_path / "first.diagnosis.json", {
        "model": "fixed-model", "phase": "first", "continue": True,
        "code_fingerprints": {name: name for name in plan["arms"]},
        "diagnosis": "Completed terminal stages reviewed; this is not an accuracy claim."})
    phase, blocker = worker.next_phase(plan, summary)
    assert phase["ids"] == ["gamma"] and blocker is None


def test_some_retention_does_not_trigger_zero_retention_pause(tmp_path):
    plan, summary = plan_and_summary(tmp_path)
    summary["original"]["retained_ids"] = ["alpha"]
    assert worker.next_phase(plan, summary)[0]["name"] == "rest"
