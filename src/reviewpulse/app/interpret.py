"""Requirement clauses interpreted against the project's own plan: a checked rule, or UNRESOLVED with a reason.

For each clause the drafting model writes a one-line expression, code builds the rule, the rule is checked against the
clause and against the plan's declared facts, and a preview of the result on this plan is attached. Nothing here is
approved: approval stays with the interpreter's named-reviewer flow.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from ..factgraph.convert import to_graph, to_inputs
from ..factgraph.from_building import from_building
from ..interpreter.checked import checked_draft
from ..interpreter.context import assemble_context
from ..interpreter.runtime import run_program
from ..interpreter.schema import Program
from ..rules.clauses import split_document
from ..schema import BuildingModel
from .store import Store

SKIP_KINDS = {"heading"}


def _file(store: Store, pid: str):
    return store.drafts_dir(pid) / "interpreted.json"


def load_results(store: Store, pid: str) -> dict:
    f = _file(store, pid)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _save(store: Store, pid: str, results: dict) -> None:
    f = _file(store, pid)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


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
        result = run_program(Program.model_validate(out["program"]), inputs, include_drafts=True, graph=route_graph)
        out["preview"] = {"outcome": result["outcome"], "missing": result["trace"].get("missing", [])[:5]}
    results = load_results(store, pid)
    results[clause_id] = out
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
