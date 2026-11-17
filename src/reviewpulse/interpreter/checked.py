"""Draft a clause the way that measured best: one readable expression, then checks, then UNRESOLVED instead of a guess.

The original `draft_program` asks the model for the whole nested rule structure in one go. On our test sentences that
gave a correct rule in about 1 case in 10. This path asks for a one-line expression, builds the structure in code,
compares the result with the clause (scope, numbers, direction, sums, what is measured) and with the declared facts
(owner, allowed values), gives the model one chance to repair, and otherwise answers UNRESOLVED with a reason.
See docs/progress/M7_rule_extraction_facts_and_stairs.md for the measurements.
"""

from __future__ import annotations

import os
import re
from types import SimpleNamespace

from ..factgraph.convert import to_catalogue
from ..factgraph.schema import FactGraph
from ..rules.clauses import BULLET_LEAD, MODALS
from ..xeval.arms import draft_arm
from ..xeval.expr_ir import to_text
from ..xeval.readback import describe_rule
from ..xeval.status import clause_status
from ..xeval.verify import verify
from .context import ContextBundle
from .quantities import normalise_quantities
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
    text = BULLET_LEAD.sub("", text, count=1)          # a symbol-font bullet is a marker, not part of the requirement
    if clause.kind == "table_row":
        head = next((c for c in context.clauses if c.id == clause.parent and c.kind == "table_header"), None)
        rendered = _row_with_header(head.text, text) if head is not None else None
        if rendered:
            return normalise_quantities(rendered)
    body = strip_title(text.strip())
    # a list item ("- largeur minimale de 0,90 m") has no subject of its own: it belongs to the sentence that introduces the
    # list ("les portes doivent offrir les caractéristiques suivantes :"), so that sentence is read with it
    lead = next((c for c in context.clauses if c.id == clause.parent), None) if clause.kind == "subitem" else None
    if lead is not None and lead.text.rstrip().endswith(":") and lead.kind != "table_header":
        intro = strip_title(lead.text[len(lead.id):].lstrip(" :.-)\t").strip() if lead.text.startswith(lead.id) else lead.text.strip())
        item = re.sub(r"^[-*•–]\s*|^\(?[a-z0-9ivx]{1,4}\)\s*", "", body)
        return normalise_quantities(f"{intro} {item}")
    return normalise_quantities(body)


def is_bare_label(body: str) -> bool:
    """One or two words, no figure and no word of obligation ("Dimensions", "Square Footage", "Compaction"): a heading or a form label,
    not a requirement. Read as one it became "the drawing is dimensioned" or "every room has an area above zero", rules nobody wrote."""
    words = re.findall(r"[^\W\d_]+", body)
    return 0 < len(words) <= 2 and not any(ch.isdigit() for ch in body) and not MODALS.search(body)


def _row_with_header(header: str, row: str) -> str | None:
    """A table row read with the names of its columns: "Bedroom | 7 m2" under "Room | Minimum area" says "Room: Bedroom; Minimum area:
    7 m2". Alone the row says nothing about what 7 m2 is. None when the header does not fit the row (different number of cells, or a
    header that is not a row of names), in which case the row is read as it stands."""
    names = [h.strip() for h in header.strip().strip("|").split("|")]
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    if len(names) != len(cells) or len(names) < 2 or not all(names):
        return None
    if any(len(n.split()) > 8 or re.fullmatch(r"[\d\s.,%()/-]+", n) for n in names):
        return None                                      # a header cell that is a sentence or a number is not a column name
    pairs = [f"{n}: {c}" for n, c in zip(names, cells) if c]
    return "; ".join(pairs) if len(pairs) >= 2 else None


TITLE = re.compile(r"^([^\W\d_][^\W\d_'’-]*(?:\s+[^\W\d_][^\W\d_'’-]*){0,3})\s*[.:]\s+(?=\S)", re.UNICODE)


def strip_title(text: str) -> str:
    """A clause often opens with a short title ("Circulation.", "Dead ends.", "Garage."). A title names the topic, so words
    in it look like categories the rule must mention; it is not part of the requirement, so the checks do not read it. A
    short opening that contains a digit or is the whole text is kept: it may be the requirement itself."""
    m = TITLE.match(text)
    if not m or any(ch.isdigit() for ch in m.group(0)):
        return text
    words = m.group(1).split()
    if MODALS.search(m.group(1)) or words[-1].lower().rstrip(".") in ABBREVIATIONS:
        return text                    # "Hallways must be min." opens the requirement itself; a title never states an obligation
    return text[m.end():].strip()


