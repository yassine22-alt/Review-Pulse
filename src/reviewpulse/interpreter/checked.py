"""Draft regulations as typed slots. Triage is advisory and every verdict requires approval."""

from __future__ import annotations

import re

from ..factgraph.convert import to_catalogue
from ..factgraph.schema import FactGraph
from ..rules.clauses import BULLET_LEAD, MODALS
from .context import ContextBundle
from .quantities import normalise_quantities
from .schema import Inputs


def catalogue_from(inputs: Inputs, graph: FactGraph | None) -> dict:
    """What the drafter may refer to. The fact graph gives categories and their words too; bare inputs give names only."""
    from .metadata import metadata_vocabulary

    if graph is not None:
        return {**to_catalogue(graph), "metadata_vocabulary": metadata_vocabulary()}
    collections = {}
    for name, coll in inputs.collections.items():
        facts = sorted({f for item in coll.items for f in inputs.facts.get(item, {})})
        collections[name] = {"facts": facts}
    return {"metadata_vocabulary": metadata_vocabulary(),
            "collections": collections, "building": sorted(inputs.facts.get("building", {})), "whole": "building",
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
    opinion = None
    if triage:
        from .triage import triage as ask

        ok, why = ask(client, body, catalogue)
        opinion = {"checkable": ok, "reason": why, "advisory": True}
    out = _attempt(context, catalogue, body, client)
    if out["status"] != "DRAFTED" and not out.get("program") and fallback is not None:
        second = _attempt(context, catalogue, body, fallback)
        if second["status"] == "DRAFTED":
            second["escalated_from"] = {"model": out["model"], "reason": out["reason"]}
            second["triage"] = opinion
            return second
        out["fallback_tried"] = {"model": second["model"], "reason": second["reason"]}
    if out.get("evidence_requests"):
        out["needs"] = "; ".join(request["fact"] for request in out["evidence_requests"])
    out["triage"] = opinion
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


def _attempt(context: ContextBundle, catalogue: dict, body: str, client) -> dict:
    from .structured import draft_structured

    return draft_structured(context, catalogue, body, client)
