"""A short, plain summary of the drawing set model for the review pack and the coverage report. Information only: no verdict
and no rule reads it.

Switch: REVIEWPULSE_DRAWINGSET=on builds it from the project's PDF plan (off by default, because it reads every page).
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from .model import DrawingSet


def enabled() -> bool:
    return os.environ.get("REVIEWPULSE_DRAWINGSET", "off").strip().lower() == "on"


def summarise(ds: DrawingSet) -> dict:
    """Views per sheet, how callouts resolved, and where the sheet index and the title blocks disagree."""
    callouts = Counter(c.status for c in ds.callouts)
    return {
        "name": ds.name,
        "sheets": [{"index": s.index, "number": s.number, "title": s.title, "views": len(s.views),
                    "kinds": dict(Counter(v.kind for v in s.views))} for s in ds.sheets],
        "views": len(ds.views()),
        "callouts": {"total": len(ds.callouts), "by_status": dict(callouts),
                     "resolved": callouts.get("view", 0) + callouts.get("sheet", 0)},
        "index": {"entries": len(ds.index), "mismatches": [{"number": i.number, "title": i.title, "status": i.status}
                                                           for i in ds.index if i.status and i.status != "match"],
                  "sheets_missing_from_index": list(ds.index_missing)},
    }


def summary_for_pdf(path: str | Path) -> dict | None:
    """The summary of a PDF plan, or None when it is not a PDF or cannot be read (the report then simply has no such section)."""
    from .build import build_from_pdf

    if Path(path).suffix.lower() != ".pdf":
        return None
    try:
        return summarise(build_from_pdf(path))
    except Exception:  # noqa: BLE001 - information only
        return None


def html_block(summary: dict | None, esc=str) -> str:
    if not summary:
        return ""
    c, i = summary["callouts"], summary["index"]
    rows = "".join(f"<li>Sheet {esc(s['number'] or s['index'] + 1)}: {esc(s['title'] or '')} - {s['views']} view(s)</li>"
                   for s in summary["sheets"])
    mism = "".join(f"<li>{esc(m['number'])} {esc(m['title'])}: {esc(m['status'])}</li>" for m in i["mismatches"])
    return (f'<h2>Drawing set (information only)</h2><p class="muted">{summary["views"]} views on {len(summary["sheets"])} sheets; '
            f'{c["resolved"]} of {c["total"]} callouts resolved to a view or sheet; {len(i["mismatches"])} index entries do not match '
            f'a title block.</p><ul>{rows}</ul>' + (f"<ul>{mism}</ul>" if mism else ""))
