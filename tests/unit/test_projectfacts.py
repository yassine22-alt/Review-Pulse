"""Project facts: label-value reading, units and locales, unknowns, derived conditions, planted sheets, metamorphic changes."""

from __future__ import annotations

import pytest

from reviewpulse.drawingset.pagedata import Line, PageData
from reviewpulse.factgraph.schema import Fact, FactGraph, Node
from reviewpulse.interpreter.schema import Binding
from reviewpulse.ledger.candidate import Candidate
from reviewpulse.ledger.request import FactRequest
from reviewpulse.projectfacts import (
    Condition,
    ProjectFactsProducer,
    dwelling_above_another,
    evaluate,
    load_spec,
    read_project_facts,
    risers_at_least,
)
from reviewpulse.projectfacts.planted import make_cover
from reviewpulse.projectfacts.values import parse_number, parse_value


def page(*rows: tuple[str, float, float]) -> PageData:
    pg = PageData(0, 1000.0, 800.0)
    for text, x, y in rows:
        pg.lines.append(Line(text, x, y, x + 7 * len(text), y + 10, 10))
    return pg


def facts(*rows):
    return read_project_facts([page(*rows)])


def value(pf, fact, entity="building"):
    return next((c.value for c in pf.candidates if c.fact == fact and c.entity == entity and c.value is not None), None)


# ---- numbers and locales ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, lang, unit, want", [
    ("1,092", "en", "ft2", 1092.0), ("61,3", "de", "m2", 61.3), ("1.092,5", "de", "m2", 1092.5), ("1,092.5", "en", "m2", 1092.5),
    ("1 092,5", "fr", "m2", 1092.5), ("4'586", "de", "m2", 4586.0), ("12.5", "en", "m2", 12.5), ("1,092", "de", "m2", 1.092),
    ("1.092", "de", "m2", 1092.0), ("7,500", "en", "ft2", 7500.0)])
def test_number_locales(text, lang, unit, want):
    assert parse_number(text, lang, unit) == pytest.approx(want)


def test_area_units_become_square_metres():
    f = load_spec().fields["gross_floor_area"]
    s = load_spec()
    assert parse_value(f, "1,207 SF", s, "en").value == pytest.approx(112.1, abs=0.1)
    assert parse_value(f, "61,3 m²", s, "de").value == pytest.approx(61.3)
    assert parse_value(f, "120", s, "en").status == "unstated"           # no unit anywhere: not guessed
    assert parse_value(f, "120", s, "en", "m2").value == 120.0           # unit from the header


def test_height_feet_and_inches():
    f = load_spec().fields["building_height"]
    assert parse_value(f, "17'-2\" (+ HEIGHT OF PIERS)", load_spec()).value == pytest.approx(5.23, abs=0.01)


# ---- layouts ----------------------------------------------------------------------------------------------------------

def test_colon_line_cell_and_header_layouts_agree():
    a = facts(("SPRINKLERS: NO", 50, 100))
    b = facts(("SPRINKLERS", 50, 100), (": NO", 300, 100))
    c = facts(("SPRINKLERS", 50, 100), ("NO", 50, 112))
    assert value(a, "sprinklered") is value(b, "sprinklered") is value(c, "sprinklered") is False


def test_value_of_a_label_is_never_taken_from_another_label():
    pf = facts(("SPRINKLERS", 50, 100), ("FIRE ALARM", 50, 112), ("YES", 300, 112))
    assert value(pf, "sprinklered") is None and value(pf, "fire_alarm") is True


def test_levels_from_a_column_with_unit_in_header():
    pf = facts(("Area (m²)", 300, 100), ("Ground floor", 50, 120), ("95,5", 300, 120), ("First floor", 50, 140), ("80", 300, 140))
    assert value(pf, "floor_area", "level:ground") == pytest.approx(95.5)
    assert value(pf, "floor_area", "level:level 1") == pytest.approx(80.0)


def test_unit_written_in_the_label():
    assert value(facts(("LIVABLE SF:    4,586", 50, 100)), "living_area") == pytest.approx(426.0, abs=0.5)


def test_construction_label_with_a_use_value_is_read_as_a_use():
    pf = facts(("CONSTRUCTION TYPE", 50, 100), (": SINGLE FAMILY RESIDENTIAL", 300, 100))
    assert value(pf, "construction_type") is None
    assert value(pf, "building_class") == "single_family_dwelling"
    assert "construction_type" in pf.unknown


