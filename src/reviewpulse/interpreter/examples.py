"""Offline compound-rule demonstrations, not complete legal formalizations."""

from __future__ import annotations

import copy

from .runtime import run_program
from .schema import Inputs, Program


def _literal(value, unit="1"):
    return {"node": "literal", "value": value, "unit": unit}


def _fact(name, entity="building"):
    return {"node": "fact", "entity": entity, "name": name}


def _binary(node, left, right):
    return {"node": node, "left": left, "right": right}


def _logic(node, *args):
    return {"node": node, "args": list(args)}


def demonstrations() -> list[dict]:
    """Independent expected cases include strict boundaries and missing alternative evidence."""
    inner_requirement = _logic(
        "all",
        _fact("occupancy_ok"),
        _fact("not_bedroom"),
        _fact("direct_access"),
        _fact("single_access_room"),
        _fact("travel_ok"),
        _fact("not_hazard"),
        _fact("same_occupier"),
        _logic("any", _fact("partition_gap_ok"), _fact("vision_panel_ok"), _fact("alarm_ok")),
    )
    inner_values = {
        name: True
        for name in (
            "occupancy_ok",
            "not_bedroom",
            "direct_access",
            "single_access_room",
            "travel_ok",
            "not_hazard",
            "same_occupier",
            "vision_panel_ok",
        )
    }
    inner_values.update(partition_gap_ok=False, alarm_ok=None)
    inner = _example(
        "inner_room",
        "1 Inner-room acceptance requires all stated conditions and at least one warning arrangement.",
        inner_requirement,
        {name: {"kind": "boolean"} for name in inner_values},
        inner_values,
    )
    inner["cases"] = [
        ({}, "SATISFIED"),
        ({"not_bedroom": False}, "VIOLATED"),
        ({"vision_panel_ok": False}, "UNRESOLVED"),
        ({"vision_panel_ok": False, "alarm_ok": False}, "VIOLATED"),
    ]

    def aggregate(node):
        return {"node": node, "collection": "exits", "variable": "$exit", "body": _fact("capacity", "$exit")}

    capacity = _example(
        "exit_capacity",
        "1 Available exit capacity, excluding one largest exit, must accommodate the occupants.",
        _binary("ge", _binary("sub", aggregate("sum"), aggregate("max")), _fact("occupants")),
        {"capacity": {"kind": "number", "unit": "count"}, "occupants": {"kind": "number", "unit": "count"}},
        {"occupants": 150},
    )
    capacity["inputs"]["collections"] = {
        "exits": {"items": ["a", "b", "c"], "complete": True, "trusted": True}
    }
    capacity["inputs"]["facts"].update(
        {
            key: {"capacity": {"value": val, "source": f"fixture:{key}", "trusted": True}}
            for key, val in (("a", 200), ("b", 80), ("c", 80))
        }
    )
    capacity["cases"] = [
        ({}, "SATISFIED"),
        ({"occupants": 160}, "SATISFIED"),
        ({"occupants": 161}, "VIOLATED"),
        ({"occupants": None}, "UNRESOLVED"),
    ]

    values = {
        "vertical_exempt": True,
        "same_decor": True,
        "same_services": True,
        "mezzanine_area": 24,
        "combined_area": 100,
        "route_exists": False,
    }
    bindings = {name: {"kind": "boolean"} for name in values}
    for name in ("mezzanine_area", "combined_area"):
        bindings[name] = {"kind": "number", "unit": "m2"}
    dining = _example(
        "dining_exception",
        "1 A dining area needs an accessible route unless all conditions of the scoped mezzanine exception hold.",
        _fact("route_exists"),
        bindings,
        values,
    )
    dining["program"]["exemption"] = _logic(
        "all",
        _fact("vertical_exempt"),
        _fact("same_decor"),
        _fact("same_services"),
        _binary("lt", _binary("div", _fact("mezzanine_area"), _fact("combined_area")), _literal(0.25)),
    )
    dining["cases"] = [
        ({}, "EXEMPT"),
        ({"mezzanine_area": 25}, "VIOLATED"),
        ({"same_services": None}, "UNRESOLVED"),
        ({"same_services": None, "route_exists": True}, "SATISFIED"),
    ]
    return [inner, capacity, dining]


def _example(name, source, requirement, bindings, values):
    return {
        "name": name,
        "source": source,
        "program": {
            "id": name,
            "title": name.replace("_", " "),
            "document": "illustrative-fixture",
            "requirement": requirement,
            "sources": [{"clause": "1", "start": 0, "end": len(source), "quote": source}],
        },
        "inputs": {
            "bindings": bindings,
            "facts": {
                "building": {
                    name: {"value": value, "source": f"fixture:{name}", "trusted": True}
                    for name, value in values.items()
                }
            },
        },
    }


def run_demonstration(example: dict) -> list[dict]:
    results = []
    for changes, expected in example["cases"]:
        inputs = copy.deepcopy(example["inputs"])
        for name, value in changes.items():
            inputs["facts"]["building"][name]["value"] = value
        result = run_program(
            Program.model_validate(example["program"]), Inputs.model_validate(inputs), include_drafts=True
        )
        results.append(
            {
                "changes": changes,
                "expected": expected,
                "matches": result["outcome"] == expected,
                "result": result,
            }
        )
    return results
