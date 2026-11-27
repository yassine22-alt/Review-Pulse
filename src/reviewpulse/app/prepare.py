"""Search every requirement ahead of the reviewer, so opening one is not a wait.

Opening a requirement for the first time takes seconds: it is cut into parts and each part is searched. Done after upload, in
the background, that time passes while nobody is waiting. One worker for the whole server goes through one submission at a
time, one requirement at a time, and steps aside whenever a person is waiting for a search of their own. What it makes is
exactly what opening would have made, kept under the same names, so nothing a reviewer sees depends on whether it ran. It
also waits while any job is queued or running: reading drawings, reading requirements and checking are things a person asked
for, and they share the processor and the local model with it.

It does not run with a reading model outside this machine and its private network: a person opening a requirement is a use
they chose, a hundred calls nobody asked for would spend their allowance (and hosted consent was given for use, not for that).
Results then are made on opening, as before."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager

from . import interpret
from .store import Store

PAUSE_S = 0.1
GIVE_UP_AFTER = 3                      # requirements in a row that cannot be searched: something is wrong, stop asking


class Preparer:
    def __init__(self, store: Store, llm: Callable[[], object | None], enabled: bool = True,
                 busy: Callable[[], bool] = lambda: False):
        self.store, self.llm, self.enabled, self.busy = store, llm, enabled, busy
        self._queue: deque[str] = deque()
        self._state: dict[str, dict] = {}
        self._guard = threading.Lock()
        self._wake = threading.Event()
        self._waiting = 0              # people waiting for a search right now
        self._thread: threading.Thread | None = None
        self._stop = False

    @contextmanager
    def person_waiting(self):
        """Held while someone waits for a search: the worker starts nothing new until they have it."""
        with self._guard:
            self._waiting += 1
        try:
            yield
        finally:
            with self._guard:
                self._waiting -= 1

    def status(self, pid: str) -> dict:
        with self._guard:
            got = self._state.get(pid)
            return {k: v for k, v in got.items() if k != "stamp"} if got else {"done": 0, "total": 0, "running": False}

    def ensure(self, pid: str) -> None:
        """Queue a submission unless its present drawings and requirements are already prepared or being prepared."""
        if not self.enabled:
            return
        stamp = interpret.search_stamp(self.store, pid)
        if stamp is None:                                      # no analysed plan or no requirement document yet
            return
        with self._guard:
            got = self._state.get(pid)
            if got and got["stamp"] == stamp and (got["running"] or got["finished"]):
                return
            self._state[pid] = {"stamp": stamp, "done": 0, "total": 0, "running": True, "finished": False}
            if pid not in self._queue:
                self._queue.append(pid)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="rp-prepare", daemon=True)
                self._thread.start()
        self._wake.set()

    def close(self) -> None:
        self._stop = True
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=60)

    def _run(self) -> None:
        while not self._stop:
            with self._guard:
                pid = self._queue.popleft() if self._queue else None
            if pid is None:
                self._wake.wait(1.0)
                self._wake.clear()
                continue
            try:
                self._prepare(pid)
            except Exception as exc:  # noqa: BLE001 - preparing is a convenience; a requirement is still searched on opening
                self._set(pid, running=False, problem=f"{type(exc).__name__}: {exc}"[:200])

    def _set(self, pid: str, **values) -> None:
        with self._guard:
            self._state[pid].update(values)

    def _prepare(self, pid: str) -> None:
        with self._guard:
            stamp = self._state[pid]["stamp"]
        client = self.llm()
        if client is not None and getattr(client, "external", False):
            self._set(pid, running=False, finished=True, off="the reading model is a hosted one")
            return
        ids = interpret.searchable_clauses(self.store, pid)
        self._set(pid, total=len(ids))
        failed = 0
        for cid in ids:
            while (self._waiting or self.busy()) and not self._stop:
                time.sleep(PAUSE_S)
            if self._stop:
                return
            if interpret.search_stamp(self.store, pid) != stamp:      # new drawings or a new document: start over
                self._set(pid, running=False)
                self.ensure(pid)
                return
            try:
                interpret.find_parts(self.store, pid, cid, self.llm)
                failed = 0
            except Exception as exc:  # noqa: BLE001
                failed += 1
                if failed >= GIVE_UP_AFTER:
                    self._set(pid, running=False, problem=f"{type(exc).__name__}: {exc}"[:200])
                    return
            with self._guard:
                self._state[pid]["done"] += 1
        self._set(pid, running=False, finished=True)
