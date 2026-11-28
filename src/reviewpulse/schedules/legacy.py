"""The general sheet table reader as the door fire rating source of `annotate/schedules.find_schedules`.

The old reader finds one kind of table by a fixed header pattern. This module reads every table of the sheet with the general
reader (`reader.py`) and merges only the door fire rating into what the old reader found, so the old rows stay as they were:

  * a row the old reader found takes the general value when it has none (and keeps its own when both read one);
  * a door row only the general reader found is kept apart, under `fire_rows` of an extra schedule with no `rows`, so that the
    completeness checks that count schedule rows (`engine/consistency.py`) see exactly what they saw before;
  * a cell that is only a dash is "no rating stated" (unknown), never 0 minutes.

Switch: REVIEWPULSE_SHEET_TABLES=off keeps the old reader alone (and, with it, nothing reads a dash differently).
"""

from __future__ import annotations

import os

from ..annotate.text_classify import tag_key
from .door_fire import door_fire_rows
from .reader import read_sheet_tables


def enabled() -> bool:
    return os.environ.get("REVIEWPULSE_SHEET_TABLES", "on").strip().lower() != "off"


def general_door_fire(sheet) -> dict[str, float]:
    """{tag key: minutes} of the door fire ratings the general reader finds on the sheet; {} when it fails (the old reader stands)."""
    try:
        return {tag_key(k): v for k, v in door_fire_rows(read_sheet_tables(sheet)).items()}
    except Exception:  # noqa: BLE001 - the general reader is an addition; a failure leaves the old result untouched
        return {}


def merge_door_fire(sheet, schedules: list[dict]) -> int:
    """Merge the general door fire ratings into `schedules` (in place). Returns the number of ratings added."""
    if not enabled():
        return 0
    found = general_door_fire(sheet)
    if not found:
        return 0
    added, known = 0, set()
    for sched in schedules:
        for row in sched.get("rows", []):
            key = tag_key(str(row.get("tag", "")))
            known.add(key)
            if key in found and "fire_rating_min" not in row:
                row["fire_rating_min"] = found[key]
                added += 1
    extra = {k: v for k, v in found.items() if k not in known}
    if extra:
        schedules.append({"name": "fire_ratings", "rows": [], "fire_rows": extra})
        added += len(extra)
    return added