def checked_draft(context: ContextBundle, inputs: Inputs, graph: FactGraph | None, client, fallback=None,
                  triage: bool = False) -> dict:
    """Draft one clause. `fallback` is an optional second model (a hosted one): it is asked only when `client` could not
    produce a checked rule, and its answer goes through exactly the same checks, so a stronger model needs no extra trust."""
    from ..xeval.terms import document_groups, with_default_groups

    catalogue = catalogue_from(inputs, graph)
    defined = document_groups(context.text, catalogue.get("kinds", {}), catalogue.get("kind_labels", {}))
    catalogue["groups"] = with_default_groups(defined, catalogue.get("kinds", {}))      # the document's own classes win
    body = clause_body(context)
    if is_bare_label(body):
        return {"status": "UNRESOLVED", "arm": "label", "model": getattr(client, "model", None),
                "reason": "a bare heading or label: it names a topic but states no requirement, so there is nothing to check",
                "external": False, "program": None, "readback": None, "notes": [], "tried": []}
    target = next(c for c in context.clauses if c.id == context.target)
    numeric_table = bool(re.search(r"\d", body)) and (
        target.kind == "table_row" or any(line.strip().startswith("|") for line in target.text.splitlines())
    )
    # The triage sees a sentence, not a table. Send numeric rows through checked drafting.
    if triage and not numeric_table:
        from .triage import triage as ask

        ok, why = ask(client, body, catalogue)
        if not ok:
            return {"status": "UNRESOLVED", "reason": f"judged not checkable from a plan: {why}" if why else
                    "judged not checkable from a plan", "arm": "triage", "model": getattr(client, "model", None),
                    "external": bool(getattr(client, "external", False)), "program": None, "readback": None,
                    "notes": [], "triaged": True}
    out = _attempt(context, catalogue, body, client, judge=fallback or client)
    if out["status"] != "DRAFTED" and fallback is not None:
        second = _attempt(context, catalogue, body, fallback, judge=fallback)
        if second["status"] == "DRAFTED":
            second["escalated_from"] = {"model": out["model"], "reason": out["reason"]}
            return second
        out["fallback_tried"] = {"model": second["model"], "reason": second["reason"]}
    if out["status"] != "DRAFTED" and "could not be reached" not in (out.get("reason") or ""):
        # an opaque "no rule could be written" tells a reviewer nothing: one short question says what the sentence seems to need.
        # It explains only; the clause stays declined and no verdict depends on it
        from .triage import explain_decline

        needs = explain_decline(client, body, catalogue)
        if needs:
            out["needs"] = needs
            out["reason"] = f"{out['reason']} (the sentence seems to need: {needs})"
    return out


ABBREVIATIONS = {"min", "max", "no", "approx", "sq", "dia", "vs", "etc", "e.g", "i.e", "nos", "ref"}


def sentences(text: str) -> list[str]:
    """Split a clause into sentences. A full stop after an abbreviation ("min.", "sq. ft.") or before a number ends nothing."""
    out, start = [], 0
    for m in re.finditer(r"[.!?]\s+(?=[A-Z\"'(])", text):
        word = re.search(r"([^\W\d_.]+)$", text[start:m.start()])
        if word and word.group(1).lower() in ABBREVIATIONS:
            continue
        out.append(text[start:m.start() + 1].strip())
        start = m.end()
    out.append(text[start:].strip())
    return [x for x in out if len(x) > 3]


def _plain_arms(item, client, tried: list, label: str = ""):
    for arm, switch in (("expr_slots", "REVIEWPULSE_SLOTS"), ("expr_limits", "REVIEWPULSE_LIMITS"),
                        ("expr_relation", "REVIEWPULSE_RELATIONS")):
        if os.environ.get(switch, "on") == "off":
            continue
        attempt = draft_arm(arm, item, client)
        tried.append(label + f"{arm.removeprefix('expr_')}: " + (
            "wrote a rule" if attempt.program is not None else (attempt.detail or attempt.stage or "declined")[:180]
            + (f" [drafted: {attempt.raw['require'][:150]}]" if isinstance(attempt.raw, dict) and attempt.raw.get("require") else "")))
        if attempt.program is not None:
            return attempt
    return None