def test_title_line_is_scanned_for_use_and_work():
    pf = facts(("BAUVORHABEN:", 50, 100), ("Nutzungsänderung best. Einfamilienwohnhaus mit Garage", 50, 112))
    assert value(pf, "building_class") == "single_family_dwelling" and value(pf, "work_type") == "change_of_use"


# ---- unknowns ---------------------------------------------------------------------------------------------------------

def test_nothing_stated_means_typed_unknowns_and_requests():
    pf = facts(("Die Gemeinde prueft den Antrag", 50, 100), ("INSTALL SPRINKLER HEADS PER MANUFACTURER", 50, 112))
    assert not [c for c in pf.candidates if c.value is not None]
    assert "sprinklered" in pf.unknown and "number_of_storeys" in pf.unknown
    reqs = {r.fact: r for r in pf.requests()}
    assert reqs["sprinklered"].kind == "bool" and reqs["gross_floor_area"].unit == "m2" and reqs["sprinklered"].reason == "missing"


def test_tbd_is_unstated_not_a_value():
    pf = facts(("RISK CATEGORY", 50, 100), (": TBD", 300, 100), ("FIRE ALARM", 50, 120), (": TBD", 300, 120))
    c = next(c for c in pf.candidates if c.fact == "fire_alarm")
    assert c.value is None and "TBD" in c.words and "fire_alarm" in pf.unknown


def test_scan_without_text_layer_says_so():
    pg = PageData(0, 100.0, 100.0, has_text_layer=False)
    assert "no text layer" in read_project_facts([pg]).unknown["sprinklered"]


# ---- candidates and the ledger ----------------------------------------------------------------------------------------

def test_candidates_are_ledger_candidates_with_a_citation():
    pf = facts(("SPRINKLERS: NO", 50, 100), ("Stories: two", 50, 130))
    for c in pf.candidates:
        assert isinstance(c, Candidate) and c.source.strip()
    c = next(c for c in pf.candidates if c.fact == "sprinklered")
    assert c.kind == "stated" and "SPRINKLERS" in c.source and c.family == "textlayer"
    assert value(pf, "number_of_storeys") == 2


def test_producer_answers_a_request_by_meaning():
    prod = ProjectFactsProducer(facts(("SPRINKLERS: YES", 50, 100)))
    req = FactRequest(entity="building", entity_kind="building", fact="sprinklered", kind="bool")
    assert prod.holds(req) == 1.0 and [c.value for c in prod.answer(req)] == [True]
    assert prod.holds(FactRequest(entity_kind="room", entity="r1", fact="sprinklered", kind="bool")) == 0.0
    assert prod.holds(FactRequest(entity_kind="building", fact="gross_floor_area", kind="bool")) == 0.0


# ---- derived conditions -----------------------------------------------------------------------------------------------

def stair_graph(tread_lines: float | None, trusted: bool = True) -> FactGraph:
    attrs = {} if tread_lines is None else {"tread_lines": Fact(value=tread_lines, source="s", trusted=trusted)}
    return FactGraph(bindings={"tread_lines": Binding(kind="number", unit="count")}, nodes=[Node(id="st1", kind="stair", attrs=attrs)])


def test_risers_condition_true_false_unknown():
    assert risers_at_least(stair_graph(14), 4).holds is True
    assert risers_at_least(stair_graph(2), 6).holds is False
    e = risers_at_least(stair_graph(4), 4)                               # 3 to 5 risers: the limit falls inside
    assert e.known is False and e.holds is None
    assert risers_at_least(stair_graph(None), 4).known is False
    assert risers_at_least(stair_graph(14, trusted=False), 4).known is False


def test_dwelling_above_another_only_where_stated():
    assert dwelling_above_another({"number_of_storeys": 1}).holds is False
    assert dwelling_above_another({"building_class": "single_family_dwelling"}).holds is False
    assert dwelling_above_another({"building_class": "multi_family_dwelling", "number_of_storeys": 3}).known is False
    assert dwelling_above_another({}).known is False


def test_conditions_on_project_facts_are_three_valued():
    assert evaluate(Condition("sprinklered", "==", True), {"sprinklered": False}).holds is False
    assert evaluate(Condition("number_of_storeys", ">=", 3), {"number_of_storeys": 3}).holds is True
    e = evaluate(Condition("sprinklered"), {})
    assert e.known is False and "not stated" in e.why


