"""The door fire rating of the door schedule as a special case of the general reader: the candidates of meaning fire_rating
of a table of doors. Same shape as the rows of annotate/schedules.py (`tag`, `fire_rating_min`) so that it can be compared."""

from __future__ import annotations

from .model import Candidate, TypedTable


def door_fire_candidates(tables: list[TypedTable]) -> list[Candidate]:
    return [c for t in tables for c in t.candidates if c.meaning == "fire_rating" and c.entity_kind in ("doors", "other")
            and c.entity_tag and isinstance(c.value, float | int)]


def door_fire_rows(tables: list[TypedTable]) -> dict[str, float]:
    """{tag key: minutes} for every door row with a readable fire rating."""
    return {c.entity_tag: float(c.value) for c in door_fire_candidates(tables)}
