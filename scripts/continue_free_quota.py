"""Continue one frozen development comparison within a daily free-quota allowance.

This performs drafting work, not approvals or held-out evaluation. All clocks
and allowances are operational configuration, independent of rule thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path


class GuardFailure(Exception):
    """Only fixed diagnostic codes are persisted; arbitrary exceptions are not."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def window_start(now, reset_hour):
    start = now.astimezone(UTC).replace(hour=reset_hour, minute=0, second=0, microsecond=0)
    return start if now >= start else start - timedelta(days=1)


def requests_in(report):
    return sum(len(batch.get("events", [])) for batch in report.get("batches", []))


def used_requests(plan, journal, window):
    prior = plan.get("prior_usage", {}).get(window, 0)
    prior += sum(requests_in(read(item["report"])) for item in plan["prior_reports"]
                 if item["window"] == window)
    return prior + sum(item["charged"] for item in journal["runs"]
                       if window in item.get("charge_windows", [item["window"]]))


def phases(plan):
    ids = [item["id"] for item in read(plan["case_manifest"])["cases"]]
    if not plan.get("phase_manifest"):
        return [{"name": "all", "ids": ids}]
    result, seen, names = [], set(), set()
    for phase in read(plan["phase_manifest"])["phases"]:
        name = phase["name"]
        selected = [key for key in ids if key not in seen] if phase.get("remaining") else phase["ids"]
        if (not name.isidentifier() or name in names or not selected or
                len(set(selected)) != len(selected) or set(selected) - set(ids) or seen & set(selected)):
            raise GuardFailure("INVALID_PHASE_ORDER")
        result.append({**phase, "ids": selected})
        seen.update(selected)
        names.add(name)
    if seen != set(ids):
        raise GuardFailure("INCOMPLETE_PHASE_ORDER")
    return result


def next_phase(plan, summary):
    for phase in phases(plan):
        selected = set(phase["ids"])
        complete = all(selected <= set(arm["completed_ids"]) for arm in summary.values())
        if not complete:
            return phase, None
        if phase.get("pause_if_zero_retained") and not any(
            selected & set(arm["retained_ids"]) for arm in summary.values()
        ):
            checkpoint = Path(plan["run_directory"]) / f"{phase['name']}.diagnosis.json"
            expected = {"model": plan["model"], "phase": phase["name"],
                        "code_fingerprints": {name: arm["code_fingerprint"] for name, arm in plan["arms"].items()}}
            reviewed = read(checkpoint) if checkpoint.exists() else {}
            if (any(reviewed.get(key) != value for key, value in expected.items()) or
                    reviewed.get("continue") is not True or not reviewed.get("diagnosis")):
                return phase, "WAITING_FOR_DIAGNOSIS"
    return None, None


def progress(plan, journal):
    ids = {item["id"] for item in read(plan["case_manifest"])["cases"]}
    found = {arm: {} for arm in plan["arms"]}
    records = list(plan["prior_reports"]) + journal["runs"]
    for entry in records:
        path = Path(entry["report"])
        if not path.exists():
            continue
        report = read(path)
        arm = entry["arm"]
        if any(report.get(key) != value for key, value in {
            "model": plan["model"], "code_fingerprint": plan["arms"][arm]["code_fingerprint"],
            "max_tokens": plan["max_tokens"], "timeout": plan["timeout"],
        }.items()):
            raise GuardFailure("MODEL_CODE_OR_SETTINGS_CHANGED")
        selected = set(report.get("selected_ids", ids))
        if not selected <= ids:
            raise GuardFailure("UNEXPECTED_SELECTION")
        if report.get("status") == "COMPLETE" and {
            row["id"] for row in report.get("results", []) if row["status"] != "API_UNAVAILABLE"
        } != selected:
            raise GuardFailure("INCOMPLETE_COMPLETED_REPORT")
        for row in report.get("results", []):
            if row["id"] not in ids:
                raise GuardFailure("UNEXPECTED_OBLIGATION")
            if row["status"] != "API_UNAVAILABLE":
                previous = found[arm].get(row["id"])
                # This is a duplicate-data provenance guard, not a semantic
                # equivalence score; differing completed rows require review.
                meaningful = {key: value for key, value in row.items() if key not in ("batch", "cycle")}
                if previous is not None and previous != meaningful:
                    raise GuardFailure("CONFLICTING_COMPLETED_RESULTS")
                found[arm][row["id"]] = meaningful
    return {arm: {"completed": len(rows), "planned": len(ids), "completed_ids": sorted(rows),
                  "retained_ids": sorted(key for key, row in rows.items() if row.get("program")),
                  "retained": sum(bool(row.get("program")) for row in rows.values())}
            for arm, rows in found.items()}


