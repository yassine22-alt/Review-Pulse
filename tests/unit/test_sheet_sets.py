"""A drawing set holds more than floor plans. Only a floor plan is read as one, and a level that leaves the building by stairs
does not prove "no route to the exit"."""

import handmade

from reviewpulse import pipeline
from reviewpulse.annotate import sheet_kind
from reviewpulse.factgraph.from_building import from_building


def test_gate_empties_a_sheet_that_is_not_a_floor_plan(monkeypatch, tmp_path):
    model = handmade.build()
    assert model.rooms and model.elements
    monkeypatch.setattr(sheet_kind, "judge", lambda *a, **k: {"kind": "elevation", "contains_floor_plan": False,
                                                              "source": "vision"})
    pipeline.gate_sheet(model, tmp_path / "preview.png")
    assert model.rooms == [] and model.elements == [] and model.edges == []
    assert model.sheet.sheet_type == "elevation" and model.sheet.kind_source == "vision"
    assert any("not a floor plan" in w for w in model.sheet.warnings)


def test_gate_keeps_a_floor_plan(monkeypatch, tmp_path):
    model = handmade.build()
    n = len(model.rooms)
    monkeypatch.setattr(sheet_kind, "judge", lambda *a, **k: {"kind": "floor_plan", "contains_floor_plan": True,
                                                              "source": "vision"})
    pipeline.gate_sheet(model, tmp_path / "preview.png")
    assert len(model.rooms) == n and model.sheet.sheet_type == "floor_plan"


def test_an_unnamed_sheet_is_still_treated_as_a_plan():
    assert pipeline._is_plan(handmade.build())                      # old runs have no sheet kind


def test_title_words_name_an_elevation_in_several_languages():
    for words, kind in [("EXTERIOR ELEVATIONS", "elevation"), ("Façade nord", "elevation"), ("Coupe AA", "section_or_detail"),
                        ("Alzado principal", "elevation"), ("Site plan", "site_plan"), ("Grundriss Erdgeschoss", "floor_plan"),
                        ("Tableau des menuiseries", "schedule_or_notes")]:
        assert sheet_kind.from_words(words) == kind, words


def test_a_level_without_a_door_to_the_outside_does_not_prove_no_route():
    model = handmade.build()
    alone = from_building(model, complete=True)
    in_set = from_building(model, complete=True, part_of_set=True)
    has_exit = any(e.a in ("EXIT", "EXTERIOR") or e.b in ("EXIT", "EXTERIOR") for e in model.edges)
    assert alone.graph_complete is True
    assert in_set.graph_complete is has_exit            # only a level that really reaches the outside can prove it
    model.edges = [e for e in model.edges if e.a not in ("EXIT", "EXTERIOR") and e.b not in ("EXIT", "EXTERIOR")]
    assert from_building(model, complete=True, part_of_set=True).graph_complete is False
    assert from_building(model, complete=True, part_of_set=False).graph_complete is True
