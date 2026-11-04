"""Stable ids: kind + short hash of the sheet id and geometry rounded to 3 decimals."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def _flatten(obj) -> Iterable[str]:
    if isinstance(obj, (list, tuple)):
        for o in obj:
            yield from _flatten(o)
    elif isinstance(obj, float):
        yield f"{obj:.3f}"
    else:
        yield str(obj)


def stable_id(kind: str, sheet_id: str, *geometry) -> str:
    h = hashlib.sha1("|".join([sheet_id, *_flatten(geometry)]).encode()).hexdigest()[:10]
    return f"{kind}_{h}"


class IdFactory:
    """Guarantees uniqueness when two objects share the same rounded geometry."""

    def __init__(self, sheet_id: str):
        self.sheet_id = sheet_id
        self.seen: dict[str, int] = {}

    def __call__(self, kind: str, *geometry) -> str:
        base = stable_id(kind, self.sheet_id, *geometry)
        n = self.seen.get(base, 0)
        self.seen[base] = n + 1
        return base if n == 0 else f"{base}_{n}"
