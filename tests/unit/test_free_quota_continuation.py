import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import continue_free_quota as worker


@pytest.mark.parametrize("stamp,expected", [
    ("2026-11-18T07:59:59+00:00", "2026-11-17"),
    ("2026-11-18T08:00:00+00:00", "2026-11-18"),
])
def test_quota_window_changes_at_configured_provider_reset(stamp, expected):
    assert worker.window_start(datetime.fromisoformat(stamp), 8).date().isoformat() == expected


def test_used_allowance_includes_prior_calls_and_unreconciled_reservations(tmp_path):
    report = tmp_path / "prior.json"
    worker.write(report, {"batches": [{"events": [{}, {}]}]})
    plan = {"prior_usage": {"window": 3}, "prior_reports": [{"window": "window", "report": str(report)}]}
    journal = {"runs": [{"window": "window", "charged": 7}, {"window": "another", "charged": 9}]}
    assert worker.used_requests(plan, journal, "window") == 12


def setup_progress(tmp_path):
    manifest, report = tmp_path / "cases.json", tmp_path / "report.json"
    worker.write(manifest, {"cases": [{"id": "sample"}]})
    worker.write(report, {"model": "fixed-model", "code_fingerprint": "fixed-code",
                          "max_tokens": 100, "timeout": 10,
                          "results": [{"id": "sample", "status": "UNRESOLVED", "program": None}]})
    plan = {"case_manifest": str(manifest), "model": "fixed-model", "max_tokens": 100, "timeout": 10,
            "arms": {"original": {"code_fingerprint": "fixed-code"}},
            "prior_reports": [{"arm": "original", "report": str(report)}]}
    return plan, report


def test_progress_counts_completed_unresolved_without_calling_it_a_retained_rule(tmp_path):
    plan, _ = setup_progress(tmp_path)
    assert worker.progress(plan, {"runs": []}) == {"original": {"completed": 1, "planned": 1, "retained": 0}}


def test_progress_refuses_a_different_model_or_conflicting_results(tmp_path):
    plan, report = setup_progress(tmp_path)
    changed = worker.read(report)
    changed["model"] = "another-model"
    worker.write(report, changed)
    with pytest.raises(worker.GuardFailure, match="MODEL_CODE_OR_SETTINGS_CHANGED"):
        worker.progress(plan, {"runs": []})
    changed["model"] = "fixed-model"
    worker.write(report, changed)
    alternate = tmp_path / "alternate.json"
    changed["results"][0]["reason"] = "different result"
    worker.write(alternate, changed)
    with pytest.raises(worker.GuardFailure, match="CONFLICTING_COMPLETED_RESULTS"):
        worker.progress(plan, {"runs": [{"arm": "original", "report": str(alternate)}]})


