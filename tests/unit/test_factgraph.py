"""The fact graph format: generality (no building assumption), compatibility with the existing adapter, safety."""

import handmade
import pytest

from reviewpulse.factgraph import FactGraph, to_catalogue, to_graph, to_inputs
from reviewpulse.factgraph import io as fio
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.building import building_graph, building_inputs
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Binding, Fact, Program
from reviewpulse.xeval.synth import binary, fact, lit, setop
from reviewpulse.xeval.world import bindings_of

SRC = [{"clause": "1", "start": 0, "end": 1, "quote": "x"}]


def program(requirement, **extra):
    return Program.model_validate({"id": "p", "title": "p", "document": "d", "requirement": requirement,
                                   "sources": SRC, **extra})


def bridge() -> FactGraph:
    """A subject that is not a building at all: spans of a footbridge, declared by whoever produced the file."""
    def f(value, trusted=True):
        return Fact(value=value, source="survey", trusted=trusted)

    return FactGraph(
        bindings={"depth_m": Binding(kind="number", unit="m", description="Girder depth"),
                  "length_m": Binding(kind="number", unit="m", description="Span length"),
                  "load_class": Binding(kind="number", unit="count", description="Design load class")},
        nodes=[
            {"id": "structure", "kind": "bridge", "role": "whole", "attrs": {"load_class": f(3)}},
            {"id": "sp1", "kind": "span", "attrs": {"depth_m": f(0.45), "length_m": f(9.0)}},
            {"id": "sp2", "kind": "span", "attrs": {"depth_m": f(0.28), "length_m": f(7.5)}},
            {"id": "sp3", "kind": "span", "attrs": {"depth_m": f(None, False), "length_m": f(6.0)}},
        ],
        edges=[{"id": "j1", "a": "sp1", "b": "sp2", "kind": "joint", "trusted": True}],
        inventory={"span": {"complete": True, "trusted": True}})


def test_a_non_building_subject_works_with_no_special_casing():
    inputs = to_inputs(bridge())
    rule = program(setop("forall", "spans", binary("ge", fact("depth_m"), lit(0.3, "m"))))
    # sp2 is too shallow, sp3 unknown: a known failure decides it
    assert run_program(rule, inputs, include_drafts=True)["outcome"] == "VIOLATED"
    only_ok = inputs.model_copy(deep=True)
    only_ok.collections["spans"].items = ["sp1", "sp3"]
    # the unknown depth must not become a pass
    assert run_program(rule, only_ok, include_drafts=True)["outcome"] == "UNRESOLVED"


def test_whole_subject_facts_and_catalogue_for_the_drafter():
    cat = to_catalogue(bridge())
    assert cat["whole"] == "structure" and cat["building"] == ["load_class"]
    assert cat["collections"] == {"spans": {"facts": ["depth_m", "length_m"]}}
    assert set(bindings_of(cat)) == {"depth_m", "length_m", "load_class"}


def test_json_round_trip_and_published_schema(tmp_path):
    fg = bridge()
    assert fio.load(fio.dump(fg, tmp_path / "g.json")) == fg
    assert "nodes" in fio.write_json_schema(tmp_path / "s.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("tier", ["T1", "T2"])
def test_building_producer_matches_the_existing_interpreter_adapter(tier):
    model = handmade.build(tier=tier)
    new, old = to_inputs(from_building(model)), building_inputs(model)
    for entity, facts in old.facts.items():
        for name, fact_ in facts.items():
            if fact_.value is None:
                continue
            assert new.facts[entity][name].value == fact_.value, (entity, name)
            assert new.facts[entity][name].trusted == fact_.trusted, (entity, name, tier)
    for name, coll in old.collections.items():
        assert new.collections[name].items == coll.items
        assert new.collections[name].trusted == coll.trusted
    g_old, g_new = building_graph(model), to_graph(from_building(model))
    assert sorted(g_old.edges(data="kind")) == sorted(g_new.edges(data="kind"))


def test_routes_run_on_the_exported_graph():
    """Bed B can only leave through the bathroom, which a route rule forbids: decided on the new format."""
    model = handmade.build(bed_b_via_bath=True)
    fg = from_building(model, complete=True)
    route = {"node": "path_exists", "origin": "bedB", "destination": "EXIT", "via_edges": ["door"],
             "node_filter": binary("ne", fact("room_type", "$node"), lit("bathroom"))}
    result = run_program(program(route), to_inputs(fg), include_drafts=True, graph=to_graph(fg))
    assert result["outcome"] == "VIOLATED"
    fixed = from_building(handmade.build(bed_b_via_bath=False), complete=True)
    result = run_program(program(route), to_inputs(fixed), include_drafts=True, graph=to_graph(fixed))
    assert result["outcome"] == "SATISFIED"


def test_lower_tier_measurements_are_untrusted_so_a_rule_cannot_fail_on_them():
    fg = from_building(handmade.build(tier="T3"))
    assert all(not f.trusted for n in fg.nodes for name, f in n.attrs.items() if name == "area_m2")
    rule = program(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(100, "m2"))))
    assert run_program(rule, to_inputs(fg), include_drafts=True)["outcome"] == "UNRESOLVED"


def test_the_format_rejects_inconsistent_files():
    base = bridge().model_dump()
    with pytest.raises(ValueError, match="unknown node"):
        FactGraph.model_validate({**base, "edges": [{"id": "x", "a": "sp1", "b": "nowhere", "kind": "joint"}]})
    bad = bridge().model_dump()
    bad["nodes"][1]["attrs"]["secret"] = {"value": 1, "source": "s"}
    with pytest.raises(ValueError, match="not declared"):
        FactGraph.model_validate(bad)
    wrong = bridge().model_dump()
    wrong["nodes"][1]["attrs"]["depth_m"]["value"] = "deep"
    with pytest.raises(ValueError, match="should be number"):
        FactGraph.model_validate(wrong)
