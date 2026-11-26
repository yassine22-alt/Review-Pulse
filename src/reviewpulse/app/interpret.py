"""Requirement clauses interpreted against the project's own plan: a checked rule, or UNRESOLVED with a reason.

For each clause the drafting model writes a one-line expression, code builds the rule, the rule is checked against the
clause and against the plan's declared facts, and a preview of the result on this plan is attached. Nothing here is
approved: approval stays with the interpreter's named-reviewer flow.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable
from datetime import datetime

from ..factgraph.convert import to_graph
from ..factgraph.from_building import from_building, set_notes
from ..interpreter.checked import checked_draft
from ..interpreter.context import assemble_context
from ..interpreter.review import ReviewArtifact, approve_program, review_program
from ..interpreter.runtime import run_program
from ..interpreter.schema import Program
from ..ledger.wiring import attest as _attest
from ..ledger.wiring import build_inputs, load_attestations
from ..regs.context import with_resolved_context
from ..rules.clauses import split_cached
from ..schema import BuildingModel
from .store import Store, replace

SKIP_KINDS = {"heading", "definition", "table_header"}


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
    full, clauses = split_cached(path, store.dir(pid) / "cache")
    return {"name": path.name, "text": full,
            "clauses": [{"id": c.id, "heading": c.heading, "text": c.text, "kind": c.kind, "start": c.start, "end": c.end,
                         "scope": c.scope}
                        for c in clauses if c.kind not in SKIP_KINDS and len(c.text.strip()) > 15 and not _is_title(c)]}


def _is_title(c) -> bool:
    """A short numbered line with no figure and no obligation ("2 Requirements") names a part; nothing in it can be checked."""
    from ..rules.clauses import MODALS

    return (c.kind in ("article", "numbered") and len(c.text.split()) <= 6 and "\n" not in c.text.strip()
            and not re.search(r"\d", c.text.split(None, 1)[1] if " " in c.text.strip() else "") and not MODALS.search(c.text))


def _plan(store: Store, pid: str):
    run = store.run_dir(pid)
    files = sorted(run.glob("building_*.json"))
    if not files:
        raise ValueError("upload and analyse a plan first")
    models = [BuildingModel.model_validate_json(f.read_text(encoding="utf-8")) for f in files]
    plans = [m for m in models if not m.sheet.sheet_kind or m.sheet.sheet_kind == "floor_plan"]
    if not plans:
        kinds = sorted({m.sheet.sheet_kind for m in models if m.sheet.sheet_kind})
        raise ValueError("no floor plan was found in this upload (the sheets show: " + ", ".join(kinds).replace("_", " ") + ")")
    model = max(plans, key=lambda m: (any(e.a in ("EXIT", "EXTERIOR") or e.b in ("EXIT", "EXTERIOR") for e in m.edges),
                                      len(m.rooms)))
    graph = from_building(model, complete=False, part_of_set=len(plans) > 1, notes=set_notes(models))
    inputs, _ = build_inputs(graph, load_attestations(store.drafts_dir(pid)), model)      # REVIEWPULSE_LEDGER=off: plain conversion
    return graph, inputs, to_graph(graph)


def attestations(store: Store, pid: str):
    """What reviewers confirmed for this project (kept in the project's drafts folder, so a reload restores it)."""
    return load_attestations(store.drafts_dir(pid))


def attest(store: Store, pid: str, entity: str, fact: str, value, reviewer: str, source: str, unit: str = "1"):
    """A reviewer states one value for one fact of one entity. A name and a source are required; nothing is written otherwise."""
    with _lock(pid):
        return _attest(store.drafts_dir(pid), entity, fact, value, reviewer=reviewer, source=source, unit=unit)


def interpret_clause(store: Store, pid: str, clause_id: str, llm_factory: Callable[[], object | None],
                     fallback_factory: Callable[[], object | None] | None = None, triage: bool = False) -> dict:
    p = store.get(pid)
    path = store.req_path(p)
    if path is None or not path.exists():
        raise ValueError("upload a requirement document first")
    client = llm_factory()
    if client is None:
        raise ValueError("the drafting model is not available")
    full, clauses = split_cached(path, store.dir(pid) / "cache")
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    context = with_resolved_context(assemble_context(path.name, full, clauses, clause_id, p.context_links), clauses)
    graph, inputs, route_graph = _plan(store, pid)
    # a hosted model is asked only for a clause the local one could not read, and only when the reviewer allowed it
    fallback = fallback_factory() if fallback_factory is not None and p.external_consent else None
    out = checked_draft(context, inputs, graph, client, fallback=fallback, triage=triage)
    out["clause"] = clause_id
    _attach_evidence(store, pid, context, client, out)
    if out["program"] is not None:
        out["program"]["id"] = rule_id(clause_id)
        result = run_program(Program.model_validate(out["program"]), inputs, include_drafts=True, graph=route_graph)
        out["preview"] = {"outcome": result["outcome"], "missing": result["trace"].get("missing", [])[:5]}
    with _lock(pid):
        current = store.get(pid)
        current_path = store.req_path(current)
        if (current.requirements != p.requirements or current.context_links != p.context_links
                or current_path is None or not current_path.is_file()
                or hashlib.sha256(current_path.read_bytes()).hexdigest() != source_hash):
            raise ValueError("the source document or context links changed; read this clause again")
        results = load_results(store, pid)
        results[clause_id] = out            # a new reading replaces the old rule, its review and its decision
        _save(store, pid, results)
    return out


_EMBEDDER: list = []                     # the embedding model, looked for once per process ([None] when it is not installed)
_RERANKER: list = []                     # the cross-encoder, the same way


def _attach_evidence(store: Store, pid: str, context, client, out: dict) -> None:
    """For a clause no measured rule was written for: what the drawings say about it (the note, its sheet, its figure against the
    requirement's). It explains and points; the clause keeps its status and no verdict depends on it. Any failure leaves the
    reading exactly as it was."""
    import os

    measured = out.get("status") == "DRAFTED" and out.get("arm") != "expr_mention"
    if measured or out.get("arm") == "label" or "could not be reached" in (out.get("reason") or "") \
            or os.environ.get("REVIEWPULSE_EVIDENCE", "on") == "off":
        return
    try:
        from ..annotate.passages import set_passages
        from ..interpreter.checked import clause_body
        from ..interpreter.drawing_evidence import default_reranker, find_evidence

        models = [BuildingModel.model_validate_json(f.read_text(encoding="utf-8"))
                  for f in sorted(store.run_dir(pid).glob("building_*.json"))]
        passages = set_passages(models)
        embedder = _embedder()
        if embedder is not None and hasattr(embedder, "load"):
            embedder.load(store.run_dir(pid) / NOTE_VECTORS, [p.text for p in passages])
        if not _RERANKER:
            _RERANKER.append(default_reranker())
        found = find_evidence(clause_body(context), passages, client, embedder, _RERANKER[0])
    except Exception:  # noqa: BLE001 - evidence is an explanation; without it the reading stands
        return
    out["evidence"] = found.as_dict()
    if found.chosen:
        out["notes"] = [*(out.get("notes") or []), "In the drawings: " + found.summary]


NOTE_VECTORS = "note_vectors.npz"        # in the run folder: made again whenever the drawings are read again


def _embedder():
    from ..interpreter.drawing_evidence import default_embedder

    if not _EMBEDDER:
        _EMBEDDER.append(default_embedder())
    return _EMBEDDER[0]


def index_notes(store: Store, pid: str, models: list) -> int:
    """Prepare the meaning search over the drawing notes while the drawings are being read, not when a reviewer first asks.
    Returns the number of notes indexed; 0 when note search is off or no embedding model is installed."""
    import os

    from ..annotate.passages import set_passages

    if os.environ.get("REVIEWPULSE_EVIDENCE", "on") == "off" or (embedder := _embedder()) is None:
        return 0
    texts = [p.text for p in set_passages(models)]
    if texts:
        embedder.save(store.run_dir(pid) / NOTE_VECTORS, texts)
    return len(texts)


def draft_workers(client) -> int:
    """How many clauses are read at once. A local model serves one question at a time, so one; a hosted model (already paced
    to its provider's rate limit) takes several. REVIEWPULSE_DRAFT_WORKERS overrides."""
    import os

    env = os.environ.get("REVIEWPULSE_DRAFT_WORKERS")
    if env and env.isdigit():
        return max(1, int(env))
    return 4 if getattr(client, "external", False) else 1


def interpret_all(store: Store, pid: str, job, llm_factory: Callable[[], object | None],
                  fallback_factory: Callable[[], object | None] | None = None) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    doc = document(store, pid)
    todo = [c["id"] for c in doc["clauses"]]
    counts = {"DRAFTED": 0, "UNRESOLVED": 0, "failed": 0}
    probe = llm_factory()
    workers = min(draft_workers(probe), max(len(todo), 1))
    done = 0

    def one(cid: str) -> str:
        try:
            return interpret_clause(store, pid, cid, llm_factory, fallback_factory, triage=True)["status"]
        except ValueError:
            return "failed"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, cid) for cid in todo]
        for f in as_completed(futures):
            counts[f.result()] += 1
            done += 1
            job.progress(done / max(len(todo), 1), f"clause {done} of {len(todo)}")
    return {"clauses": len(todo), "workers": workers, **counts}


# ---- review and approval -------------------------------------------------------------------------------------------


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _context(store: Store, pid: str, clause_id: str):
    project = store.get(pid)
    path = store.req_path(project)
    if path is None or not path.exists():
        raise ValueError("upload a requirement document first")
    full, clauses = split_cached(path, store.dir(pid) / "cache")
    return with_resolved_context(assemble_context(path.name, full, clauses, clause_id, project.context_links), clauses)


def set_context_links(store: Store, pid: str, links: dict[str, list[str]]) -> dict:
    """Save explicit source dependencies and invalidate interpretations based on the old context."""
    with _lock(pid):
        project = store.get(pid)
        if project.context_links != links:
            project.context_links = links
            store.save(project)
            _file(store, pid).unlink(missing_ok=True)
        return project.context_links


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
    from ..factgraph.from_building import LOOKED_FOR

    data = build(project, document(store, pid), load_results(store, pid), read("interpreted_results.json", []), findings,
                 looked_for=list(LOOKED_FOR))
    from ..drawingset.summary import enabled, summary_for_pdf

    plan = store.plan_path(store.get(pid))
    if enabled() and plan is not None and plan.exists():          # off by default: it reads every page of the PDF
        data["drawing_set"] = summary_for_pdf(plan)
    return data