# ---- planted sheets and metamorphic changes ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en", "fr", "de"])
@pytest.mark.parametrize("layout", ["colon", "cells", "stacked"])
@pytest.mark.parametrize("ruled", [False, True])
@pytest.mark.parametrize("unit_in", ["cell", "header"])
def test_planted_cover_sheets_are_read_exactly(lang, layout, ruled, unit_in):
    for seed in range(3):
        pg, truth = make_cover(lang, layout=layout, ruled=ruled, unit_in=unit_in, seed=seed, storeys=1 + seed, sprinklered=bool(seed % 2))
        got = read_project_facts([pg]).stated()
        for k, v in truth.values.items():
            assert got.get(k) == pytest.approx(v, rel=0.006) if isinstance(v, float) else got.get(k) == v, (k, got.get(k), v)
        assert set(got) == set(truth.values)


def test_imperial_sheet_converts_to_the_same_metres():
    pg, truth = make_cover("en", imperial=True, area_m2=200.0, height_m=9.0, seed=1)
    got = read_project_facts([pg]).stated()
    assert got["gross_floor_area"] == pytest.approx(200.0, rel=0.006) and got["building_height"] == pytest.approx(9.0, rel=0.01)


def test_rules_on_the_page_change_nothing():
    a, _ = make_cover("de", seed=2, ruled=False)
    b, _ = make_cover("de", seed=2, ruled=True)
    assert read_project_facts([a]).stated() == read_project_facts([b]).stated()


@pytest.mark.parametrize("lang", ["en", "fr", "de"])
def test_changing_a_stated_value_changes_the_output_and_nothing_else(lang):
    base = read_project_facts([make_cover(lang, storeys=2, sprinklered=False, seed=5)[0]]).stated()
    more = read_project_facts([make_cover(lang, storeys=3, sprinklered=False, seed=5)[0]]).stated()
    spr = read_project_facts([make_cover(lang, storeys=2, sprinklered=True, seed=5)[0]]).stated()
    assert {k for k in base if base[k] != more.get(k)} == {"number_of_storeys"} and more["number_of_storeys"] == 3
    assert {k for k in base if base[k] != spr.get(k)} == {"sprinklered"} and spr["sprinklered"] is True


def test_dropping_a_stated_fact_makes_it_unknown():
    pg, _ = make_cover("fr", seed=1, drop=("sprinklered",))
    pf = read_project_facts([pg])
    assert "sprinklered" in pf.unknown and "sprinklered" not in pf.stated()


# ---- the embedding arm (a stand-in embedder, no model server) ---------------------------------------------------------

def test_embedding_arm_places_an_unknown_label_and_is_off_by_default(monkeypatch):
    rows = (("Levels above grade", 50, 100), ("3", 300, 100))
    assert value(facts(*rows), "number_of_storeys") is None             # words do not know this label
    spec = load_spec()

    def embedder(texts):                                                # near the storeys document, far from the rest
        return [[1.0, 0.0] if (t.lower().startswith("number of storeys") or "levels above" in t.lower())
                else [0.0, 1.0] for t in texts]

    pf = read_project_facts([page(*rows)], embedder=embedder)
    c = next(c for c in pf.candidates if c.fact == "number_of_storeys" and c.value is not None)
    assert c.value == 3 and c.score < 0.85 and spec.fields["number_of_storeys"].kind == "number"
    assert pf.arm == "words+embedding"


def test_storeys_from_plan_levels_skip_the_roof_and_stay_low_scored():
    from reviewpulse.drawingset.model import DrawingSet, Sheet, View
    from reviewpulse.projectfacts import storeys_from_plans

    views = [View(id=f"0.{i}", sheet=0, kind="plan", title=t, labels=[], bbox=(0, 0, 1, 1), level=lv, level_rank=rk)
             for i, (t, lv, rk) in enumerate([("a", "basement", -1), ("b", "ground", 0), ("c", "level 1", 1), ("d", "roof", 99)])]
    ds = DrawingSet("s", "xycut", [Sheet(0, "A1", "title block", "t", 1, 1, views=views)], [], [], [])
    c = storeys_from_plans(ds)
    assert c.value == 2 and c.kind == "inferred" and c.score < 0.5 and "roof" not in c.words
    assert storeys_from_plans(DrawingSet("e", "xycut", [], [], [], [])) is None
