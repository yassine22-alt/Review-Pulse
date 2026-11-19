"""Content-addressed obligation results. Availability failures are always retried."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path


def fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@contextmanager
def exclusive_run(output: Path):
    """One worker per resumable report; OS releases the lock even after a crash."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_suffix(output.suffix + ".lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("This report already has a running worker; resume only after it exits") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
