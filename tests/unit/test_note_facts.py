"""Words on the sheet about safety provisions become counted facts; a door schedule's fire column becomes a door fact."""

import handmade
import pytest

from reviewpulse.annotate.notes import note_counts, parse_fire_minutes
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.schema import Prov, TextItem


def _text(i, s, x=0.0, y=0.0):
    return TextItem(id=f"t{i}", text=s, bbox=(x, y, x + 1, y + 0.2), prov=Prov(source="vector", stage="test"))


def _building(graph):
    return next(n for n in graph.nodes if n.id == "building")


def test_counts_in_three_languages_and_split_runs():
    texts = [_text(1, "SMOKE", 0, 5), _text(2, "DETECTOR", 1.1, 5), _text(3, "Détecteur de fumée", 0, 3),
             _text(4, "Rauchmelder", 0, 1), _text(5, "20 MIN. FIRE DOOR", 0, 0)]
    c = note_counts(texts)
    assert c["smoke_alarm_notes"] == 3 and c["fire_rating_notes"] == 1 and c["handrail_notes"] == 0


def test_no_text_means_no_counts():
    assert note_counts([]) is None and note_counts([_text(1, "  ")]) is None


@pytest.mark.parametrize("cell,want", [("20 MIN", 20), ("1 HR", 60), ("1-1/2 HR", 90), ("EI30", 30), ("NR", 0), ("-", 0),
                                       ("45", 45), ("see note", None), ("", None)])
def test_fire_minutes(cell, want):
    assert parse_fire_minutes(cell) == want


def test_a_word_found_is_trusted_and_a_zero_only_when_the_sheet_is_alone():
    m = handmade.build()
    m.sheet.texts = [_text(1, "SMOKE ALARM, INTERCONNECTED")]
    alone = _building(from_building(m, complete=True)).attrs
    assert alone["smoke_alarm_notes"].value == 1 and alone["smoke_alarm_notes"].trusted
    assert alone["handrail_notes"].value == 0 and alone["handrail_notes"].trusted == (m.tier == "T1")
    in_set = _building(from_building(m, complete=True, part_of_set=True)).attrs
    assert in_set["smoke_alarm_notes"].trusted == (m.tier == "T1")
    assert in_set["handrail_notes"].value == 0 and not in_set["handrail_notes"].trusted


def test_a_sheet_with_no_text_gets_no_note_facts():
    m = handmade.build()
    m.sheet.texts = []
    assert "smoke_alarm_notes" not in _building(from_building(m, complete=True)).attrs
