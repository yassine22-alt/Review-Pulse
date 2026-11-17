"""Content-addressed obligation results. Availability failures are always retried."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path


def fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ResultCache:
    def __init__(self, directory: Path):
        self.directory = directory

    def get(self, key: str) -> dict | None:
        try:
            stored = json.loads((self.directory / f"{key}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(stored, dict):
            return None
        result = stored.get("result")
        if stored.get("fingerprint") != key or not isinstance(result, dict) or result.get("status") == "API_UNAVAILABLE":
            return None
        return result

    def put(self, key: str, result: dict) -> None:
        if result.get("status") == "API_UNAVAILABLE":
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{key}.json"
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps({"fingerprint": key, "result": result}, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
