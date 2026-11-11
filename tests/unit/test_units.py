"""Units by dimensional analysis: any unit a domain uses, with conversions, derived units and refusal of nonsense."""

import math

import pytest

from reviewpulse.interpreter import units as U


def test_the_units_the_building_domain_already_used_still_work():
    for unit in ("1", "m", "m2", "count", "m²", "mm", "cm", "%"):
        assert U.is_unit(unit)
    assert U.same_unit("m2", "m.m") and U.same_unit("m²", "m2")
    assert not U.same_unit("m", "cm") and U.compatible("m", "cm")
    assert math.isclose(U.convert(90, "cm", "m"), 0.9) and math.isclose(U.convert(2500, "mm", "m"), 2.5)


@pytest.mark.parametrize("value,source,target,expected", [
    (2.5, "kPa", "Pa", 2500.0), (5, "L", "m3", 0.005), (1, "m3", "L", 1000.0), (90, "min", "h", 1.5),
    (1, "ft", "cm", 30.48), (1, "kg/m3", "g/L", 1.0), (1, "bar", "kPa", 100.0), (3, "mm2", "m2", 3e-6),
    (100, "Cel", "K", 373.15), (212, "degF", "Cel", 100.0), (50, "%", "1", 0.5), (1, "km/h", "m/s", 1 / 3.6),
])
def test_conversions_between_compatible_units(value, source, target, expected):
    assert math.isclose(U.convert(value, source, target), expected, rel_tol=1e-6)


def test_different_things_are_refused():
    with pytest.raises(U.UnitError, match="different things"):
        U.convert(1, "kPa", "m")
    assert not U.compatible("kg", "s")
    with pytest.raises(U.UnitError):
        U.parse_unit("furlongs")
    with pytest.raises(U.UnitError, match="offset|temperature"):
        U.combine("Cel", "m", "mul")


def test_products_and_quotients_give_a_readable_unit_that_parses_back():
    assert U.combine("m", "m", "mul") == "m2" and U.combine("m2", "m", "div") == "m"
    assert U.combine("m", "1", "mul") == "m" and U.combine("m", "m", "div") == "1"
    density = U.combine("kg", "m3", "div")
    assert U.same_unit(density, "kg/m3") and U.is_unit(density)
    assert U.same_unit(U.combine("N", "m2", "div"), "Pa")
    scaled = U.symbol_of(U.parse_unit("cm") * U.parse_unit("cm"))
    assert U.same_unit(scaled, "cm2") and U.is_unit(scaled)


def test_prefixes_do_not_swallow_units():
    assert U.same_unit("min", "60.s") and not U.same_unit("min", "m.in")      # minute, not milli-inch
    assert U.same_unit("mm", "0.001.m") and U.same_unit("dam", "10.m")
    assert U.to_si(1, "ha") == 10000


def test_a_sentence_in_any_domain_can_state_its_unit_in_the_rule_language():
    from reviewpulse.interpreter.schema import Binding, LiteralExpr

    assert LiteralExpr(node="literal", value=5, unit="kPa").unit == "kPa"
    assert Binding(kind="number", unit="L/min").unit == "L/min"
    with pytest.raises(ValueError):
        LiteralExpr(node="literal", value=5, unit="furlongs")
