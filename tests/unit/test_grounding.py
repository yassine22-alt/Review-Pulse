"""The multiple choice grounding check: a valid rule about the wrong quantity is refused, and no answer never blocks a rule."""

from reviewpulse.interpreter.grounding import agrees, check_measured, measured_facts

BINDINGS = {"exit_distance_m": {"kind": "number", "description": "travel distance from the room to the outside (m)"},
            "area_m2": {"kind": "number", "description": "floor area (m2)"},
            "reaches_exit": {"kind": "boolean", "description": "has a route to the exit"}}
RULE = {"node": "forall", "collection": "rooms", "variable": "$r",
        "body": {"node": "lt", "left": {"node": "fact", "entity": "$r", "name": "exit_distance_m"},
                 "right": {"node": "literal", "value": 1.3, "unit": "m"}}}


class Says:
    """A model that answers with a fixed sequence of choices."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), 0

    def complete(self, system, user, schema):
        self.calls += 1
        a = self.answers.pop(0) if self.answers else self.answers_last
        if isinstance(a, Exception):
            raise a
        return {"fact": a}

    answers_last = "none"


def test_measured_facts_are_the_quantities_compared_with_a_number():
    assert measured_facts(RULE) == ["exit_distance_m"]
    exists = {"node": "exists", "collection": "doors", "variable": "$d", "body": {"node": "fact", "entity": "$d", "name": "x"}}
    assert measured_facts(exists) == []


def test_a_rule_about_another_quantity_is_refused_with_a_reason():
    why = check_measured(Says("none", "none"), "Les prises doivent etre a moins de 1,30 m du sol.", RULE, BINDINGS)
    assert why and "none of the quantities" in why
    why = check_measured(Says("area_m2", "area_m2"), "An area sentence.", RULE, BINDINGS)
    assert why and "floor area" in why


def test_agreement_passes_and_only_numeric_facts_are_offered():
    model = Says("exit_distance_m")
    assert check_measured(model, "Travel distance shall be less than 45 m.", RULE, BINDINGS) is None
    assert model.calls == 1


def test_a_position_bias_does_not_refuse_a_good_rule():
    model = Says("area_m2", "exit_distance_m")             # wrong first, right when the order is reversed
    assert agrees(model, "s", {"area_m2": "a", "exit_distance_m": "b"}, "exit_distance_m")[0] is True
    assert model.calls == 2


def test_no_answer_never_blocks_a_rule():
    assert check_measured(Says(RuntimeError("down")), "s", RULE, BINDINGS) is None
    assert check_measured(Says("not a fact id"), "s", RULE, BINDINGS) is None


# --- the kind of requirement: a route, a link, a count or a yes/no fact -------------------------------------------------

from reviewpulse.interpreter.grounding import KINDS, check_concern, concerns, kind_choices  # noqa: E402
from reviewpulse.xeval.expr_ir import parse_expression  # noqa: E402


def _kinds(text):
    return concerns(parse_expression(text, {"r", "a", "b", "d"}))


def test_the_kind_of_a_rule_is_read_from_its_structure():
    assert _kinds("forall rooms r: reaches(r, EXIT)") == ["route"]
    assert _kinds("forall rooms a: forall rooms b: not linked(a, b)") == ["link"]
    assert _kinds("forall rooms r: r.has_window == true") == ["has_window"]
    assert _kinds("forall rooms r: count(doors d) >= 2") == ["count"]
    assert _kinds("forall rooms r: r.area_m2 >= 9") == []          # a measured limit has its own check


def test_a_route_rule_for_a_sentence_about_something_else_is_refused():
    rule = parse_expression("forall rooms r: reaches(r, EXIT)", {"r"})
    why = check_concern(Says("none", "none"), "Amusement rides shall allow sufficient maneuvering clearance.", rule, BINDINGS)
    assert why and "a route from a room" in why and "does not state" in why


def test_a_route_rule_for_a_sentence_that_states_a_route_is_kept():
    rule = parse_expression("forall rooms r: reaches(r, EXIT)", {"r"})
    assert check_concern(Says("route"), "Every room shall have a route to an exit.", rule, BINDINGS) is None


def test_no_answer_never_blocks_a_rule_of_any_kind():
    rule = parse_expression("forall rooms r: reaches(r, EXIT)", {"r"})
    assert check_concern(Says(RuntimeError("down")), "Every room shall have a route to an exit.", rule, BINDINGS) is None


def test_the_menu_lists_the_generic_kinds_and_the_yes_no_facts_of_the_plan():
    menu = kind_choices(BINDINGS)
    assert set(KINDS) <= set(menu) and "reaches_exit" in menu and "area_m2" not in menu


def test_the_plans_own_route_fact_counts_as_the_route_kind():
    # the menu lists both the generic "route" and the plan's reaches_exit fact; choosing the specific one is the same answer
    rule = parse_expression("forall rooms r: reaches(r, EXIT, through n: n.room_type != 'bathroom')", {"r"})
    assert check_concern(Says("reaches_exit", "reaches_exit"), "Every room reaches an exit without passing a bathroom.",
                         rule, BINDINGS) is None


def test_a_count_of_connections_is_one_family_whichever_kind_the_sentence_names():
    bindings = {**BINDINGS,
                "links_door": {"kind": "number", "description": "Number of door connections of the room"},
                "links_passable": {"kind": "number", "description": "Number of connections of the room that a route can follow"}}
    rule = parse_expression("forall rooms r: r.links_passable >= 1", {"r"})
    assert check_measured(Says("links_door", "links_door"), "Every room has at least one door or opening.", rule, bindings) is None
    # a different quantity is still refused
    assert check_measured(Says("area_m2", "area_m2"), "Every room has at least one door or opening.", rule, bindings)


def test_a_sentence_with_two_requirements_accepts_a_rule_for_the_one_the_pick_did_not_name():
    from reviewpulse.interpreter.grounding import _also_requires

    class Yes:
        def complete(self, system, user, schema):
            return {"choice": "yes"}

    class No:
        def complete(self, system, user, schema):
            return {"choice": "no"}

    assert _also_requires(Yes(), "Dimension and label all rooms.", "the room is named on the drawing")
    assert not _also_requires(No(), "Dimension all rooms.", "the room is named on the drawing")
