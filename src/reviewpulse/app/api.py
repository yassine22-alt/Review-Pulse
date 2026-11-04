"""HTTP API and the single-page UI. ``create_app(data_dir)``; ``rp serve`` runs it with uvicorn."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..interpreter.api import interpreter_router
from . import service
from .jobs import JobRunner
from .store import PLAN_TYPES, REQ_TYPES, Store

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD_MB = 200
LLM_STATUS_TTL_S = 30
DOWNLOADS = {"report.pdf": "application/pdf", "report.html": "text/html", "findings.json": "application/json",
             "findings.csv": "text/csv", "triage.json": "application/json"}


class NewProject(BaseModel):
    name: str
    base_pack: str | None = "starter"
    curator: str = ""


class Settings(BaseModel):
    name: str | None = None
    base_pack: str | None = None
    curator: str | None = None
    clear_base_pack: bool = False


class Approve(BaseModel):
    curator: str = ""
    rule_yaml: str | None = None


class Decide(BaseModel):
    curator: str = ""


class Triage(BaseModel):
    confirm: list[str] = []
    reject: list[str] = []
    unset: list[str] = []
    dismiss: list[str] = []          # "<finding_id>:<reason>"
    restore: list[str] = []
    recheck: bool = True


def create_app(data_dir: str | Path = "data/app", llm: Callable[[], object | None] | None = None,
               workers: int = 2) -> FastAPI:
    store = Store(data_dir)
    jobs = JobRunner(store, workers)
    llm = llm or service.default_llm
    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.shutdown()

    app = FastAPI(title="ReviewPulse", version="0.1.0", lifespan=lifespan,
                  description="Automated review of architectural plans against requirement documents")
    app.state.store, app.state.jobs = store, jobs
    app.include_router(interpreter_router(llm))

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
            llm_cache.update(at=time.time(), status=service.llm_status(llm))
        return {"ok": True, "llm": llm_cache["status"], "plan_types": sorted(PLAN_TYPES),
                "requirement_types": sorted(REQ_TYPES)}

    @app.get("/api/packs")
    def packs():
        return service.base_packs()

    # -- projects -------------------------------------------------------------
    @app.get("/api/projects")
    def list_projects():
        return [payload(p) for p in store.list()]

    @app.post("/api/projects", status_code=201)
    def create_project(body: NewProject):
        if body.base_pack and body.base_pack not in {p["name"] for p in service.base_packs()}:
            raise HTTPException(400, f"unknown base pack {body.base_pack!r}")
        return payload(store.create(body.name, body.base_pack, body.curator))

    @app.get("/api/projects/{pid}")
    def get_project(pid: str):
        return payload(project(pid))

    @app.patch("/api/projects/{pid}")
    def update_project(pid: str, body: Settings):
        p = project(pid)
        if body.name is not None:
            p.name = body.name.strip() or p.name
        if body.curator is not None:
            p.curator = body.curator.strip()
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
        try:
            store.put_input(p, "plan", file.filename or "plan", await read_upload(file))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return jobs.submit(pid, "analyse", lambda job: service.analyse(store, pid, job))

    @app.post("/api/projects/{pid}/requirements", status_code=202)
    async def upload_requirements(pid: str, file: UploadFile = File(...)):
        p = project(pid)
        try:
            store.put_input(p, "requirements", file.filename or "requirements", await read_upload(file))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return jobs.submit(pid, "draft", lambda job: service.draft(store, pid, job, llm))

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
            return jobs.submit(pid, "analyse", lambda job: service.analyse(store, pid, job))
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

    @app.get("/api/projects/{pid}/drafts")
    def get_drafts(pid: str):
        project(pid)
        return service.drafts(store, pid)

    @app.post("/api/projects/{pid}/drafts/{index}/approve")
    def approve(pid: str, index: int, body: Approve):
        project(pid)
        try:
            return service.approve_draft(store, pid, index, body.curator, body.rule_yaml)
        except KeyError:
            raise HTTPException(404, f"no draft {index}") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/projects/{pid}/drafts/{index}/reject")
    def reject(pid: str, index: int, body: Decide):
        project(pid)
        try:
            return service.reject_draft(store, pid, index, body.curator)
        except KeyError:
            raise HTTPException(404, f"no draft {index}") from None

    @app.post("/api/projects/{pid}/drafts/{index}/reset")
    def reset(pid: str, index: int, body: Decide):
        project(pid)
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
        return FileResponse(f, media_type="application/json")

    @app.get("/api/projects/{pid}/sheets/{index}/backdrop.png")
    def backdrop(pid: str, index: int):
        project(pid)
        f = store.run_dir(pid) / f"backdrop_{index}.png"
        if not f.exists():
            raise HTTPException(404, "no such sheet")
        return FileResponse(f, media_type="image/png")

    @app.post("/api/projects/{pid}/triage")
    def post_triage(pid: str, body: Triage):
        project(pid)
        try:
            t = service.triage(store, pid, body.confirm, body.reject, body.unset, body.dismiss, body.restore)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        job = jobs.submit(pid, "check", lambda job: service.check(store, pid, job)) if body.recheck else None
        return {"triage": t, "job": job}

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
        return FileResponse(f, media_type=DOWNLOADS[name], filename=f"{pid}_{name}",
                            content_disposition_type="inline" if inline else "attachment")

    # -- UI ------------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unexpected(_req, exc):  # pragma: no cover - last-resort JSON error
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app
