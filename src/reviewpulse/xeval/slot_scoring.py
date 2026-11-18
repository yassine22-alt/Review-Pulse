"""Score emitted fields before validation; retention is a different measurement."""
from __future__ import annotations

import json
import unicodedata
from collections import Counter

from ..interpreter.units import parse_unit
from .expr_ir import parse_expression

SLOTS = ("subject", "fact", "operator", "value", "unit", "applicability", "clause_span")


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def partial_json(text: str):
    """Keep completed fields/items in truncated JSON, never invent a closing value."""
    decoder = json.JSONDecoder()

    def read(pos):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return None, pos, False
        if text[pos] not in "[{":
            try:
                value, end = decoder.raw_decode(text, pos)
                return value, end, True
            except ValueError:
                return None, pos, False
        obj = text[pos] == "{"
        result = {} if obj else []
        closing = "}" if obj else "]"
        pos += 1
        while pos < len(text):
            while pos < len(text) and (text[pos].isspace() or text[pos] == ","):
                pos += 1
            if pos < len(text) and text[pos] == closing:
                return result, pos + 1, True
            key = None
            if obj:
                key, pos, complete = read(pos)
                if not complete or not isinstance(key, str):
                    break
                while pos < len(text) and text[pos].isspace():
                    pos += 1
                if pos >= len(text) or text[pos] != ":":
                    break
                pos += 1
            value, end, complete = read(pos)
            if complete or isinstance(value, (list, dict)):
                if obj:
                    result[key] = value
                else:
                    result.append(value)
            if not complete:
                break
            pos = end
        return result, pos, False

    return read(0)[0]


def flat_nodes(raw: dict) -> list[dict]:
    if isinstance(raw.get("nodes"), list):
        return [node for node in raw["nodes"] if isinstance(node, dict)]
    if isinstance(raw.get("require"), str):
        nodes = []

        def visit(node):
            if isinstance(node, dict):
                if "node" in node:
                    nodes.append({**node, "op": node["node"]})
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        for field in ("require", "applies_when", "unless"):
            try:
                visit(parse_expression(raw.get(field) or "true", {"building"}))
            except ValueError:
                continue
        return nodes
    return []


def quantity(node):
    value, symbol = node.get("value"), node.get("unit") or "1"
    try:
        unit = parse_unit(symbol)
        return (round(float(value) * unit.factor + unit.offset, 9), repr(unit.dims), "count" if symbol == "count" else "physical")
    except (ValueError, TypeError, AttributeError):
        return (str(value), "invalid", str(symbol))


def fields(raw: dict) -> dict:
    nodes = flat_nodes(raw)
    owners = {node.get("variable"): node.get("collection") for node in nodes if node.get("variable")}
    facts = [(owners.get(node.get("entity"), node.get("entity")), node.get("name"))
             for node in nodes if node.get("op") == "fact"]
    literals = [node for node in nodes if node.get("op") == "literal" and type(node.get("value")) in (int, float)]
    metadata = []
    for condition in raw.get("metadata_applicability", []):
        if not isinstance(condition, dict):
            continue
        value = quantity(condition) if condition.get("kind") == "number" else norm(condition.get("value"))
        metadata.append((condition.get("field"), condition.get("operator"), condition.get("kind"), value))
    strings = [norm(node["value"]) for node in nodes if node.get("op") == "literal" and isinstance(node.get("value"), str)]
    return {"subject": norm(raw.get("subject", "")), "fact": Counter(set(facts)),
            "operator": Counter(set(node.get("op") for node in nodes if node.get("op") not in ("literal", "fact", None))),
            "value": Counter({*(quantity(node)[0] for node in literals), *strings}),
            "unit": Counter(set(quantity(node)[1:] for node in literals)),
            "applicability": Counter(metadata),
            "clause_span": Counter(set((source.get("clause"), norm(source.get("quote", "")))
                                        for source in raw.get("sources", []) if isinstance(source, dict)))}


def score_slots(raw: dict, gold: dict, annotation: dict, *, subject_requested: bool = True) -> dict:
    expected = {**gold["slots"], "metadata_applicability": annotation["conditions"]}
    a, b = fields(raw), fields(expected)
    result = {}
    for slot in SLOTS:
        eligible = (bool(b[slot]) if slot != "applicability" else annotation["annotated"])
        if slot == "subject":
            eligible = subject_requested
            matched = a[slot] in {norm(value) for value in annotation["subject_accept"]}
            hits, expected_n, predicted_n = int(matched), 1, int(bool(a[slot]))
        else:
            matched = a[slot] == b[slot]
            hits = sum((a[slot] & b[slot]).values())
            expected_n, predicted_n = sum(b[slot].values()), sum(a[slot].values())
        result[slot] = {"eligible": eligible, "exact": bool(matched) if eligible else None,
                        "matched_atoms": hits, "gold_atoms": expected_n, "predicted_atoms": predicted_n}
    return result


def totals(rows: list[dict]) -> dict:
    result = {}
    for slot in SLOTS:
        values = [row[slot] for row in rows if row[slot]["eligible"]]
        correct = sum(value["exact"] for value in values)
        result[slot] = {"correct": correct, "denominator": len(values),
                        "accuracy": correct / len(values) if values else None,
                        "matched_atoms": sum(value["matched_atoms"] for value in values),
                        "gold_atoms": sum(value["gold_atoms"] for value in values),
                        "predicted_atoms": sum(value["predicted_atoms"] for value in values)}
    return result
