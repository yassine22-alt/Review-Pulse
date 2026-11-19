"""Explicit review repair plans, not edit distance or string-match scores."""
from __future__ import annotations

from collections import Counter

OPERATIONS = {"add_unit", "add_scope_condition", "remove_scope_condition", "rename_fact", "bind_entity",
              "replace_requirement", "rewrite", "correct_value", "supply_fact_link", "clear_unresolved",
              "remove_declaration", "ground_scope_value"}


def edit_bucket(edits: list[dict], *, complete: bool = True) -> str:
    if any(edit.get("operation") not in OPERATIONS or not edit.get("site") for edit in edits):
        raise ValueError("each review edit requires a known operation and an explicit semantic site")
    sites = [(edit["operation"], edit["site"]) for edit in edits]
    if len(set(sites)) != len(sites):
        raise ValueError("duplicate correction sites inflate the minimum-edit estimate")
    if any(edit["operation"] == "rewrite" for edit in edits):
        return "rewrite"
    if not complete:
        return "needs_context"
    return "0" if not edits else "1" if len(edits) == 1 else "2+"


def distribution(rows: list[dict]) -> dict:
    counts = Counter(edit_bucket(row["edits"], complete=row.get("complete", True)) for row in rows)
    return {"denominator": len(rows), **{name: [counts[name], len(rows)] for name in ("0", "1", "2+", "rewrite", "needs_context")}}
