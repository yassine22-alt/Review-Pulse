"""Server-timed reviewer sessions. Test/assistant events never become observed human effort."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime
from statistics import median

from ..interpreter.checked import catalogue_from
from ..interpreter.schema import Program
from ..interpreter.structured import SlotDraft, compile_slots, slot_schema, slots_from_program
from . import interpret
from .store import replace


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def diff(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        return [change for key in sorted(set(before) | set(after))
                for change in diff(before.get(key), after.get(key), path + "/" + key)]
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [change for i, (left, right) in enumerate(zip(before, after))
                for change in diff(left, right, path + "/" + str(i))]
    return [] if before == after else [{"path": path or "/", "before": before, "after": after}]


def _load(store, pid):
    path = store.drafts_dir(pid) / "assisted-effort.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(store, pid, sessions):
    path = store.drafts_dir(pid) / "assisted-effort.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sessions, indent=2) + "\n", encoding="utf-8")
    replace(tmp, path)


def start(store, pid, clause, reviewer, actor_type="human"):
    if not reviewer.strip() or actor_type not in ("human", "assistant", "test"):
        raise ValueError("reviewer name and valid actor type required")
    with interpret._lock(pid):
        _, entry = interpret._entry(store, pid, clause)
        context = interpret._context(store, pid, clause)
        program = entry.get("program")
        subject = entry.get("slots", {}).get("subject") or next(c.text for c in context.clauses if c.id == clause)
        slots = slots_from_program(Program.model_validate(program), subject) if program else None
        session = {"id": uuid.uuid4().hex, "clause": clause, "reviewer": reviewer.strip(), "actor_type": actor_type,
            "queue": entry.get("queue", "in_scope_draft" if program else "reviewer_formalization"),
            "source_fingerprint": fingerprint(context.model_dump(mode="json")), "draft_fingerprint": fingerprint(program),
            "before": slots, "elapsed_seconds": 0.0, "running_since": time.time(),
            "started_at": datetime.now(UTC).isoformat(), "status": "ACTIVE", "attempts": []}
        sessions = _load(store, pid)
        sessions[session["id"]] = session
        _save(store, pid, sessions)
        _, inputs, _ = interpret._plan(store, pid)
        catalogue = catalogue_from(inputs, None)
        return session | {"catalogue": catalogue, "editor_schema": slot_schema(catalogue, context), "context": context.model_dump(mode="json")}


def _tick(session):
    if session["running_since"] is not None:
        session["elapsed_seconds"] += max(0, time.time() - session["running_since"])
        session["running_since"] = time.time()


def pause(store, pid, session_id, paused):
    with interpret._lock(pid):
        sessions = _load(store, pid)
        session = sessions[session_id]
        if session["status"] != "ACTIVE":
            raise ValueError("session already finished")
        _tick(session)
        session["running_since"] = None if paused else time.time()
        _save(store, pid, sessions)
        return session


def save(store, pid, session_id, text, input_events):
    with interpret._lock(pid):
        sessions = _load(store, pid)
        session = sessions[session_id]
        if session["status"] != "ACTIVE":
            raise ValueError("session already finished")
        if session["running_since"] is None:
            raise ValueError("resume the timer before saving")
        context = interpret._context(store, pid, session["clause"])
        results, entry = interpret._entry(store, pid, session["clause"])
        if (session["source_fingerprint"] != fingerprint(context.model_dump(mode="json"))
                or session["draft_fingerprint"] != fingerprint(entry.get("program"))):
            raise ValueError("source or draft changed; start a new session")
        _tick(session)
        attempt = {"text": text, "elapsed_seconds": session["elapsed_seconds"], "input_events": input_events}
        try:
            slots = SlotDraft.model_validate_json(text)
            _, inputs, graph = interpret._plan(store, pid)
            program = compile_slots(slots, context, catalogue_from(inputs, None))
        except ValueError as error:
            attempt.update(status="VALIDATION_REJECTED", reason=str(error))
            session["attempts"].append(attempt)
            _save(store, pid, sessions)
            return {"saved": False, "session": session, "reason": str(error)}
        after = slots.model_dump(mode="json")
        session.update(status="COMPLETED", after=after, diff=diff(session["before"], after), running_since=None,
                       input_events=input_events, finished_at=datetime.now(UTC).isoformat())
        session["attempts"].append(attempt | {"status": "VALIDATED"})
        entry.update(program=program.model_copy(update={"id": interpret.rule_id(session["clause"])}).model_dump(mode="json"),
                     slots=after, status="DRAFTED", formalized_by=session["reviewer"], arm="assisted")
        for key in ("review", "decision", "approved_program", "preview"):
            entry.pop(key, None)
        from ..interpreter.runtime import run_program
        preview = run_program(program, inputs, include_drafts=True, graph=graph)
        entry["preview"] = {"outcome": preview["outcome"], "missing": preview["trace"].get("missing", [])}
        from ..xeval.readback import plain
        entry["readback"] = plain(program.requirement.model_dump(), {n:b.model_dump() for n,b in inputs.bindings.items()})
        session["saved_program_fingerprint"] = fingerprint(entry["program"])
        interpret._save(store, pid, results)
        _save(store, pid, sessions)
        return {"saved": True, "session": session, "entry": entry}


def approve(store, pid, clause, reviewer, acknowledge):
    if not reviewer.strip() or not acknowledge:
        raise ValueError("named reviewer must confirm source meaning, units, ownership and applicability")
    with interpret._lock(pid):
        results, entry = interpret._entry(store, pid, clause)
        if entry.get("arm") != "assisted" or not entry.get("program"):
            raise ValueError("no validated assisted rule to approve")
        matching = [s for s in _load(store, pid).values() if s["status"] == "COMPLETED"
                    and s["clause"] == clause and s["reviewer"] == reviewer.strip()
                    and s.get("saved_program_fingerprint") == fingerprint(entry["program"])]
        if not matching:
            raise ValueError("complete and save a timed review of this draft before approval")
        context = interpret._context(store, pid, clause)
        _, inputs, _ = interpret._plan(store, pid)
        subject = entry.get("slots", {}).get("subject") or next(c.text for c in context.clauses if c.id == clause)
        slots = slots_from_program(Program.model_validate(entry["program"]), subject)
        program = compile_slots(SlotDraft.model_validate(slots), context, catalogue_from(inputs, None))
        if program.unresolved or context.missing:
            raise ValueError("resolve interpretation/context dependencies before approval")
        entry.update(approved_program=program.model_copy(update={"status":"approved", "approved_by":reviewer.strip(),
            "id":interpret.rule_id(clause)}).model_dump(mode="json"), decision={"state":"approved", "by":reviewer.strip(),
            "at":datetime.now(UTC).isoformat(), "note":"Explicit assisted source-meaning attestation; no model approval"})
        interpret._save(store, pid, results)
        return entry


def report(store, pid):
    sessions = list(_load(store, pid).values())
    observed = [s for s in sessions if s["actor_type"] == "human" and s["status"] == "COMPLETED"]
    groups = {queue: [s for s in observed if s["queue"] == queue]
              for queue in ("in_scope_draft", "reviewer_formalization")}
    summary = {queue: {"completed_sessions":len(rows), "seconds":sum(s["elapsed_seconds"] for s in rows),
                      "median_seconds":median(s["elapsed_seconds"] for s in rows) if rows else None,
                      "changed_sites":[len(s["diff"]) for s in rows],
                      "input_events":[s["input_events"] for s in rows]} for queue, rows in groups.items()}
    return {"summary": summary, "observed_sessions":len(observed), "distinct_clauses":len({s["clause"] for s in observed}),
        "rows":observed, "groups":{queue:[s for s in observed if s["queue"]==queue] for queue in ("in_scope_draft","reviewer_formalization")},
        "excluded_sessions":len(sessions)-len(observed),
        "limits":"Server elapsed wall time excludes explicit pauses, includes reading and idle time. Reviewer identity is self-reported. Diff sites and input events are not semantic edit grades. Assistant/test/open sessions excluded. No observed effort until people complete sessions."}
