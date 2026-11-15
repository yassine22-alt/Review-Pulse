"""Read and write fact graphs as JSON, and publish the JSON Schema so any producer can target the format."""

from __future__ import annotations

import json
from pathlib import Path

from .schema import FactGraph


def dump(fg: FactGraph, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fg.model_dump_json(indent=1, exclude_none=True), encoding="utf-8")
    return path


def load(path: str | Path) -> FactGraph:
    return FactGraph.model_validate_json(Path(path).read_text(encoding="utf-8"))


def write_json_schema(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(FactGraph.model_json_schema(), indent=1), encoding="utf-8")
    return path
