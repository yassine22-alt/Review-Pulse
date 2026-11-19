import pytest

from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.table_rows import compile_table, parse_table_row
from reviewpulse.rules.clauses import Clause


def context(header, row):
    text = header + "\n" + row
    return ContextBundle(document="test", text=text, target="row", clauses=[
        Clause(id="header", heading="", page=0, text=header, start=0, end=len(header), kind="table_header"),
        Clause(id="row", heading="", page=0, text=row, start=len(header) + 1, end=len(text), kind="table_row", parent="header")])


def catalogue():
    return {"whole": "building", "building": ["thermal_transfer"], "collections": {},
            "bindings": {"thermal_transfer": {"kind": "number", "unit": "W/m2/K", "description": "Heat transfer"}},
            "metadata_vocabulary": {
                "zone": {"kind": "string", "unit": "1", "header_aliases": ["region"]},
                "class": {"kind": "string", "unit": "1", "header_aliases": ["use"], "value_cues": ["housing"]},
                "method": {"kind": "string", "unit": "1", "header_aliases": ["approach"], "value_cues": ["method"]},
                "band": {"kind": "number", "unit": "%", "header_aliases": ["band"]}}}


def test_table_preserves_all_scope_cells_units_and_absolute_source_spans():
    ctx = context("| Use and approach | Region | Band | Heat transfer (W/m²/K) |",
                  "| Method alpha, housing beta | X7 | 12 – 24 % | ≤ 0,82 |")
    frame = parse_table_row(ctx, catalogue())
    assert not frame["blockers"]
    assert len(frame["metadata_applicability"]) == 5
    assert frame["measurements"][0]["value"] == 0.82
    assert frame["measurements"][0]["unit"] == "W/m²/K"
    for condition in frame["metadata_applicability"]:
        assert ctx.text[condition["source"]["start"]:condition["source"]["end"]] == condition["source"]["quote"]
    for item in frame["trace"]:
        assert ctx.text[item["source"]["start"]:item["source"]["end"]] == item["source"]["quote"]


def test_new_scope_field_comes_only_from_runtime_data_and_decimal_comma_range_is_not_split():
    cat = catalogue()
    cat["metadata_vocabulary"]["new_field"] = {"kind": "number", "unit": "%", "header_aliases": ["new field"]}
    frame = parse_table_row(context("| New field | Heat transfer (W/m2/K) |", "| 1,2 – 2,4 % | ≥ 0,4 |"), cat)
    assert not frame["blockers"]
    assert [c["value"] for c in frame["metadata_applicability"]] == [1.2, 2.4]


@pytest.mark.parametrize("cell", ["other: ≤ 0.8", "0.8", "≤ 0.8 m"])
def test_qualifiers_missing_comparators_and_conflicting_units_cannot_be_dropped(cell):
    frame = parse_table_row(context("| Heat transfer (W/m2/K) |", f"| {cell} |"), catalogue())
    assert frame["blockers"]
    with pytest.raises(ValueError):
        compile_table(frame, {"choices": []}, context("| Heat transfer (W/m2/K) |", f"| {cell} |"), catalogue())


def test_unknown_scope_column_and_reversed_band_require_review():
    for header, row in [("| Unknown scope | Heat transfer (W/m2/K) |", "| X3 | ≤ 0.8 |"),
                        ("| Band | Heat transfer (W/m2/K) |", "| 30 – 10 % | ≤ 0.8 |")]:
        assert parse_table_row(context(header, row), catalogue())["blockers"]


def test_alternative_zone_is_not_silently_changed_to_single_equality():
    frame = parse_table_row(context("| Region | Heat transfer (W/m2/K) |", "| X3 or X4 | ≤ 0.8 |"), catalogue())
    assert frame["blockers"] and frame["metadata_applicability"] == []


def test_quantity_and_units_remain_fixed_when_linker_proposes_an_incompatible_fact():
    ctx = context("| Heat transfer (W/m2/K) |", "| ≤ 0.8 |")
    cat = catalogue()
    cat["bindings"]["other"] = {"kind": "number", "unit": "m"}
    cat["building"].append("other")
    frame = parse_table_row(ctx, cat)
    with pytest.raises(ValueError, match="incompatible"):
        compile_table(frame, {"choices": [{"measurement": "m0", "fact": "other"}]}, ctx, cat)
    assert frame["measurements"][0]["value"] == 0.8 and frame["measurements"][0]["operator"] == "le"


def test_narrative_quantities_are_not_presented_as_a_complete_rule():
    text = "At least 3 m unless exempt."
    ctx = ContextBundle(document="x", text=text, target="r", clauses=[
        Clause(id="r", heading="", page=0, text=text, start=0, end=len(text))])
    frame = parse_table_row(ctx, catalogue())
    assert frame["kind"] == "numeric_prose" and frame["blockers"]
