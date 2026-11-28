"""The regulation graph as extra context for drafting and evidence.

`assemble_context` follows a clause's numbered references and the definitions of the terms it uses. The regulation graph reads
more of what the document itself says about a clause: references written in words, the tables it cites (with their rows), the
exceptions that attach to it, the clauses that hold its conditions. `with_resolved_context` adds the clauses these links point to
to a `ContextBundle`, so the drafting model can read them.

Nothing about checking is loosened. The clauses added are clauses of the same document with their own offsets, so the bundle
validates exactly as before, and a rule's source quote is still accepted only when it sits inside a clause of the bundle at the
exact offsets (`ContextBundle.check_span`): the clause itself, or one of the clauses its own text cites. A reading model's
sentence that is in neither is refused as before. The target clause, the program checks, the grounding checks and the round trip
read the target clause only (`clause_body`) and are not touched.

Switch: REVIEWPULSE_REGGRAPH=off returns the bundle unchanged.
"""

from __future__ import annotations

import hashlib
import os

from ..interpreter.context import ContextBundle
from .graph import build_graph, resolve_context

MAX_ADDED = 12
_GRAPHS: dict[str, object] = {}


def enabled() -> bool:
    return os.environ.get("REVIEWPULSE_REGGRAPH", "on").strip().lower() != "off"


def _graph(text: str, clauses: list):
    key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest() + str(len(clauses))
    if key not in _GRAPHS:
        if len(_GRAPHS) >= 4:
            _GRAPHS.pop(next(iter(_GRAPHS)))
        _GRAPHS[key] = build_graph(text, clauses)
    return _GRAPHS[key]


def with_resolved_context(context: ContextBundle, clauses: list, depth: int = 1) -> ContextBundle:
    """`context` plus the clauses the regulation graph says the target needs (and the rows of the tables it cites). Any failure
    returns the context as it was."""
    if not enabled():
        return context
    try:
        resolved = resolve_context(_graph(context.text, clauses), context.target, depth=depth)
        have = {c.id for c in context.clauses}
        by_id = {c.id: c for c in clauses}
        wanted = list(resolved.clause_ids())
        for cid in list(wanted):                                  # a cited table brings its rows
            wanted += [c.id for c in clauses if c.parent == cid and c.kind == "table_row"]
        added = [by_id[c] for c in dict.fromkeys(wanted) if c in by_id and c not in have][:MAX_ADDED]
        if not added:
            return context
        merged = sorted([*context.clauses, *added], key=lambda c: c.start)
        return ContextBundle(document=context.document, text=context.text, clauses=merged, target=context.target,
                             missing=context.missing)
    except Exception:  # noqa: BLE001 - extra reading material; the drafting context stands without it
        return context
