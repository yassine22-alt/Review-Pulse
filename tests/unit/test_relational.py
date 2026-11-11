"""Relational requirements: routes that avoid categories, direct links between rooms, door counts and travel distance."""

import handmade
import pytest

from reviewpulse.factgraph.convert import to_catalogue, to_graph, to_inputs
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.expr_ir import ExprError, compile_expr_program, parse_expression, to_text

SRC = [{"clause": "1", "start": 0, "end": 1, "quote": "x"}]
KINDS = {"room_type": ["bathroom", "bedroom", "corridor", "living"]}


def program_from(require: str, tmp_model=None, kinds=KINDS):
    fg = from_building(tmp_model, complete=True)
    cat = to_catalogue(fg)
    tree = compile_expr_program({"require": require, "sources": [{"clause": "1", "quote": "x"}]}, "d",
                                {n: b for n, b in fg.bindings.items()}, {"building"}, kinds=cat["kinds"])
    tree["sources"] = SRC
    return Program.model_validate(tree), fg


def outcome(require: str, model):
    program, fg = program_from(require, model)
    return run_program(program, to_inputs(fg), include_drafts=True, graph=to_graph(fg))["outcome"]


def test_avoiding_names_categories_and_the_filter_is_built_from_declared_values():
    tree = compile_expr_program({"require": "forall rooms r: reaches(r, EXIT, avoiding 'bathroom', 'bedroom')",
                                 "sources": []}, "d", {}, set(), kinds=KINDS)
    path = tree["requirement"]["body"]
    assert path["node"] == "path_exists" and path["node_filter"]["node"] == "all"
    assert {a["right"]["value"] for a in path["node_filter"]["args"]} == {"bathroom", "bedroom"}
    assert path["node_filter"]["args"][0]["left"] == {"node": "fact", "entity": "$node", "name": "room_type"}


def test_a_value_no_category_declares_is_refused():
    with pytest.raises(ExprError, match="no category fact declares"):
        compile_expr_program({"require": "forall rooms r: reaches(r, EXIT, avoiding 'garage')", "sources": []},
                             "d", {}, set(), kinds=KINDS)


def test_linked_round_trips():
    text = "forall rooms a: forall rooms b: not linked(a, b)"
    node = parse_expression(text)
    assert to_text(node) == text and parse_expression(to_text(node)) == node


def test_a_route_may_not_pass_through_a_bathroom_and_the_start_room_is_never_blocked():
    # bedroom B can only leave through the bathroom
    bad = handmade.build(bed_b_via_bath=True)
    good = handmade.build(bed_b_via_bath=False)
    rule = "forall rooms r where r.room_type == 'bedroom': reaches(r, EXIT, avoiding 'bathroom')"
    assert outcome(rule, bad) == "VIOLATED"
    assert outcome(rule, good) == "SATISFIED"
    # avoiding every bedroom must still let a bedroom leave: only the rooms passed through are limited
    assert outcome("forall rooms r where r.room_type == 'bedroom': reaches(r, EXIT, avoiding 'bedroom')", good) == "SATISFIED"


def test_a_direct_link_between_two_categories():
    model = handmade.build(bed_b_via_bath=True)
    # the bathroom and the corridor are joined by a door; bedroom B and the bathroom too in this variant
    joined = ("exists rooms a where a.room_type == 'bathroom': exists rooms b where b.room_type == 'corridor': linked(a, b)")
    never = ("forall rooms a where a.room_type == 'bedroom': forall rooms b where b.room_type == 'living': not linked(a, b)")
    assert outcome(joined, model) == "SATISFIED"
    assert outcome(never, model) == "SATISFIED"
    assert outcome("forall rooms a where a.room_type == 'bedroom': forall rooms b where b.room_type == 'bathroom': "
                   "not linked(a, b)", model) == "VIOLATED"


def test_connection_counts_routes_and_travel_distance_are_facts_of_each_room():
    model = handmade.build()
    fg = from_building(model, complete=True)
    rooms = {n.id: n.attrs for n in fg.nodes if n.kind == "room"}
    assert rooms["bedA"]["links_door"].value == 1 and rooms["hall"]["links_passable"].value == 3
    assert all(rooms[r]["reaches_exit"].value is True for r in rooms)
    assert 5 < rooms["bedB"]["exit_distance_m"].value < 30 and rooms["bedB"]["exit_distance_m"].trusted
    assert [n for n in fg.nodes if n.role == "whole"][0].attrs["links_to_exit"].value == 1
    # "a room with a single door has a window", "at most 15 m to an exit"
    assert outcome("forall rooms r: r.links_door != 1 or r.has_window", model) == "SATISFIED"
    assert outcome("forall rooms r: r.exit_distance_m <= 9 m", model) == "VIOLATED"
    assert outcome("forall rooms r: r.exit_distance_m <= 15 m", model) == "SATISFIED"


def test_distances_are_unknown_without_a_scale():
    model = handmade.build()
    model.sheet.scale.metres_per_unit = None
    fg = from_building(model, complete=True)
    assert "exit_distance_m" not in {k for n in fg.nodes if n.kind == "room" for k in n.attrs}


def test_the_relational_layer_knows_nothing_about_buildings():
    """A water network: tanks and valves joined by pipes and a cable, an outlet as the boundary. Same facts, same rules."""
    from reviewpulse.factgraph.relations import derive_relations
    from reviewpulse.factgraph.schema import Edge, FactGraph, Inventory, Node
    from reviewpulse.interpreter.schema import Binding, Fact

    def kind_of(value):
        return {"kind": Fact(value=value, source="survey", trusted=True)}

    fg = FactGraph(
        bindings={"kind": Binding(kind="string", description="Component type")},
        nodes=[Node(id="t1", kind="component", attrs=kind_of("tank")), Node(id="v1", kind="component", attrs=kind_of("valve")),
               Node(id="t2", kind="component", attrs=kind_of("tank")), Node(id="OUTLET", kind="outlet", role="boundary"),
               Node(id="net", kind="network", role="whole")],
        edges=[Edge(id="e1", a="t1", b="v1", kind="pipe", trusted=True), Edge(id="e2", a="v1", b="OUTLET", kind="pipe", trusted=True),
               Edge(id="e3", a="t2", b="t1", kind="cable", trusted=True)],
        inventory={"component": Inventory(complete=True, trusted=True)}, graph_complete=True,
        value_labels={"kind": {"tank": ["tank"], "valve": ["valve"]}}, passable=["pipe"])
    fg = derive_relations(fg)
    nodes = {n.id: n.attrs for n in fg.nodes}
    assert nodes["t1"]["links_pipe"].value == 1 and nodes["t1"]["links_cable"].value == 1
    assert nodes["t1"]["reaches_outlet"].value is True
    assert nodes["t2"]["reaches_outlet"].value is False and nodes["t2"]["reaches_outlet"].trusted   # a cable is not a pipe
    assert nodes["net"]["links_to_outlet"].value == 1
    cat = to_catalogue(fg)
    assert cat["boundaries"] == ["OUTLET"] and cat["passable"] == ["pipe"]
    tree = compile_expr_program(
        {"require": "forall components c where c.kind == 'tank': reaches(c, OUTLET, avoiding 'valve')",
         "sources": [{"clause": "1", "quote": "x"}]}, "d", fg.bindings, set(), kinds=cat["kinds"], passable=cat["passable"])
    tree["sources"] = SRC
    program = Program.model_validate(tree)
    result = run_program(program, to_inputs(fg), include_drafts=True, graph=to_graph(fg))
    assert result["outcome"] == "VIOLATED"          # tank 1 reaches the outlet only through the valve