def _attempt(context: ContextBundle, catalogue: dict, body: str, client, judge=None) -> dict:
    # `text` is what is read (normalised); `quote` is what a rule cites: the clause as the document wrote it
    quote = next(c.text for c in context.clauses if c.id == context.target)
    item = SimpleNamespace(id=context.target, text=body, catalogue=catalogue, lang=None, ctx=context, quote=quote)
    draft, tried = None, []
    # the arms in order: a limit on one quantity, several limits / an exception / "at least one", how spaces connect; each one
    # declines when the sentence is not its shape, and the free-form arm reads what none of them took
    draft = _plain_arms(item, client, tried)
    rest: list[str] = []
    parts = sentences(body)
    if draft is None and len(parts) > 1:
        # a checklist line often holds several requirements ("1 egress door required min. 32 in. Door must not require a key.").
        # Each sentence is tried on its own; the first that becomes a rule is kept and the others are listed as not checked
        for i, part in enumerate(parts):
            sub = SimpleNamespace(id=item.id, text=part, catalogue=catalogue, lang=None, ctx=context, quote=quote)
            found = _plain_arms(sub, client, tried, label=f"sentence {i + 1}: ")
            if found is not None:
                draft, rest = found, [p for j, p in enumerate(parts) if j != i]
                break
    if draft is None:
        draft = draft_arm("expr_verify", item, client)
        tried.append("free-form: " + ("wrote a rule" if draft.program is not None else (draft.detail or draft.stage or "declined")[:180]))
    status, reason = clause_status(draft)
    out = {"status": status, "reason": reason, "arm": draft.arm, "model": getattr(client, "model", None),
           "external": bool(getattr(client, "external", False)), "program": None, "readback": None, "notes": [], "tried": tried}
    if draft.program is None:
        return out
    program = draft.program
    program.status, program.approved_by, program.document = "draft", None, context.document
    program.id = "I-" + "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in context.target)
    program.unresolved = sorted(set(program.unresolved + context.missing))
    program.not_checked = list(program.not_checked) + rest
    for span in program.sources:
        context.check_span(span)
    dumped = program.model_dump(mode="json")
    out["program"] = dumped
    out["readback"] = to_text(dumped["requirement"])
    if status == "DRAFTED" and os.environ.get("REVIEWPULSE_GROUNDING", "on") != "off":
        from .grounding import check_concern, check_measured

        why = (check_measured(client, body, dumped["requirement"], catalogue.get("bindings", {}))
               or check_concern(client, body, dumped["requirement"], catalogue.get("bindings", {})))
        if why:                      # a valid rule about the wrong quantity is worse than no rule
            out.update(status="UNRESOLVED", reason=f"grounding: {why}", program=None, readback=None)
            return out
    out.update(describe_rule(dumped["requirement"], dumped["applicability"], dumped["exemption"],
                             catalogue.get("bindings", {}), catalogue.get("whole") or "building"))
    if status == "DRAFTED" and os.environ.get("REVIEWPULSE_ROUNDTRIP", "on") != "off":
        from .roundtrip import compare

        verdict = compare(judge or client, body, out.get("plain") or out["readback"], program.not_checked)
        if verdict == "different":              # two answers agree the rule says something else: a wrong rule is worse than none
            out.update(status="UNRESOLVED", program=None, readback=None,
                       reason="round trip: the rule as written is about something different from the sentence, so it was not kept: "
                              + str(out.get("plain") or "")[:200])
            tried.append("round trip: refused")
            return out
        if verdict == "partial":
            out["notes"] = list(out.get("notes") or []) + ["The rule may check only part of this sentence; please read it."]
    out["applies_when"] = to_text(dumped["applicability"])
    out["unless"] = to_text(dumped["exemption"])
    out["notes"] = [i.message for i in verify(program, body, catalogue) if not i.blocking]
    if "silent_direction" in (draft.detail or ""):
        out["notes"].append("The sentence gives a figure but not whether it is a minimum or a maximum. The reading model chose "
                            f"'{draft.detail.rsplit('=', 1)[1]}' the same way twice; please confirm the direction.")
    out["notes"] += [f"Not checked by this rule (the plan does not show it): {part}" for part in program.not_checked]
    return out
