"""Background jobs: a small thread pool, one job at a time per project, every job recorded on disk.

A job record is ``{id, project, kind, status, progress, message, error, result, created, started,
finished}``; status goes queued -> running -> done | failed. Jobs left running by a stopped server are
marked failed ("interrupted") at start-up, never silently resumed.
"""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .store import Store, now, replace


class Job:
    """Handle passed to the work function: report progress, read the record."""

    def __init__(self, runner: JobRunner, rec: dict):
        self._runner = runner
        self.rec = rec

    def progress(self, fraction: float, message: str | None = None) -> None:
        self.rec["progress"] = round(max(0.0, min(1.0, fraction)), 3)
        if message is not None:
            self.rec["message"] = message
        self._runner._write(self.rec)


class JobRunner:
    def __init__(self, store: Store, workers: int = 2):
        self.store = store
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rp-job")
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._io = threading.Lock()
        self._live: dict[str, dict] = {}        # records of jobs started by this process
        self._recover()

    def _path(self, pid: str, jid: str) -> Path:
        return self.store.dir(pid) / "jobs" / f"{jid}.json"

    def _write(self, rec: dict) -> None:
        p = self._path(rec["project"], rec["id"])
        p.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(rec, indent=1, default=str)
        with self._io:
            tmp = p.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            replace(tmp, p)

    def _recover(self) -> None:
        for f in (self.store.root / "projects").glob("*/jobs/*.json"):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if rec.get("status") in ("queued", "running"):
                rec.update(status="failed", error="interrupted: the server stopped while this job ran",
                           finished=now())
                self._write(rec)

    def _lock(self, pid: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(pid, threading.Lock())

    def submit(self, pid: str, kind: str, fn: Callable[[Job], dict | None]) -> dict:
        rec = {"id": uuid.uuid4().hex[:12], "project": pid, "kind": kind, "status": "queued", "progress": 0.0,
               "message": "queued", "error": None, "result": None, "created": now(), "started": None,
               "finished": None}
        self._live[rec["id"]] = rec
        self._write(rec)
        job = Job(self, rec)

        def run():
            with self._lock(pid):
                rec.update(status="running", started=now(), message="running")
                self._write(rec)
                try:
                    rec["result"] = fn(job)
                    rec.update(status="done", progress=1.0, message="done")
                except Exception as e:  # noqa: BLE001 - a failed job is recorded, never lost
                    rec.update(status="failed", error=f"{type(e).__name__}: {e}",
                               trace=traceback.format_exc()[-4000:])
                rec["finished"] = now()
                self._write(rec)

        self.pool.submit(run)
        return rec

    def get(self, pid: str, jid: str) -> dict:
        live = self._live.get(jid)
        if live is not None and live["project"] == pid:
            return json.loads(json.dumps(live, default=str))
        p = self._path(pid, jid)
        if not p.exists():
            raise KeyError(jid)
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self, pid: str, limit: int = 20) -> list[dict]:
        recs = []
        for f in (self.store.dir(pid) / "jobs").glob("*.json"):
            live = self._live.get(f.stem)
            if live is not None:
                recs.append(json.loads(json.dumps(live, default=str)))
                continue
            try:
                recs.append(json.loads(f.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        return sorted(recs, key=lambda r: r["created"], reverse=True)[:limit]

    def active(self, pid: str) -> list[dict]:
        return [r for r in self.list(pid, 50) if r["status"] in ("queued", "running")]

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
