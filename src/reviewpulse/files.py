"""Files that one part of the app rewrites while another reads them: a reader sees the old file or the new one, never a part."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

PATIENCE_S = 10.0


def _retry(act):
    """Windows refuses to replace (or for an instant to open) a file another handle holds: wait a little longer each time."""
    end, pause = time.monotonic() + PATIENCE_S, 0.005
    while True:
        try:
            return act()
        except PermissionError:
            if time.monotonic() >= end:
                raise
            time.sleep(pause)
            pause = min(pause * 1.5, 0.2)


def replace(tmp: Path, dst: Path) -> None:
    """Atomic rename of ``tmp`` over ``dst``."""
    _retry(lambda: tmp.replace(dst))


def publish(path: Path, data: bytes) -> None:
    """Write the file whole under a name of its own, then put it in place in one step."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_bytes(data)
        replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_whole(path: Path) -> bytes:
    """All the bytes of a published file."""
    return _retry(path.read_bytes)
