"""Reviewer statuses, the overall result, and the language free discipline tags (all read from data files)."""

from __future__ import annotations

import pytest

from reviewpulse.report import disciplines as disc
from reviewpulse.report import reviewer_states as rs


def test_data_file_keeps_its_own_rules():
    assert rs.check_policy() == []


def test_every_verdict_maps_and_unknown_is_never_a_pass():
    for verdict in ("FAIL", "WARNING", "NOT_EVALUATED"):
        assert rs.rollup(rs.status_of_verdict(verdict)) == "Revision required"
    assert rs.status_of_verdict("PASS") == "approved"
    assert rs.rollup(rs.status_of_verdict("SOMETHING_NEW")) == "Revision required"        # an unknown verdict asks for information
    assert rs.status_of_outcome("UNRESOLVED") == "information_requested"
    assert rs.status_of_outcome("NOT_APPLICABLE") == "not_applicable"
    assert rs.status_of_outcome("EXEMPT") == "not_applicable"
    assert rs.status_of_outcome("VIOLATED") == "revision_required"


def test_the_six_reviewer_statuses_exist():
    labels = {v["label"] for v in rs.statuses().values()}
    assert labels == {"Approved", "Approved with comments", "Information requested", "Revision required", "Not applicable",
                      "Deferred submittal"}


def test_overall_is_the_most_severe_status():
    assert rs.results() == ["Not required", "Approved", "Approved with comments", "Revision required", "Rejected"]
    assert rs.overall(["approved", "revision_required", "not_applicable"])["result"] == "Revision required"
    assert rs.overall(["approved", "information_requested"])["result"] == "Revision required"
    assert rs.overall(["approved", "deferred"])["result"] == "Approved with comments"
    assert rs.overall(["approved", "approved"])["result"] == "Approved"
    assert rs.overall(["not_applicable"])["result"] == "Not required"


def test_a_clause_that_was_not_decided_stops_a_plain_approval():
    assert rs.overall(["approved"], uncovered=3)["result"] == "Approved with comments"
    assert rs.overall(["approved"], uncovered=0)["result"] == "Approved"
    assert rs.overall([], reviewed=0)["result"] is None           # nothing decided: no proposal at all


def test_the_tool_never_proposes_rejected():
    assert rs.overall(["revision_required"] * 5, uncovered=9)["result"] != "Rejected"
    assert rs.rank("Rejected") > rs.rank("Revision required")


@pytest.mark.parametrize("text,expected", [
    ("Smoke alarms shall be installed in each sleeping room.", "fire_life_safety"),
    ("Les détecteurs de fumée doivent être installés dans chaque chambre; alarme incendie.", "fire_life_safety"),
    ("Brandschutz: der Rettungsweg muss frei sein.", "fire_life_safety"),
    ("Las puertas de evacuación y la salida de emergencia.", "fire_life_safety"),
    ("The foundation footing and the beam shall carry the seismic load.", "structural"),
    ("La poutre et le poteau portent la charge sismique.", "structural"),
    ("Receptacle outlets and the lighting circuit need grounding.", "electrical"),
    ("Die Steckdose und der Stromkreis brauchen eine Erdung.", "electrical"),
    ("Water closet and lavatory drains connect to the sewer.", "plumbing"),
    ("Ventilation duct, exhaust fan and furnace.", "mechanical"),
    ("Insulation with the stated U-factor, thermal envelope.", "energy"),
    ("Wheelchair accessible route and ramp with grab bar.", "accessibility"),
    ("Accessibilité: rampe pour fauteuil roulant.", "accessibility"),
    ("Setback from the property line and zoning, parking.", "planning"),
    ("Every door has a clear width of at least 0.80 m.", "architectural"),
    ("Lorem ipsum dolor sit amet.", "general"),
])
def test_clauses_are_tagged_in_four_languages(text, expected):
    assert disc.discipline_of(text) == expected


def test_a_cue_is_a_word_not_a_fragment():
    assert disc.discipline_of("The window is open.") == "architectural"      # 'wind' is a structural cue; 'window' is not it


def test_accents_and_case_do_not_matter():
    assert disc.discipline_of("KÜCHE") == disc.discipline_of("kuche") == "architectural"


def test_sheets_by_number_prefix_title_and_kind():
    assert disc.sheet_discipline("A-101") == "architectural"
    assert disc.sheet_discipline("S2.1") == "structural"
    assert disc.sheet_discipline("E-201") == "electrical"
    assert disc.sheet_discipline("FP-1") == "fire_life_safety"
    assert disc.sheet_discipline("M1") == "mechanical"
    assert disc.sheet_discipline("sheet_3", title="Plan de plomberie, sanitaire") == "plumbing"
    assert disc.sheet_discipline("plan_p0", sheet_type="structural") == "structural"
    assert disc.sheet_discipline("plan_p0") == "general"


def test_code_chapter_from_a_heading_or_the_clause_number():
    assert disc.chapter_of("R311.6")[0] == "R311"
    assert disc.chapter_of("Art. 6.1")[0] == "Art. 6"
    assert disc.chapter_of("3.2.1")[0] == "3"
    assert disc.chapter_of("R311.6", "Chapter 3 Building planning")[1] == "Chapter 3 Building planning"
    assert disc.chapter_of("")[1] == "Other"


def test_every_listed_discipline_has_cues_in_all_four_languages():
    for did, spec in disc.config()["disciplines"].items():
        if did == disc.config()["default"]:
            continue
        assert set(spec["cues"]) == {"en", "fr", "de", "es"}, did
    assert set(disc.config()["tie_order"]) == set(disc.config()["disciplines"])
