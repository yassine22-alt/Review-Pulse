"""Requirement clauses interpreted against the project's own plan: a checked rule, or UNRESOLVED with a reason.

For each clause the drafting model writes a one-line expression, code builds the rule, the rule is checked against the
clause and against the plan's declared facts, and a preview of the result on this plan is attached. Nothing here is
approved: approval stays with the interpreter's named-reviewer flow.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import datetime

from ..factgraph.convert import to_graph, to_inputs
from ..factgraph.from_building import from_building
from ..interpreter.checked import checked_draft
from ..interpreter.context import assemble_context
from ..interpreter.review import ReviewArtifact, approve_program, review_program
from ..interpreter.runtime import run_program
from ..interpreter.schema import Program
from ..rules.clauses import split_document
from ..schema import BuildingModel
from .store import Store, replace

SKIP_KINDS = {"heading"}


def rule_id(clause_id: str) -> str:
    """A rule is named after its clause, so a finding, an approval and a report line all point at the same thing."""
    return "I-" + "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in clause_id)


def _file(store: Store, pid: str):
    return store.drafts_dir(pid) / "interpreted.json"


def load_results(store: Store, pid: str) -> dict:
    f = _file(store, pid)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(pid: str) -> threading.RLock:
    """One writer at a time per project: a reviewer approving a rule while the whole document is being read must not
    lose either change."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(pid, threading.RLock())


def _save(store: Store, pid: str, results: dict) -> None:
    f = _file(store, pid)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    replace(tmp, f)                       # a crash can never leave a half-written file


def document(store: Store, pid: str) -> dict:
    """The requirement text with its clauses, for showing next to what was extracted."""
    p = store.get(pid)
    path = store.req_path(p)
    if path is None or not path.exists():
        raise ValueError("upload a requirement document first")
    full, clauses = split_document(path)
    return {"name": path.name, "text": full,
            "clauses": [{"id": c.id, "heading": c.heading, "text": c.text, "kind": c.kind, "start": c.start, "end": c.end}
                        for c in clauses if c.kind not in SKIP_KINDS and len(c.text.strip()) > 15]}


def _plan(store: Store, pid: str):
    run = store.run_dir(pid)
    files = sorted(run.glob("building_*.json"))
    if not files:
        raise ValueError("upload and analyse a plan first")
    model = BuildingModel.model_validate_json(files[0].read_text(encoding="utf-8"))
    graph = from_building(model, complete=False)
    return graph, to_inputs(graph), to_graph(graph)


def interpret_clause(store: Store, pid: str, clause_id: str, llm_factory: Callable[[], object | None]) -> dict:
    p = store.get(pid)
    path = store.req_path(p)
    if path is None or not path.exists():
        raise ValueError("upload a requirement document first")
    client = llm_factory()
    if client is None:
        raise ValueError("the drafting model is not available")
    full, clauses = split_document(path)
    context = assemble_context(path.name, full, clauses, clause_id)
    graph, inputs, route_graph = _plan(store, pid)
    out = checked_draft(context, inputs, graph, client)
    out["clause"] = clause_id
    if out["program"] is not None:
        out["program"]["id"] = rule_id(clause_id)
        result = run_program(Program.model_validate(out["program"]), inputs, include_drafts=True, graph=route_graph)
        out["preview"] = {"outcome": result["outcome"], "missing": result["trace"].get("missing", [])[:5]}
    with _lock(pid):
        results = load_results(store, pid)
        results[clause_id] = out            # a new reading replaces the old rule, its review and its decision
        _save(store, pid, results)
    return out


def interpret_all(store: Store, pid: str, job, llm_factory: Callable[[], object | None]) -> dict:
    doc = document(store, pid)
    todo = [c["id"] for c in doc["clauses"]]
    counts = {"DRAFTED": 0, "UNRESOLVED": 0, "failed": 0}
    for i, cid in enumerate(todo):
        job.progress(i / max(len(todo), 1), f"clause {i + 1} of {len(todo)}")
        try:
            counts[interpret_clause(store, pid, cid, llm_factory)["status"]] += 1
        except ValueError:
            counts["failed"] += 1
    return {"clauses": len(todo), **counts}