def verify_inputs(plan):
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != plan["worker_script_sha256"]:
        raise GuardFailure("CONTINUATION_WORKER_CHANGED")
    for field in ("pinned_repo", "original_repo"):
        directory = Path(plan[field])
        command = ["git", "-c", f"safe.directory={directory.as_posix()}", "-C", str(directory)]
        actual = subprocess.check_output(command + ["rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(command + ["status", "--porcelain", "--untracked-files=no"], text=True)
        if actual != plan[field + "_commit"] or dirty:
            raise GuardFailure("FROZEN_CHECKOUT_CHANGED")
    actual = hashlib.sha256(Path(plan["access_text"]).read_bytes()).hexdigest()
    if actual != plan["access_text_sha256"]:
        raise GuardFailure("SOURCE_TEXT_CHANGED")
    command = [plan["python"], "-c",
               "import json,platform,importlib.metadata as m; "
               "print(json.dumps({'python':platform.python_version(),"
               "'packages':{name:m.version(name) for name in " + repr(plan["runtime_packages"]) + "}}))"]
    if json.loads(subprocess.check_output(command, text=True)) != plan["runtime_signature"]:
        raise GuardFailure("FROZEN_RUNTIME_CHANGED")


@contextmanager
def exclusive(path):
    """An OS lock releases on exit or reboot; a stale file cannot block resume."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def invoke(plan, journal, journal_path, arm, window, budget, phase=None):
    directory = Path(plan["run_directory"])
    number = len(journal["runs"]) + 1
    output = directory / f"{window}-{number:03d}-{arm}.json"
    entry = {"arm": arm, "window": window, "report": str(output), "reserved": budget,
             "charged": budget, "status": "RESERVED"}
    if phase is not None:
        entry["phase"] = phase["name"]
    journal["runs"].append(entry)
    write(journal_path, journal)  # Debit first: interruption cannot create free retries.
    command = [plan["python"], "-u", str(Path(plan["pinned_repo"]) / "scripts/run_development_drafting.py"),
               plan["access_text"], str(output), "--backend", "gemini", "--model", plan["model"],
               "--max-tokens", str(plan["max_tokens"]), "--timeout", str(plan["timeout"]),
               "--batch-size", "1", "--cycles", "3", "--request-budget", str(budget),
               "--min-interval", str(plan["min_interval"]), "--cache", plan["cache"]]
    if arm == "original":
        command += ["--original-src", str(Path(plan["original_repo"]) / "src")]
    if phase is not None:
        selection = directory / f"{phase['name']}.selection.json"
        write(selection, phase["ids"])
        command += ["--case-ids", str(selection)]
    interrupted = False
    deadline = datetime.fromisoformat(window).replace(hour=plan["reset_utc_hour"], tzinfo=UTC)
    deadline += timedelta(days=1)
    with output.with_suffix(".log").open("ab") as log:
        child = subprocess.Popen(command, cwd=plan["pinned_repo"], stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            now = datetime.now(UTC)
            if (directory / "STOP").exists() or now >= deadline:
                child.terminate()
                interrupted = True
                if now >= deadline:
                    final_window = window_start(now, plan["reset_utc_hour"])
                    # Sleep or suspension can straddle a reset. Charge the full
                    # reservation to every crossed window rather than guess.
                    entry["charge_windows"] = []
                    cursor = deadline - timedelta(days=1)
                    while cursor <= final_window:
                        entry["charge_windows"].append(cursor.date().isoformat())
                        cursor += timedelta(days=1)
                break
            time.sleep(1)
        code = child.wait()
    if code != 0 or interrupted or not output.exists():
        entry["status"] = "INTERRUPTED_RESERVATION_RETAINED"
        write(journal_path, journal)
        return "STOPPED" if interrupted else "NEEDS_ATTENTION"
    report = read(output)
    actual = requests_in(report)
    if report.get("status") not in ("COMPLETE", "API_UNAVAILABLE") or actual > budget:
        raise GuardFailure("INCOMPLETE_OR_OVER_BUDGET_REPORT")
    entry.update(charged=actual, status="FINISHED")
    write(journal_path, journal)
    if report["status"] == "COMPLETE" or report.get("blocker") == "REQUEST_BUDGET_EXHAUSTED":
        return "CONTINUE"
    statuses = {event.get("http_status") for batch in report.get("batches", []) for event in batch["events"]}
    return "WAITING_FOR_QUOTA" if 429 in statuses else "NEEDS_ATTENTION"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--watch", action="store_true", help="Wait through quota resets; no system scheduler is installed")
    args = parser.parse_args()
    plan = read(args.plan)
    if not (0 <= plan["reset_utc_hour"] < 24 and
            0 < plan["minimum_start_budget"] <= plan["per_run_budget"] <= plan["daily_budget"] < plan["project_daily_limit"]):
        parser.error("invalid operational limits")
    directory = Path(plan["run_directory"])
    journal_path, state_path = directory / "journal.json", directory / "progress.json"
    with exclusive(directory / "worker.lock"):
        journal = read(journal_path) if journal_path.exists() else {"runs": []}
        last_state = None
        while True:
            now = datetime.now(UTC)
            start = window_start(now, plan["reset_utc_hour"])
            window = start.date().isoformat()
            next_reset = start + timedelta(days=1)
            summary = {"pid": os.getpid(), "model": plan["model"], "window": window,
                       "heartbeat_utc": now.isoformat(), "next_reset_utc": next_reset.isoformat()}
            try:
                verify_inputs(plan)
                summary["arms"] = progress(plan, journal)
                phase, checkpoint_status = next_phase(plan, summary["arms"]) if plan.get("phase_manifest") else (None, None)
                if phase is not None:
                    summary["phase"] = phase["name"]
                remaining = max(0, plan["daily_budget"] - used_requests(plan, journal, window))
                summary["request_allowance_remaining"] = remaining
                if now >= datetime.fromisoformat(plan["expires_utc"]):
                    status = "EXPIRED_REVIEW_REQUIRED"
                elif (directory / "STOP").exists():
                    status = "STOPPED"
                elif all(row["completed"] == row["planned"] for row in summary["arms"].values()):
                    status = "COMPLETE_DRAFTING_REVIEW_PENDING"
                elif not os.environ.get("GEMINI_API_KEY"):
                    status = "NEEDS_ENV_CREDENTIAL"
                elif checkpoint_status:
                    status = checkpoint_status
                elif (remaining < plan["minimum_start_budget"] or journal.get("defer_until") == window or
                      (next_reset - now).total_seconds() < plan["reset_guard_seconds"]):
                    status = "WAITING_FOR_QUOTA"
                else:
                    eligible = {name: row for name, row in summary["arms"].items()
                                if (set(phase["ids"]) - set(row["completed_ids"]) if phase
                                    else row["completed"] < row["planned"])}
                    arm = min(eligible, key=lambda name: len(set(eligible[name]["completed_ids"]) & set(phase["ids"]))
                              if phase else eligible[name]["completed"])
                    summary.update(status="RUNNING", arm=arm)
                    write(state_path, summary)
                    status = invoke(plan, journal, journal_path, arm, window,
                                    min(remaining, plan["per_run_budget"]), phase)
                    if status == "WAITING_FOR_QUOTA":
                        journal["defer_until"] = window
                        write(journal_path, journal)
                    if status == "CONTINUE":
                        # The child resets its own pacer. Keep a gap across
                        # children too, even if the final response was fast.
                        time.sleep(plan["min_interval"])
                        continue
            except Exception as error:
                summary["error_type"] = type(error).__name__  # Never log exception values or credentials.
                if isinstance(error, GuardFailure):
                    summary["blocker"] = error.code
                status = "NEEDS_ATTENTION"
            summary["status"] = status
            write(state_path, summary)
            if status != last_state:
                print(status, window, flush=True)
                last_state = status
            if status not in ("WAITING_FOR_QUOTA", "WAITING_FOR_DIAGNOSIS") or not args.watch:
                return
            time.sleep(min(60, max(1, (next_reset - datetime.now(UTC)).total_seconds())))


if __name__ == "__main__":
    main()
