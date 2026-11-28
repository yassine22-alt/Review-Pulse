"""HTTP API and the single-page UI. ``create_app(data_dir)``; ``rp serve`` runs it with uvicorn."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..interpreter.api import interpreter_router
from . import interpret as interpretation
from . import service, workflow
from .jobs import JobRunner
from .prepare import Preparer
from .store import PLAN_TYPES, REQ_TYPES, Store, one_line, read_whole

STATIC = Path(__file__).parent / "static"
WEB = Path(__file__).parent / "web"          # the product front end, built from frontend/ (npm run build)
WEB_CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
           "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
MAX_UPLOAD_MB = 200
LLM_STATUS_TTL_S = 30
DOWNLOADS = {"report.pdf": "application/pdf", "report.html": "text/html", "findings.json": "application/json",
             "findings.csv": "text/csv", "triage.json": "application/json"}


def served(path: Path, media_type: str, filename: str | None = None, inline: bool = True) -> Response:
    """A file the app makes and remakes, sent from bytes read at once. Streaming it from disk announces one length and may send
    another when a job rewrites the file meanwhile."""
    headers = {}
    if filename:
        headers["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{filename}"'
    return Response(read_whole(path), media_type=media_type, headers=headers)


class NewProject(BaseModel):
    name: str
    base_pack: str | None = None
    curator: str = ""
    occupancy: str = ""
    location: str = ""


class Settings(BaseModel):
    name: str | None = None
    occupancy: str | None = None
    location: str | None = None
    base_pack: str | None = None
    curator: str | None = None
    inventory_reviewed: bool | None = None
    external_consent: bool | None = None
    clear_base_pack: bool = False


class ClauseRef(BaseModel):
    clause: str


class Decision(ClauseRef):
    action: str                       # approve | reject | reset
    reviewer: str = ""
    note: str = ""
    acknowledge: bool = False         # the reviewer read the second reader's notes and approves anyway


class ItemAction(BaseModel):
    action: str                       # accept | edit | drop | reset
    reviewer: str = ""
    wording: str | None = None
    reason: str = ""                  # why it is not a correction: required to dismiss


class FollowUp(BaseModel):
    reviewer: str = ""
    assignee: str | None = None       # an empty name takes the assignment away
    due: str = ""
    resolved: bool | None = None
    note: str = ""                    # what was checked: required to resolve


class Place(BaseModel):
    sheet: str                        # the sheet's id
    box: list[float] | None = None    # in sheet space; none means the sheet as a whole
    text: str = ""                    # the words relied on


class PartMark(BaseModel):
    text: str
    mark: str                         # seen | missing


class ClauseState(BaseModel):
    clause: str
    state: str                        # shown | correction | not_applicable | deferred | reset
    reviewer: str = ""
    note: str = ""
    evidence: Place | None = None
    parts: list[PartMark] = []        # what the reviewer ticked, part by part


class SignOff(BaseModel):
    reviewer: str = ""
    discipline: str
    result: str
    cycle: int = 1
    note: str = ""


class Approve(BaseModel):
    curator: str = ""
    rule_yaml: str | None = None


class Decide(BaseModel):
    curator: str = ""


class ContextLinks(BaseModel):
    links: dict[str, list[str]]


class Triage(BaseModel):
    confirm: list[str] = []
    reject: list[str] = []
    unset: list[str] = []
    dismiss: list[str] = []          # "<finding_id>:<reason>"
    restore: list[str] = []
    recheck: bool = True


def create_app(data_dir: str | Path = "data/app", llm: Callable[[], object | None] | None = None,
               workers: int = 2, fallback: Callable[[], object | None] | None = None, auth: bool = True) -> FastAPI:
    """``auth=False`` is for scripts and tests that drive the app inside their own process; a served app has accounts."""
    store = Store(data_dir)
    jobs = JobRunner(store, workers)
    llm = llm or service.default_llm
    fallback = fallback if fallback is not None else service.default_fallback
    preparer = Preparer(store, llm, enabled=os.environ.get("REVIEWPULSE_PREPARE", "on") != "off", busy=jobs.any_active)

    def then_prepare(pid: str, work):
        """A job that, once done, lets the requirements be searched ahead of the reviewer."""
        def run(job):
            result = work(job)
            preparer.ensure(pid)
            return result
        return run

    @asynccontextmanager
    async def lifespan(_app):
        yield
        preparer.close()
        jobs.shutdown()

    app = FastAPI(title="ReviewPulse", version="0.1.0", lifespan=lifespan,
                  description="Automated review of architectural plans against requirement documents")
    app.state.store, app.state.jobs, app.state.preparer = store, jobs, preparer
    app.include_router(interpreter_router(llm))
    if auth:
        from .auth import Accounts
        from .auth.http import install

        app.state.accounts = Accounts(Path(data_dir) / "accounts.sqlite")
        install(app, app.state.accounts, store)

    def who(request: Request, typed: str) -> str:
        """The name that goes on a decision: the signed in account's, never one typed into the request."""
        user = getattr(request.state, "user", None)
        return user.name if user else typed

    def project(pid: str):
        try:
            return store.get(pid)
        except KeyError:
            raise HTTPException(404, f"no project {pid}") from None

    def payload(p) -> dict:
        d = dict(p.__dict__)
        d["active_jobs"] = jobs.active(p.id)
        d["analysed"] = (store.run_dir(p.id) / "view.json").exists()
        d["checked"] = (store.run_dir(p.id) / "findings.json").exists()
        d["has_drafts"] = any(store.drafts_dir(p.id).glob("*.drafts.yaml"))
        # what the plan reader looks for, in words: the screens say what a person confirms, from the data
        from ..factgraph.from_building import LOOKED_FOR
        from ..report.coverage import _every

        d["looked_for"] = _every([k + "s" if not k.endswith("s") else k for k in LOOKED_FOR])
        try:
            d["rules"] = service.rules_summary(store, p)
        except ValueError as e:
            d["rules"] = {"error": str(e)}
        return d

    async def read_upload(f: UploadFile) -> bytes:
        data = await f.read()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"file larger than {MAX_UPLOAD_MB} MB")
        if not data:
            raise HTTPException(400, "empty file")
        return data

    # -- service --------------------------------------------------------------
    llm_cache: dict = {}

    @app.get("/api/health")
    def health():
        # probing the model server takes seconds; the answer is kept for LLM_STATUS_TTL_S
        if time.time() - llm_cache.get("at", 0) > LLM_STATUS_TTL_S:
            llm_cache.update(at=time.time(), status=service.llm_status(llm), hosted=service.llm_status(fallback))
        from ..perception.learned.classifier import version

        return {"ok": True, "llm": llm_cache["status"], "hosted": llm_cache["hosted"], "plan_types": sorted(PLAN_TYPES),
                "requirement_types": sorted(REQ_TYPES), "drawing_model": version()}

    @app.get("/api/packs")
    def packs():
        return service.base_packs()

    # -- projects -------------------------------------------------------------
    @app.get("/api/projects")
    def list_projects(request: Request):
        user = getattr(request.state, "user", None)
        return [payload(p) for p in store.list() if not user or p.org == user.org]

    @app.post("/api/projects", status_code=201)
    def create_project(body: NewProject, request: Request):
        if body.base_pack and body.base_pack not in {p["name"] for p in service.base_packs()}:
            raise HTTPException(400, f"unknown base pack {body.base_pack!r}")
        user = getattr(request.state, "user", None)
        return payload(store.create(body.name, body.base_pack, who(request, body.curator), user.org if user else "",
                                    body.occupancy, body.location))

    @app.get("/api/projects/{pid}")
    def get_project(pid: str):
        return payload(project(pid))

    @app.patch("/api/projects/{pid}")
    def update_project(pid: str, body: Settings, request: Request):
        p = project(pid)
        user = getattr(request.state, "user", None)
        reviewers_only = body.inventory_reviewed is not None or body.external_consent is not None
        if user and reviewers_only and "reviewer" not in user.roles:
            raise HTTPException(403, "only a reviewer can confirm the inventory or allow a hosted model")
        if body.name is not None:
            p.name = body.name.strip() or p.name
        if body.occupancy is not None:
            p.occupancy = one_line(body.occupancy)
        if body.location is not None:
            p.location = one_line(body.location)
        if body.curator is not None:
            p.curator = who(request, body.curator.strip())
        if body.inventory_reviewed is not None:
            p.inventory_reviewed = body.inventory_reviewed
        if body.external_consent is not None:
            p.external_consent = body.external_consent
        if body.clear_base_pack:
            p.base_pack = None
        elif body.base_pack is not None:
            if body.base_pack not in {x["name"] for x in service.base_packs()}:
                raise HTTPException(400, f"unknown base pack {body.base_pack!r}")
            p.base_pack = body.base_pack
        return payload(store.save(p))

    @app.delete("/api/projects/{pid}", status_code=204)
    def delete_project(pid: str):
        project(pid)
        store.delete(pid)

    # -- uploads and jobs -------------------------------------------------------
    @app.post("/api/projects/{pid}/plan", status_code=202)
    async def upload_plan(pid: str, file: UploadFile = File(...)):
        p = project(pid)
        data = await read_upload(file)
        if p.plan_version and hashlib.sha256(data).hexdigest()[:16] != p.plan_version:
            try:                                   # what was asked on the present drawings is kept before they are replaced
                service.keep_round_comments(store, pid)
            except ValueError:
                pass                               # no correction list yet: there is nothing a later round could answer
            p = project(pid)
        try:
            store.put_input(p, "plan", file.filename or "plan", data)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return jobs.submit(pid, "analyse", then_prepare(pid, lambda job: service.analyse(store, pid, job)))

    @app.post("/api/projects/{pid}/requirements", status_code=202)
    async def upload_requirements(pid: str, file: UploadFile = File(...)):
        p = project(pid)
        try:
            store.put_input(p, "requirements", file.filename or "requirements", await read_upload(file))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        # the product reads clauses on demand from the review desk; the older pages still list drafts made at upload
        return jobs.submit(pid, "draft", then_prepare(pid, lambda job: service.draft(store, pid, job, llm, split_only=auth)))

    @app.post("/api/projects/{pid}/draft", status_code=202)
    def redraft(pid: str):
        p = project(pid)
        if not p.requirements:
            raise HTTPException(400, "upload a requirement document first")
        return jobs.submit(pid, "draft", lambda job: service.draft(store, pid, job, llm))

    @app.post("/api/projects/{pid}/check", status_code=202)
    def run_check(pid: str):
        p = project(pid)
        if not p.plan:
            raise HTTPException(400, "upload a plan first")
        if not (store.run_dir(pid) / "view.json").exists():
            return jobs.submit(pid, "analyse", then_prepare(pid, lambda job: service.analyse(store, pid, job)))
        return jobs.submit(pid, "check", lambda job: service.check(store, pid, job))

    @app.get("/api/projects/{pid}/jobs")
    def list_jobs(pid: str):
        project(pid)
        return jobs.list(pid)

    @app.get("/api/projects/{pid}/jobs/{jid}")
    def get_job(pid: str, jid: str):
        project(pid)
        try:
            return jobs.get(pid, jid)
        except KeyError:
            raise HTTPException(404, f"no job {jid}") from None

    # -- requirements and the review queue -------------------------------------
    @app.get("/api/projects/{pid}/clauses")
    def get_clauses(pid: str):
        project(pid)
        return service.clauses(store, pid)

    @app.get("/api/projects/{pid}/document")
    def get_document(pid: str):
        project(pid)
        try:
            return interpretation.document(store, pid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.put("/api/projects/{pid}/context-links")
    def put_context_links(pid: str, body: ContextLinks):
        project(pid)
        return {"links": interpretation.set_context_links(store, pid, body.links)}

    @app.get("/api/projects/{pid}/notes")
    def get_notes(pid: str, clause: str):
        """The notes of the drawing set closest to a requirement. A search only: no rule is written and nothing is decided."""
        project(pid)
        try:
            return interpretation.find_notes(store, pid, clause)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/projects/{pid}/parts")
    def get_parts(pid: str, clause: str):
        """The things one requirement asks for, each with the notes and the drawing text closest to it. Only the
        requirement's words go to the reading model."""
        project(pid)
        try:
            with preparer.person_waiting():
                return interpretation.find_parts(store, pid, clause, llm)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/projects/{pid}/back-check")
    def get_back_check(pid: str):
        """The current drawings against the version before: what was asked, and how the new set answers each comment."""
        project(pid)
        return service.back_check_view(store, pid)

    @app.post("/api/projects/{pid}/back-check", status_code=202)
    def post_back_check(pid: str):
        project(pid)
        found, why = service.rounds(store, pid)
        if found is None:
            raise HTTPException(409, why)
        return jobs.submit(pid, "backcheck", lambda job: service.run_back_check(store, pid, job))

    @app.get("/api/projects/{pid}/prepared")
    def get_prepared(pid: str):
        """How far the requirements have been searched ahead. Asking also starts it, after a restart for instance."""
        project(pid)
        preparer.ensure(pid)
        return preparer.status(pid)

    @app.get("/api/projects/{pid}/interpreted")
    def get_interpreted(pid: str):
        project(pid)
        return interpretation.load_results(store, pid)

    @app.post("/api/projects/{pid}/interpret/{clause_id:path}")
    def interpret_one(pid: str, clause_id: str):
        project(pid)
        try:
            return interpretation.interpret_clause(store, pid, clause_id, llm, fallback)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.post("/api/projects/{pid}/review")
    def review_one(pid: str, body: ClauseRef):
        project(pid)
        try:
            return interpretation.review_clause(store, pid, body.clause, llm)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.post("/api/projects/{pid}/decision")
    def decide_one(pid: str, body: Decision, request: Request):
        project(pid)
        body.reviewer = who(request, body.reviewer)
        try:
            out = interpretation.decide_clause(store, pid, body.clause, body.action, body.reviewer, body.note,
                                               body.acknowledge, llm)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        if body.reviewer.strip():
            workflow.log(store, pid, body.reviewer, f"rule for clause {body.clause}: {body.action}",
                         {"clause": body.clause, "action": body.action, "note": body.note})
        return out

    @app.get("/api/projects/{pid}/coverage")
    def get_coverage(pid: str):
        project(pid)
        try:
            return interpretation.coverage(store, pid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/projects/{pid}/coverage.html", include_in_schema=False)
    def get_coverage_html(pid: str):
        from ..report.coverage import render_html

        project(pid)
        try:
            return HTMLResponse(render_html(interpretation.coverage(store, pid)))
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.post("/api/projects/{pid}/interpret", status_code=202)
    def interpret_everything(pid: str):
        project(pid)
        return jobs.submit(pid, "interpret", lambda job: interpretation.interpret_all(store, pid, job, llm, fallback))

    @app.get("/api/projects/{pid}/drafts")
    def get_drafts(pid: str):
        project(pid)
        return service.drafts(store, pid)

    @app.post("/api/projects/{pid}/drafts/{index}/approve")
    def approve(pid: str, index: int, body: Approve, request: Request):
        project(pid)
        body.curator = who(request, body.curator)
        try:
            return service.approve_draft(store, pid, index, body.curator, body.rule_yaml)
        except KeyError:
            raise HTTPException(404, f"no draft {index}") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/projects/{pid}/drafts/{index}/reject")
    def reject(pid: str, index: int, body: Decide, request: Request):
        project(pid)
        body.curator = who(request, body.curator)
        try:
            return service.reject_draft(store, pid, index, body.curator)
        except KeyError:
            raise HTTPException(404, f"no draft {index}") from None

    @app.post("/api/projects/{pid}/drafts/{index}/reset")
    def reset(pid: str, index: int, body: Decide, request: Request):
        project(pid)
        body.curator = who(request, body.curator)
        try:
            return service.reject_draft(store, pid, index, body.curator, reset=True)
        except KeyError:
            raise HTTPException(404, f"no draft {index}") from None

    # -- results -------------------------------------------------------------------
    @app.get("/api/projects/{pid}/findings")
    def get_findings(pid: str):
        project(pid)
        return service.findings(store, pid)

    @app.get("/api/projects/{pid}/view")
    def get_view(pid: str):
        project(pid)
        f = store.run_dir(pid) / "view.json"
        if not f.exists():
            raise HTTPException(404, "not analysed yet")
        return served(f, "application/json")

    @app.get("/api/projects/{pid}/sheets/{index}/backdrop.png")
    def backdrop(pid: str, index: int):
        project(pid)
        f = store.run_dir(pid) / f"backdrop_{index}.png"
        if not f.exists():
            raise HTTPException(404, "no such sheet")
        return served(f, "image/png")

    @app.post("/api/projects/{pid}/triage")
    def post_triage(pid: str, body: Triage):
        project(pid)
        try:
            t = service.triage(store, pid, body.confirm, body.reject, body.unset, body.dismiss, body.restore)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        job = jobs.submit(pid, "check", lambda job: service.check(store, pid, job)) if body.recheck else None
        return {"triage": t, "job": job}

    # -- the correction list, reviewer states, sign off and audit trail ------------------------------------------
    def current_list(pid: str, cycle: int | None = None) -> dict:
        project(pid)
        try:
            return service.correction_list(store, pid, cycle)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/reviewer-states")
    def reviewer_states():
        from ..report import disciplines
        from ..report import reviewer_states as rstates

        cfg = rstates.config()
        return {"statuses": {k: v["label"] for k, v in cfg["statuses"].items()}, "results": cfg["results"],
                "signoff_results": cfg["signoff_results"], "reviewer_settable": list(cfg["reviewer_decisions"]),
                "disciplines": {k: disciplines.label(k) for k in disciplines.order()}}

    EXPORT_TYPES = {"pdf": ("application/pdf", "correction_markup.pdf"), "bcf": ("application/octet-stream", "correction_list.bcf"),
                    "csv": ("text/csv", "correction_list.csv"), "json": ("application/json", "correction_list.comments.json")}

    @app.get("/api/projects/{pid}/correction-list")
    def get_correction_list(pid: str, format: str = "json", cycle: int | None = None, file: bool = False):
        """format: json (the list itself; ``file=true`` gives the exchange file), html, txt, pdf, bcf or csv."""
        from fastapi.responses import PlainTextResponse

        from ..report import correction_list as cl

        if format not in {"json", "html", "txt", "text", "pdf", "bcf", "csv"}:
            raise HTTPException(400, "format must be json, html, txt, pdf, bcf or csv")
        data = current_list(pid, cycle)
        if format == "html":
            return HTMLResponse(cl.render_html(data))
        if format in ("txt", "text"):
            return PlainTextResponse(cl.render_text(data))
        if format == "json" and not file:
            return data
        if not any(store.run_dir(pid).glob("building_*.json")) and format in ("pdf", "bcf"):
            raise HTTPException(409, "the plan has not been analysed yet")
        try:
            path = service.correction_export(store, pid, format, cycle)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        mime, name = EXPORT_TYPES[format]
        response = served(path, mime, f"{pid}_{name}", inline=format == "pdf")
        shutil.rmtree(path.parent, ignore_errors=True)
        return response

    @app.get("/api/projects/{pid}/correction-list.pdf")
    def get_correction_pdf(pid: str, cycle: int | None = None):
        return get_correction_list(pid, "pdf", cycle)

    @app.put("/api/projects/{pid}/correction-list/items/{key:path}")
    def put_item(pid: str, key: str, body: ItemAction, request: Request):
        data = current_list(pid)
        body.reviewer = who(request, body.reviewer)
        if body.action != "reset" and not any(i["key"] == key for i in data["items"]):
            raise HTTPException(404, f"no correction item {key}")
        try:
            workflow.set_item(store, pid, key, body.action, body.reviewer, body.wording, reason=body.reason)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return service.correction_list(store, pid)

    def office(request: Request) -> list[dict]:
        """The people of the signed in person's organisation a comment can be given to; none without accounts."""
        from .auth.policy import OFFICE

        user = getattr(request.state, "user", None)
        if user is None:
            return []
        return [{"name": m["name"], "roles": m["roles"]} for m in app.state.accounts.members(user.org)
                if m["active"] and OFFICE & set(m["roles"])]

    @app.get("/api/people")
    def people(request: Request):
        return office(request)

    @app.get("/api/my-items")
    def my_items(request: Request):
        user = getattr(request.state, "user", None)
        return service.assigned_to(store, user.org, user.name) if user else []

    @app.put("/api/projects/{pid}/correction-list/follow-up/{key:path}")
    def put_follow_up(pid: str, key: str, body: FollowUp, request: Request):
        data = current_list(pid)
        body.reviewer = who(request, body.reviewer)
        if not any(i["key"] == key for i in data["items"]):
            raise HTTPException(404, f"no correction item {key}")
        if body.assignee is None and body.resolved is None:
            raise HTTPException(400, "say who takes it, or whether it is resolved")
        accounts = getattr(request.state, "user", None) is not None
        if body.assignee and accounts and body.assignee not in {m["name"] for m in office(request)}:
            raise HTTPException(400, "choose someone of your organisation")
        try:
            if body.assignee is not None:
                workflow.assign(store, pid, key, body.assignee, body.due, body.reviewer)
            if body.resolved is not None:
                workflow.resolve(store, pid, key, body.resolved, body.note, body.reviewer)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return service.correction_list(store, pid)

    @app.get("/api/projects/{pid}/clause-states")
    def get_clause_states(pid: str):
        project(pid)
        return workflow.decisions(store, pid, service.clause_texts(store, pid))

    @app.put("/api/projects/{pid}/clause-states")
    def put_clause_state(pid: str, body: ClauseState, request: Request):
        project(pid)
        body.reviewer = who(request, body.reviewer)
        try:
            evidence = service.checked_place(store, pid, body.evidence.model_dump()) if body.evidence else None
            if body.state in ("shown", "correction"):
                service.known_clause(store, pid, body.clause)
            return workflow.set_clause_state(store, pid, body.clause, body.state, body.reviewer, body.note, evidence,
                                             service.clause_texts(store, pid).get(body.clause),
                                             [m.model_dump() for m in body.parts],
                                             interpretation.offered_parts(store, pid, body.clause) if body.parts else [])
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/projects/{pid}/signoffs")
    def get_signoffs(pid: str):
        project(pid)
        return workflow.signoffs(store, pid)

    @app.post("/api/projects/{pid}/signoffs", status_code=201)
    def post_signoff(pid: str, body: SignOff, request: Request):
        from ..report import disciplines

        project(pid)
        body.reviewer = who(request, body.reviewer)
        try:
            return workflow.sign_off(store, pid, body.reviewer, body.discipline, body.result, body.cycle, body.note,
                                     known_disciplines=set(disciplines.order()))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/projects/{pid}/audit")
    def get_audit(pid: str):
        project(pid)
        return workflow.audit(store, pid)

    @app.get("/api/projects/{pid}/files/{name}")
    def download(pid: str, name: str):
        project(pid)
        if name not in DOWNLOADS:
            raise HTTPException(404, "unknown file")
        f = store.run_dir(pid) / name
        if not f.exists():
            raise HTTPException(404, "not produced yet: run a check")
        # reports open in the browser tab; data files download
        inline = name.endswith((".pdf", ".html"))
        return served(f, DOWNLOADS[name], f"{pid}_{name}", inline=inline)

    # -- UI ------------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unexpected(_req, exc):  # pragma: no cover - last-resort JSON error
        if auth:                           # a served product does not show its internals
            logging.getLogger("reviewpulse").error("unhandled error", exc_info=exc)
            return JSONResponse({"detail": "something went wrong on the server; the error was logged"}, status_code=500)
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    if auth and (WEB / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        if not auth:                       # the single user pages cannot sign in: only for a server without accounts
            return FileResponse(STATIC / "index.html")
        if not (WEB / "index.html").exists():
            return HTMLResponse("<h1>ReviewPulse</h1><p>The web pages are not built. Run: cd frontend, npm ci, "
                                "npm run build.</p>", status_code=503)
        return FileResponse(WEB / "index.html", headers={"Content-Security-Policy": WEB_CSP, "Cache-Control": "no-cache"})

    return app
