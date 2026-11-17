"""A persistent cache of model answers: re-running a demo or an evaluation costs nothing and gives the same result.

An answer is keyed by everything that determines it (model, system prompt, user prompt, schema). Three modes:
  readwrite   use a stored answer when there is one, store each new answer (default)
  replay      never call the model: a missing answer is an error (offline demos, tests, reproducing a result exactly)
  off         no cache

This also keeps a free tier's daily allowance for new work: a clause read once is never paid for again.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path


class CachedClient:
    def __init__(self, inner, path: str | Path, mode: str = "readwrite"):
        if mode not in ("readwrite", "replay", "off"):
            raise ValueError(f"unknown cache mode {mode!r}")
        self.inner, self.mode = inner, mode
        self.model = inner.model
        self.external = getattr(inner, "external", False)
        self.provider = getattr(inner, "provider", type(inner).__name__)
        self.hits = self.misses = 0
        self._lock = threading.Lock()
        if mode != "off":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(path), check_same_thread=False)
            self._db.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, model TEXT, answer TEXT)")
            self._db.commit()

    @property
    def last(self) -> dict:
        return getattr(self.inner, "last", {})

    @property
    def usage(self) -> dict:
        return getattr(self.inner, "usage", {})

    def _key(self, system: str, user: str, schema: dict) -> str:
        blob = json.dumps([self.model, system, user, schema], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def complete(self, system: str, user: str, json_schema: dict) -> dict:
        if self.mode == "off":
            return self.inner.complete(system, user, json_schema)
        key = self._key(system, user, json_schema)
        with self._lock:
            row = self._db.execute("SELECT answer FROM answers WHERE key = ?", (key,)).fetchone()
        if row:
            self.hits += 1
            return json.loads(row[0])
        if self.mode == "replay":
            raise RuntimeError("replay mode: this question has no stored answer")
        answer = self.inner.complete(system, user, json_schema)
        self.misses += 1
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO answers VALUES (?, ?, ?)",
                             (key, self.model, json.dumps(answer, ensure_ascii=False)))
            self._db.commit()
        return answer
