"""Answerability triage: can this sentence be decided from what the plan reader provides? One short question to the model
before the long drafting call.

Why: a real standard has hundreds of clauses and most do not concern a drawing (permits, materials, signage text, who may
sign). Drafting each one costs 30 to 70 seconds on a local model and almost always ends in "not checkable". A short yes/no
costs a few seconds and the answer is understood in any language, so there is no keyword list to keep per language.

What it must never do: hide a requirement. So a "no" is not a silent skip. The clause stays in the list with the reason in
plain words ("judged not checkable from a plan: ..."), the reviewer can read it anyway, and the coverage report counts it as
not checked. When the model's answer is unusable the clause is read normally (triage only ever removes work, never adds a
verdict).
"""

from __future__ import annotations

import json

SYSTEM = """You decide whether one sentence from a requirements document can be CHECKED ON A DRAWING of a building plan.

The plan reader provides only: which spaces, openings, circulation elements and their connections exist, their sizes, areas,
counts, distances and positions, the text labels written on the drawing, and the scale and sheet information.

Answer checkable = true when the sentence states something about those things (a size, an area, a count, a distance, a
presence or absence, a connection or route between spaces, a label that must exist) that a plan could show or violate.

Answer checkable = false when the sentence is about something a plan does not show: administrative or legal process, who may
do what, permits, fees, dates, materials and their performance, products and installation details, maintenance, signage text,
other drawing sheets, definitions, introductions, or intentions with no measurable content.

When unsure, answer true: a wrong "false" hides a requirement, a wrong "true" only costs time.
Reply with JSON only: {"checkable": true or false, "reason": "one short phrase in the language of the sentence"}."""

SCHEMA = {"type": "object", "properties": {"checkable": {"type": "boolean"}, "reason": {"type": "string"}},
          "required": ["checkable", "reason"]}


def provided(catalogue: dict) -> str:
    """What this plan provides, in a line: the kinds of thing and the facts each one has."""
    parts = []
    for name, coll in (catalogue.get("collections") or {}).items():
        parts.append(f"{name} ({', '.join((coll.get('facts') or [])[:8])})")
    whole = catalogue.get("whole") or "building"
    if catalogue.get("building"):
        parts.append(f"the {whole} as a whole ({', '.join(catalogue['building'][:8])})")
    return "; ".join(parts)


def triage(client, text: str, catalogue: dict) -> tuple[bool, str]:
    """(checkable, reason). Any failure to get a usable answer is (True, "") so that the clause is read normally."""
    user = json.dumps({"sentence": text[:1200], "the plan provides": provided(catalogue)}, ensure_ascii=False)
    try:
        out = client.complete(SYSTEM, user, SCHEMA)
    except Exception:  # noqa: BLE001 - never lose a clause because the quick question failed
        return True, ""
    if not isinstance(out, dict) or not isinstance(out.get("checkable"), bool):
        return True, ""
    return out["checkable"], str(out.get("reason") or "")[:160]


EXPLAIN_SYSTEM = """A sentence from a requirements document could not be turned into a rule that a plan drawing can be checked against.
The plan reader provides only the spaces, openings, circulation elements, their sizes, areas, counts, distances and positions, the
text labels on the drawing and the scale. In a few words, in the language of the sentence, say what the sentence needs that the
plan reader does not provide (for example: a fire rating note, alarm symbols, stair landings, handrails, appliance clearances,
structural details, site information, a document or form). If it needs nothing the drawing could show, answer "not about the
drawing". Reply with JSON only: {"needs": "a short phrase"}."""

EXPLAIN_SCHEMA = {"type": "object", "properties": {"needs": {"type": "string"}}, "required": ["needs"]}


def explain_decline(client, text: str, catalogue: dict) -> str:
    """A short phrase on what a declined sentence needs, or "" when no usable answer came back. It only EXPLAINS: it never turns a
    decline into a rule and never decides a verdict, so a wrong phrase costs a reviewer a moment and nothing else."""
    user = json.dumps({"sentence": text[:1200], "the plan provides": provided(catalogue)}, ensure_ascii=False)
    try:
        out = client.complete(EXPLAIN_SYSTEM, user, EXPLAIN_SCHEMA)
    except Exception:  # noqa: BLE001 - an explanation is optional
        return ""
    needs = out.get("needs") if isinstance(out, dict) else None
    return " ".join(str(needs).split())[:140] if isinstance(needs, str) else ""
