"""I4 without network: a replay client stands in for the LLM (frame answers)."""

from pathlib import Path

import pytest

from reviewpulse.rules.clauses import Clause
from reviewpulse.rules.draft import (
    ReplayClient,
    comparison_from_text,
    draft_document,
    load_drafts,
    output_schema,
    to_rule_dict,
)
from reviewpulse.rules.schema import Rule

DOC = Path(__file__).parents[2] / "docs" / "requirements_example.md"
RASE = {"requirement": [], "applicability": [], "selection": [], "exception": []}


def frame(prop, subject="room", rooms=(), avoid=(), pairs=(), comp="no_number", number=None, unit="none"):
    return {"property": prop, "subject": subject, "room_types": list(rooms), "avoid_room_types": list(avoid),
            "forbidden_pairs": [list(p) for p in pairs], "comparison": comp, "number": number,
            "unit_written": unit, "severity": "major", "title": prop, "rase": RASE}


ANSWERS = {
    "Art. 6.1": frame("clear_width", "door", comp="at_least", number=0.80, unit="m"),
    "Art. 2": frame("route_to_exit", rooms=["bedroom", "living"], avoid=["bathroom", "wc", "bedroom"]),
    "Art. 4": frame("forbidden_direct_connection", pairs=[("garage", "bedroom")]),
    "Art. 6.2": frame("corridor_width", rooms=["corridor"], comp="at_least", number=9.0, unit="m"),  # wrong number
    "Art. 7": frame("glazed_area_ratio", rooms=[], comp="at_least", number=0.1667, unit="fraction"),
    "Art. 8": frame("fire_resistance"),
}


def test_frames_become_valid_rules(tmp_path):
    out = draft_document(DOC, ReplayClient(ANSWERS), tmp_path, only=list(ANSWERS))
    d = {x.clause_id: x for x in load_drafts(out)}
    door = Rule.model_validate(d["Art. 6.1"].rule)
    assert (door.check.fn, door.check.op, door.check.value, door.applies_to) == ("width_m", ">=", 0.8, {"element": "door"})
    assert Rule.model_validate(d["Art. 2"].rule).check.avoid == {"room_type": ["bathroom", "wc", "bedroom"]}
    assert Rule.model_validate(d["Art. 4"].rule).check.model_extra["pairs"] == [["garage", "bedroom"]]
    # a number absent from the clause is flagged (and implausible), not silently accepted
    assert any("does not appear" in f for f in d["Art. 6.2"].flags)
    # empty room list for a room property means habitable rooms
    assert Rule.model_validate(d["Art. 7"].rule).applies_to["room_type"] == ["bedroom", "living", "dining", "kitchen", "office"]
    assert d["Art. 8"].checkable == "not_checkable" and d["Art. 8"].rule is None
    assert all(x.model == "replay" and x.prompt_hash for x in d.values())


def test_units_are_converted():
    cl = Clause(id="X", heading="", text="Doors at least 850 mm wide.", page=0, start=0, end=27)
    r = to_rule_dict(frame("clear_width", "door", comp="at_least", number=850, unit="mm"), cl, "d")
    assert r["check"]["value"] == 0.85 and r["check"]["unit"] == "m"
    r = to_rule_dict(frame("glazed_area_ratio", comp="at_least", number=10, unit="percent"), cl, "d")
    assert r["check"]["value"] == 0.1


def test_comparison_words_override_the_model():
    assert comparison_from_text("La largeur est d'au moins 0,80 m") == "at_least"
    assert comparison_from_text("shall not exceed 25 metres") == "at_most"
    assert comparison_from_text("Le parcours ne dépasse pas 15 m") == "at_most"
    assert comparison_from_text("Each room is labelled") is None
    cl = Clause(id="X", heading="", text="shall not exceed 25 m", page=0, start=0, end=21)
    r = to_rule_dict(frame("travel_distance_to_exit", comp="at_least", number=25, unit="m"), cl, "d")
    assert r["check"]["op"] == "<="


def test_schema_enums_cover_every_property():
    props = output_schema()["properties"]["property"]["enum"]
    assert "clear_width" in props and "fire_resistance" in props and "door_height" in props


@pytest.mark.parametrize("text,flagged", [
    ("Between the locking points the distance should be 400-600mm.", True),           # CODE-ACCORD miss
    ("La hauteur d'allège est comprise entre 0,90 et 1,00 m.", True),
    ("A minimum of 2 m and a maximum of 3 m.", True),
    ("The level difference outside the door may be more than 20 millimetres.", True),  # CODE-ACCORD miss
    ("La pente peut dépasser 5 % sur 2 m.", True),
    ("Doors have a clear width of at least 0.80 m.", False),
    ("Hallways shall be no narrower than 1.10 m.", False),
    ("Article 6-2: doors 0.90 m wide.", False),
])
def test_wordings_one_comparison_cannot_express_are_flagged(text, flagged):
    from reviewpulse.rules.draft import wording_flags

    assert bool(wording_flags(text)) is flagged
