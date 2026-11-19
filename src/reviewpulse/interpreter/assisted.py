"""Narrow source-locked assisted drafting. No guessed scope or executable model code."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..xeval.verify import wording
from .deterministic import extract_quantities
from .schema import Program, Span
from .structured import SlotDraft, SlotFailure, compile_slots, slots_from_program
from .table_rows import compile_table, fact_request, parse_table_row
from .units import compatible

CUES = yaml.safe_load(Path(__file__).with_name("assisted_scope.yaml").read_text(encoding="utf-8"))


def cue_matches(text, cues):
    return [cue for cue in cues if re.search(rf"(?<!\w){re.escape(cue)}(?!\w)", text, re.I)]


def ratio_quantity(text):
    numbers = {word: value for lang in ("fr", "en") for word, value in wording()[lang]["numbers"].items()}
    numeral = r"(?:\d+(?:[.,]\d+)?|" + "|".join(re.escape(w) for w in sorted(numbers, key=len, reverse=True)) + ")"
    connectors = "|".join(re.escape(c) for c in CUES["ratio_connectors"])
    pattern = rf"(?<!\w)({numeral})(?:\s+[^\W\d_]+){{0,4}}?\s+({connectors})\s+({numeral})(?!\w)"
    found = list(re.finditer(pattern, text, re.I))
    if len(found) != 1:
        return None
    match = found[0]
    def number(value):
        return numbers[value.casefold()] if value.casefold() in numbers else float(value.replace(",", "."))
    numerator, denominator = number(match[1]), number(match[3])
    if denominator <= 0:
        return None
    return {"value": numerator / denominator, "unit": "1", "operator": None,
            "ratio_terms": [numerator, denominator], "quote": match[0], "span": list(match.span())}


def numeric_frame(context):
    target = next(c for c in context.clauses if c.id == context.target)
    source = Span(clause=target.id, start=target.start, end=target.end, quote=target.text).model_dump()
    scan = extract_quantities(target.text)
    ratio = ratio_quantity(target.text)
    evidence = scan["evidence"]
    blockers = []
    if ratio:
        # A proportional phrase alone establishes a ratio, not a minimum/maximum obligation.
        operators = {op for lang in ("fr", "en") for op in ("ge", "le", "gt", "lt")
                     if cue_matches(target.text, wording()[lang].get(op, []))}
        ratio["operator"] = next(iter(operators)) if len(operators) == 1 else None
        evidence = [ratio]
        extra = re.sub(re.escape(ratio["quote"]), "", target.text, count=1)
        if extract_quantities(extra)["evidence"]:
            blockers.append({"reason": "additional_quantity_outside_ratio", "source": source})
    if len(evidence) != 1 or evidence[0].get("unit") is None or evidence[0].get("operator") is None:
        blockers.append({"reason": "requires_one_explicit_comparator_quantity_unit", "source": source})
    measurement = []
    if len(evidence) == 1:
        item = evidence[0]
        measurement = [{"id": "m0", "header": source, "source": source, "value": item["value"],
                        "unit": item["unit"], "operator": item["operator"], "unit_source": "source_sentence",
                        **({"ratio_terms": item["ratio_terms"]} if ratio else {})}]
    return {"kind": "simple_numeric", "measurements": measurement, "metadata_applicability": [],
            "blockers": blockers, "trace": [{"operation": "source_numeric_scan", "source": source,
            "result": scan}, *([{"operation": "explicit_ratio", "source": source, "result": ratio}] if ratio else [])]}


def classify_scope(context, catalogue):
    target = next(c for c in context.clauses if c.id == context.target)
    text = target.text
    if target.kind == "table_row" or "|" in text:
        try:
            frame = parse_table_row(context, catalogue)
        except ValueError as error:
            return {"family": "table-row", "in_scope": False, "reason": str(error), "frame": None}
        return {"family": "table-row", "in_scope": not frame["blockers"], "frame": frame,
                "reason": "; ".join(b["reason"] for b in frame["blockers"])}
    frame = numeric_frame(context)
    for family, key in (("conditional", "conditions"), ("conditional", "scope_markers"), ("relational", "relations"),
                        ("relational", "references")):
        hits = cue_matches(text, CUES[key])
        if hits:
            return {"family": family, "in_scope": False, "reason": "unsupported linguistic cues: " + ", ".join(hits), "frame": frame}
    if cue_matches(text, CUES["connectives"]) or ";" in text:
        return {"family": "conditional", "in_scope": False, "reason": "composed obligation or alternative needs formalization", "frame": frame}
    if frame["measurements"] or extract_quantities(text)["evidence"]:
        return {"family": "simple numeric", "in_scope": not frame["blockers"], "frame": frame,
                "reason": "; ".join(b["reason"] for b in frame["blockers"])}
    return {"family": "qualitative/unsupported", "in_scope": False, "reason": "no supported single numeric predicate", "frame": frame}


def compile_assisted(scope, choices, context, catalogue):
    if not scope["in_scope"]:
        raise SlotFailure("reviewer_formalization", scope["reason"])
    frame = scope["frame"]
    if scope["family"] == "table-row":
        return compile_table(frame, choices, context, catalogue)
    if len(choices.get("choices", [])) != 1 or choices["choices"][0].get("measurement") != "m0":
        raise SlotFailure("fact_link", "one closed fact selection required")
    measurement = frame["measurements"][0]
    name = choices["choices"][0]["fact"]
    spec = catalogue["bindings"].get(name)
    if not spec or spec["kind"] != "number" or not compatible(spec["unit"], measurement["unit"]):
        raise SlotFailure("vocabulary_gap", "no compatible catalogue fact; reviewer formalization required")
    owners = ([catalogue.get("whole") or "building"] if name in catalogue.get("building", []) else []) + [
        key for key, value in catalogue["collections"].items() if name in value.get("facts", [])]
    if len(owners) != 1:
        raise SlotFailure("entity_binding", "selected fact must have one declared owner")
    owner = owners[0]
    target = next(c for c in context.clauses if c.id == context.target)
    collection = catalogue["collections"].get(owner)
    aliases = (collection or catalogue).get("subject_aliases", [owner.replace("_", " ")])
    if not cue_matches(target.text, aliases) or (collection is not None and not cue_matches(target.text, CUES["universal"])):
        raise SlotFailure("entity_binding", "subject/quantifier not established by runtime catalogue aliases")
    expression = {"node": measurement["operator"], "left": {"node": "fact", "name": name,
        "entity": "$member" if collection is not None else owner},
        "right": {"node": "literal", "value": measurement["value"], "unit": measurement["unit"]}}
    if collection is not None:
        expression = {"node": "forall", "collection": owner, "variable": "$member", "body": expression}
    program = Program(id=target.id, title=target.heading or target.id, document=context.document,
        requirement=expression, sources=[Span(clause=target.id, start=target.start, end=target.end, quote=target.text)])
    slots = slots_from_program(program, target.text)
    return compile_slots(SlotDraft.model_validate(slots), context, catalogue), slots


def assisted_draft(context, catalogue, client=None):
    scope = classify_scope(context, catalogue)
    result = {"scope": scope, "status": "UNRESOLVED", "program": None,
              "queue": "reviewer_formalization", "reason": scope["reason"]}
    if not scope["in_scope"]:
        return result
    system, payload, schema = fact_request(scope["frame"], catalogue)
    if not any(header["candidates"] for header in payload["headers"]):
        result["reason"] = "vocabulary_gap: no compatible fact in catalogue"
        return result
    if client is None:
        result["reason"] = "model_unavailable: closed fact selection required"
        return result
    import json
    try:
        choice = client.complete(system, json.dumps(payload, ensure_ascii=False), schema)
        program, slots = compile_assisted(scope, choice, context, catalogue)
        result.update(status="DRAFTED", queue="in_scope_draft", program=program.model_dump(mode="json"),
                      slots=slots, reason="Pending named reviewer approval")
    except ValueError as error:
        result.update(reason=str(error), stage=getattr(error, "stage", "validation"))
    return result
