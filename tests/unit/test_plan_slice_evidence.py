import json
from pathlib import Path

import networkx as nx
import pytest

from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Binding, Fact, Inputs, Program


@pytest.fixture
def slice_data():
    data = json.loads((Path(__file__).parents[2] / "reports/plan-answerable-results.json").read_text(encoding="utf-8"))
    return Inputs.model_validate(data["reviewed_facts"]), {row["id"]: Program.model_validate(row["rule"]) for row in data["requirements"]}


def test_incomplete_scope_cannot_pass_but_confirmed_violation_still_fails(slice_data):
    inputs, rules = slice_data
    inputs.collections["reviewed_bedrooms"].complete = False
    assert run_program(rules["area"], inputs)["outcome"] == "UNRESOLVED"
    member = inputs.collections["reviewed_bedrooms"].items[0]
    inputs.facts[member]["area_m2"].value = rules["area"].requirement.body.right.value - 1
    assert run_program(rules["area"], inputs)["outcome"] == "VIOLATED"


def test_unverified_room_evidence_cannot_satisfy_area_rule(slice_data):
    inputs, rules = slice_data
    member = inputs.collections["reviewed_bedrooms"].items[0]
    inputs.facts[member]["area_m2"].trusted = False
    assert run_program(rules["area"], inputs)["outcome"] == "UNRESOLVED"


def test_unknown_room_on_only_confirmed_route_is_unresolved(slice_data):
    inputs, rules = slice_data
    member = inputs.collections["reviewed_bedrooms"].items[0]
    inputs.collections["reviewed_bedrooms"].items = [member]
    hall = inputs.collections["reviewed_halls"].items[0]
    inputs.facts["unknown"] = {"room_type": Fact(value=None, source="Unlabelled intermediate room")}
    graph = nx.MultiGraph()
    for key in (member, hall, "unknown"):
        graph.add_node(key, role="member")
    graph.add_edge(member, "unknown", kind="door", trusted=True)
    graph.add_edge("unknown", hall, kind="door", trusted=True)
    assert run_program(rules["route"], inputs, graph=graph)["outcome"] == "UNRESOLVED"


def test_nominal_size_never_fills_missing_clear_opening(slice_data):
    inputs, rules = slice_data
    door = inputs.collections["reviewed_doors"].items[0]
    inputs.bindings["nominal_width_m"] = Binding(kind="number", unit="m")
    inputs.facts[door]["nominal_width_m"] = Fact(value=1.1, source="Nominal schedule size", trusted=True)
    assert run_program(rules["clear_width"], inputs)["outcome"] == "UNRESOLVED"


def test_partial_sheet_cannot_establish_absence_of_final_exits(slice_data):
    inputs, rules = slice_data
    assert not inputs.collections["final_exits"].complete
    assert run_program(rules["exit_count"], inputs)["outcome"] == "UNRESOLVED"
