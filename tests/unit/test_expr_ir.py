"""The expression format: it must express every rule shape in the corpus and refuse malformed text clearly."""

import re

import pytest

from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.behavior import compare
from reviewpulse.xeval.expr_ir import ExprError, compile_expr_program, to_expression, to_text
from reviewpulse.xeval.synth import build_corpus
from reviewpulse.xeval.world import bindings_of


def program_from(item, requirement_text, **extra):
    bindings = bindings_of(item.catalogue)
    fields = {"require": requirement_text, "sources": [{"clause": "Art. 1", "quote": "x"}], **extra}
    return Program.model_validate(compile_expr_program(fields, "d", bindings, {"building"}))


def test_every_reference_rule_survives_print_then_parse():
    """250 rules over 10 families and 12 invented subjects: text -> structure must keep the behaviour."""
    for item in build_corpus(120, seed=21) + build_corpus(40, seed=22, split="test"):
        ref = Program.model_validate(item.program)
        extra = {}
        if item.program.get("applicability"):
            extra["applies_when"] = to_text(item.program["applicability"])
        if item.program.get("exemption"):
            extra["unless"] = to_text(item.program["exemption"])
        rebuilt = program_from(item, to_text(item.program["requirement"]), **extra)
        assert compare(ref, rebuilt, item.catalogue, 150)["equivalent"], (item.family, to_text(item.program["requirement"]))


def test_units_are_converted_by_code_and_bare_numbers_take_the_fact_unit():
    cat = build_corpus(1, seed=3)[0].catalogue
    name = next(n for n, b in cat["bindings"].items() if b["unit"] == "m")
    coll = next(c for c, spec in cat["collections"].items() if name in spec["facts"])
    bindings = bindings_of(cat)
    tree = to_expression(f"forall {coll} x: x.{name} >= 90 cm", bindings)
    assert tree["body"]["right"] == {"node": "literal", "value": 0.9, "unit": "m"}
    tree = to_expression(f"count({coll} x where x.{name} >= 2) >= 3", bindings)
    assert tree["right"]["unit"] == "count" and tree["left"]["where"]["right"]["unit"] == "m"


@pytest.mark.parametrize("text,message", [
    ("forall rooms r: r.area_m2 >=", "ends too early"),
    ("forall rooms r: q.area_m2 >= 9 m2", "not a variable"),
    ("r.area_m2 >= 9", "not a variable"),
    ("forall rooms r r.area_m2 >= 9", "expected ':'"),
    ("(1 + 2", "expected ')'"),
    ("forall rooms r: r.area_m2 >= 9 m2 )", "unexpected"),
    ("area >= 9", "expected '.'"),
])
def test_malformed_text_is_refused_with_a_reason(text, message):
    with pytest.raises(ExprError, match=re.escape(message)):
        to_expression(text, {})


def test_the_readback_is_the_text_the_model_wrote():
    text = "forall rooms r where r.room_type == 'bedroom': (r.area_m2 >= 9 m2 and r.min_width_m >= 2.2 m)"
    tree = to_expression(text, bindings_of({"bindings": {
        "room_type": {"kind": "string", "unit": "1", "description": ""},
        "area_m2": {"kind": "number", "unit": "m2", "description": ""},
        "min_width_m": {"kind": "number", "unit": "m", "description": ""}}}))
    assert to_text(tree) == text.replace("(r.area", "r.area").replace("2.2 m)", "2.2 m")


def test_exists_without_colon_and_count_with_colon():
    from reviewpulse.xeval.expr_ir import parse_expression

    a = parse_expression("exists guards g where g.guards_height >= 0.9 m")
    assert a["node"] == "exists" and "where" not in a
    b = parse_expression("count(ducts d where d.ducts_kind == 'x': d.ducts_length >= 1 m) >= 3")
    assert b["left"]["where"]["node"] == "all"


def test_aggregate_with_the_value_after_the_bracket():
    from reviewpulse.xeval.expr_ir import parse_expression

    node = parse_expression("sum(bays b where b.k == 'x'): b.l >= 16 m")
    assert node["node"] == "ge" and node["left"]["node"] == "sum" and node["left"]["body"]["name"] == "l"