def test_frozen_source_and_runtime_changes_refuse_execution(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    plan = {"pinned_repo": str(tmp_path / "pinned"), "original_repo": str(tmp_path / "original"),
            "pinned_repo_commit": "fixed", "original_repo_commit": "fixed", "access_text": str(source),
            "access_text_sha256": "wrong", "python": "python", "runtime_packages": [],
            "runtime_signature": {"python": "fixed", "packages": {}}}
    plan["worker_script_sha256"] = hashlib.sha256(Path(worker.__file__).read_bytes()).hexdigest()
    monkeypatch.setattr(worker.subprocess, "check_output", lambda command, **_: "fixed" if command[-1] == "HEAD" else "")
    with pytest.raises(worker.GuardFailure, match="SOURCE_TEXT_CHANGED"):
        worker.verify_inputs(plan)
    plan["access_text_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    original = worker.subprocess.check_output
    monkeypatch.setattr(worker.subprocess, "check_output", lambda command, **kwargs:
                        json.dumps({}) if command[0] == "python" else original(command, **kwargs))
    with pytest.raises(worker.GuardFailure, match="FROZEN_RUNTIME_CHANGED"):
        worker.verify_inputs(plan)


def invoke_plan(tmp_path):
    return {"run_directory": str(tmp_path), "python": "python", "pinned_repo": str(tmp_path),
            "original_repo": str(tmp_path), "access_text": "source", "model": "fixed-model",
            "max_tokens": 100, "timeout": 10, "min_interval": 13, "cache": str(tmp_path / "cache"),
            "reset_utc_hour": 8}


@pytest.mark.parametrize("exit_code,charged,status", [(0, 2, "CONTINUE"), (1, 7, "NEEDS_ATTENTION")])
def test_reservation_is_written_before_calls_and_only_refunded_on_clean_exit(tmp_path, monkeypatch, exit_code, charged, status):
    journal, journal_path = {"runs": []}, tmp_path / "journal.json"

    class Child:
        def __init__(self, command, **_):
            assert worker.read(journal_path)["runs"][0]["charged"] == 7
            worker.write(command[4], {"status": "API_UNAVAILABLE", "blocker": "REQUEST_BUDGET_EXHAUSTED",
                                      "batches": [{"events": [{}, {}]}]})

        def poll(self):
            return exit_code

        def wait(self):
            return exit_code

    monkeypatch.setattr(worker.subprocess, "Popen", Child)
    assert worker.invoke(invoke_plan(tmp_path), journal, journal_path, "original", "2026-11-18", 7) == status
    assert journal["runs"][0]["charged"] == charged


def test_crossing_reset_keeps_full_reservation_in_both_windows(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 19, 8, 1, tzinfo=UTC)

    class Child:
        def __init__(self, *args, **kwargs):
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self):
            assert self.terminated
            return 1

    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(worker.subprocess, "Popen", Child)
    journal = {"runs": []}
    plan = invoke_plan(tmp_path) | {"prior_reports": []}
    assert worker.invoke(plan, journal, tmp_path / "journal.json", "original", "2026-11-18", 7) == "STOPPED"
    assert worker.used_requests(plan, journal, "2026-11-18") == 7
    assert worker.used_requests(plan, journal, "2026-11-19") == 7


def test_atomic_progress_file_is_valid_json(tmp_path):
    path = Path(tmp_path) / "progress.json"
    worker.write(path, {"status": "WAITING_FOR_QUOTA"})
    assert worker.read(path)["status"] == "WAITING_FOR_QUOTA"
    assert not list(tmp_path.glob("*.tmp"))


def test_another_worker_cannot_take_the_same_lock(tmp_path):
    with worker.exclusive(tmp_path / "worker.lock"), pytest.raises(OSError), worker.exclusive(tmp_path / "worker.lock"):
        pass


def test_zero_remaining_allowance_writes_wait_state_without_starting_a_child(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 18, 0, 30, tzinfo=UTC)

    plan = {"reset_utc_hour": 8, "minimum_start_budget": 3, "per_run_budget": 9,
            "daily_budget": 19, "project_daily_limit": 20, "run_directory": str(tmp_path),
            "prior_usage": {"2026-11-17": 19}, "prior_reports": [], "model": "fixed-model",
            "reset_guard_seconds": 3600, "expires_utc": "2026-12-18T08:00:00+00:00"}
    path = tmp_path / "plan.json"
    worker.write(path, plan)
    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(worker, "verify_inputs", lambda _: None)
    monkeypatch.setattr(worker, "progress", lambda *_: {"original": {"completed": 2, "planned": 46}})
    monkeypatch.setattr(worker, "invoke", lambda *args: pytest.fail("zero quota must not start a child"))
    monkeypatch.setenv("GEMINI_API_KEY", "temporary-test-credential")
    monkeypatch.setattr("sys.argv", ["worker", str(path)])
    worker.main()
    state = worker.read(tmp_path / "progress.json")
    assert state["status"] == "WAITING_FOR_QUOTA"
    assert state["next_reset_utc"] == "2026-11-18T08:00:00+00:00"


def test_pacing_is_preserved_between_child_invocations(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 18, 9, tzinfo=UTC)

    completed, sleeps = [0], []
    plan = {"reset_utc_hour": 8, "minimum_start_budget": 3, "per_run_budget": 9,
            "daily_budget": 19, "project_daily_limit": 20, "run_directory": str(tmp_path),
            "prior_usage": {}, "prior_reports": [], "model": "fixed-model", "min_interval": 13,
            "reset_guard_seconds": 3600, "expires_utc": "2026-12-18T08:00:00+00:00"}
    path = tmp_path / "plan.json"
    worker.write(path, plan)

    def invoke(*args):
        completed[0] = 1
        return "CONTINUE"

    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(worker, "verify_inputs", lambda _: None)
    monkeypatch.setattr(worker, "progress", lambda *_: {"original": {"completed": completed[0], "planned": 1}})
    monkeypatch.setattr(worker, "invoke", invoke)
    monkeypatch.setattr(worker.time, "sleep", sleeps.append)
    monkeypatch.setenv("GEMINI_API_KEY", "temporary-test-credential")
    monkeypatch.setattr("sys.argv", ["worker", str(path)])
    worker.main()
    assert sleeps == [13]
    assert worker.read(tmp_path / "progress.json")["status"] == "COMPLETE_DRAFTING_REVIEW_PENDING"
