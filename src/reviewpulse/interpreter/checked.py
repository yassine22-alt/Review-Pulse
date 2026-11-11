"""Draft a clause the way that measured best: one readable expression, then checks, then UNRESOLVED instead of a guess.

The original `draft_program` asks the model for the whole nested rule structure in one go. On our test sentences that
gave a correct rule in about 1 case in 10. This path asks for a one-line expression, builds the structure in code,
compares the result with the clause (scope, numbers, direction, sums, what is measured) and with the declared facts
(owner, allowed values), gives the model one chance to repair, and otherwise answers UNRESOLVED with a reason.
See docs/progress/M7_rule_extraction_facts_and_stairs.md for the measurements.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from ..factgraph.convert import to_catalogue
from ..factgraph.schema import FactGraph
from ..xeval.arms import draft_arm
from ..xeval.expr_ir import to_text
from ..xeval.readback import describe_rule
from ..xeval.status import clause_status
from ..xeval.verify import verify
from .context import ContextBundle
from .schema import Inputs


def catalogue_from(inputs: Inputs, graph: FactGraph | None) -> dict:
    """What the drafter may refer to. The fact graph gives categories and their words too; bare inputs give names only."""
    if graph is not None:
        return to_catalogue(graph)
    collections = {}
    for name, coll in inputs.collections.items():
        facts = sorted({f for item in coll.items for f in inputs.facts.get(item, {})})
        collections[name] = {"facts": facts}
    return {"collections": collections, "building": sorted(inputs.facts.get("building", {})), "whole": "building",
            "bindings": {n: b.model_dump() for n, b in inputs.bindings.items()}, "kinds": {}, "kind_labels": {}}


def clause_body(context: ContextBundle) -> str:
    clause = next(c for c in context.clauses if c.id == context.target)
    text = clause.text
    if text.startswith(clause.id):
        text = text[len(clause.id):].lstrip(" :.-)\t")
    return strip_title(text.strip())


TITLE = re.compile(r"^([^\W\d_][^\W\d_'’-]*(?:\s+[^\W\d_][^\W\d_'’-]*){0,3})\s*[.:]\s+(?=\S)", re.UNICODE)


def strip_title(text: str) -> str:
    """A clause often opens with a short title ("Circulation.", "Dead ends.", "Garage."). A title names the topic, so words
    in it look like categories the rule must mention; it is not part of the requirement, so the checks do not read it. A
    short opening that contains a digit or is the whole text is kept: it may be the requirement itself."""
    m = TITLE.match(text)
    return text[m.end():].strip() if m and not any(ch.isdigit() for ch in m.group(0)) else text


def checked_draft(context: ContextBundle, inputs: Inputs, graph: FactGraph | None, client) -> dict:
    from ..xeval.terms import document_groups

    catalogue = catalogue_from(inputs, graph)
    catalogue["groups"] = document_groups(context.text, catalogue.get("kinds", {}), catalogue.get("kind_labels", {}))
    body = clause_body(context)
    item = SimpleNamespace(id=context.target, text=body, catalogue=catalogue, lang=None, ctx=context)
    draft = draft_arm("expr_verify", item, client)
    status, reason = clause_status(draft)
    out = {"status": status, "reason": reason, "arm": "expr_verify", "model": getattr(client, "model", None),
           "program": None, "readback": None, "notes": []}
    if draft.program is None:
        return out
    program = draft.program
    program.status, program.approved_by, program.document = "draft", None, context.document
    program.id = "I-" + "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in context.target)
    program.unresolved = sorted(set(program.unresolved + context.missing))
    for span in program.sources:
        context.check_span(span)
    dumped = program.model_dump(mode="json")
    out["program"] = dumped
    out["readback"] = to_text(dumped["requirement"])
    out.update(describe_rule(dumped["requirement"], dumped["applicability"], dumped["exemption"],
                             catalogue.get("bindings", {}), catalogue.get("whole") or "building"))
    out["applies_when"] = to_text(dumped["applicability"])
    out["unless"] = to_text(dumped["exemption"])
    out["notes"] = [i.message for i in verify(program, body, catalogue) if not i.blocking]
    return out