# ---- review and approval -------------------------------------------------------------------------------------------


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _context(store: Store, pid: str, clause_id: str):
    path = store.req_path(store.get(pid))
    if path is None or not path.exists():
        raise ValueError("upload a requirement document first")
    full, clauses = split_document(path)
    return assemble_context(path.name, full, clauses, clause_id)


def _entry(store: Store, pid: str, clause_id: str) -> tuple[dict, dict]:
    results = load_results(store, pid)
    entry = results.get(clause_id)
    if entry is None:
        raise ValueError("read this clause first")
    return results, entry


def review_clause(store: Store, pid: str, clause_id: str, llm_factory: Callable[[], object | None]) -> dict:
    """An independent second reading of the drafted rule against its clause. It never approves; it lists what looks wrong."""
    _, entry = _entry(store, pid, clause_id)
    if entry["status"] != "DRAFTED":
        raise ValueError("there is no rule to review for this clause")
    client = llm_factory()
    if client is None:
        raise ValueError("the drafting model is not available")
    context = _context(store, pid, clause_id)
    _, inputs, _ = _plan(store, pid)
    review = review_program(Program.model_validate(entry["program"]), context, inputs, client)
    with _lock(pid):                                  # re-read: other clauses may have changed while the model worked
        results, entry = _entry(store, pid, clause_id)
        entry["review"] = review
        _save(store, pid, results)
    return entry


def decide_clause(store: Store, pid: str, clause_id: str, action: str, reviewer: str, note: str,
                  acknowledge: bool, llm_factory: Callable[[], object | None]) -> dict:
    """approve (named reviewer; the critic's notes are kept), reject, or reset to pending."""
    update: dict = {}
    if action == "approve":
        _, entry = _entry(store, pid, clause_id)
        if entry["status"] != "DRAFTED":
            raise ValueError("there is no rule to approve for this clause")
        if "review" not in entry:
            entry = review_clause(store, pid, clause_id, llm_factory)
        context = _context(store, pid, clause_id)
        _, inputs, _ = _plan(store, pid)
        artifact = ReviewArtifact.model_validate(entry["review"])
        approved = approve_program(Program.model_validate(entry["program"]), context, inputs, artifact, reviewer,
                                   acknowledge=acknowledge)
        notes = [i.message for i in artifact.review.issues] + list(artifact.review.limitations)
        update = {"approved_program": approved.model_copy(update={"id": rule_id(clause_id)}).model_dump(mode="json"),
                  "decision": {"state": "approved", "by": reviewer.strip(), "at": _now(), "note": note.strip(),
                               "acknowledged_notes": notes if acknowledge else []}}
    elif action == "reject":
        if not reviewer.strip():
            raise ValueError("a reviewer name is required")
        update = {"approved_program": None, "decision": {"state": "rejected", "by": reviewer.strip(), "at": _now(),
                                                         "note": note.strip()}}
    elif action == "reset":
        update = {"approved_program": None, "decision": None}
    else:
        raise ValueError(f"unknown action {action!r}")
    with _lock(pid):
        results, entry = _entry(store, pid, clause_id)
        for key, value in update.items():
            if value is None:
                entry.pop(key, None)
            else:
                entry[key] = value
        _save(store, pid, results)
    return entry


def approved_programs(store: Store, pid: str) -> list[Program]:
    return [Program.model_validate(e["approved_program"]) for e in load_results(store, pid).values()
            if e.get("approved_program") and e.get("decision", {}).get("state") == "approved"]


def coverage(store: Store, pid: str) -> dict:
    """The coverage report data: every clause with what was done, and the outcome of each approved rule on the plan."""
    from ..report.coverage import build

    project = {k: getattr(store.get(pid), k) for k in ("name", "plan", "inventory_reviewed")}
    run = store.run_dir(pid)

    def read(name: str, default):
        f = run / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default

    findings = read("findings.json", {})
    findings = findings.get("findings", []) if isinstance(findings, dict) else findings
    return build(project, document(store, pid), load_results(store, pid), read("interpreted_results.json", []), findings)
