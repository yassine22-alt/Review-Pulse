"""Correction lists: item ids of a canned list, the layout accidents of their PDFs, and the item description of scripts/correction_list_eval.py."""

import sys
from pathlib import Path

from reviewpulse.rules.clauses import prepare_items, split_text

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

import correction_list_eval as cle  # noqa: E402

LIST = (
    "A. PLAN REQUIREMENTS\n\n"
    "A1. Specify on plans that the governing codes are the 2019 CRC.\n\n"
    "A2. Indicate a job address on all sheets of the plans. [CRC R106.1.1]\n\n"
    "A3. Provide a completely dimensioned plot plan showing [CRC R106.1.1]:\n"
    "a) Existing grades.\n\nb) North Arrow.\n\n"
    "A4. Owner or contractor to sign the form. Completed form to be returned at recheck.A5. Complete and sign the attached form.\n\n"
    "B. GENERAL\n\n"
    "B1. Townhouse parapets shall be constructed on exterior walls in accordance with CRC\n"
    "R302.2.3. [CRC R302.2.2]\n\n"
    "B2. Provide a footing with a water cement ratio of\n"
    "0.45. No special inspection is required if a ticket is provided.\n\n"
    "B3. Show the north arrow on the site plan.\n"
)


def ids(text):
    full, pages = prepare_items(text, [(0, len(text))])
    return full, [(c.id, c.text) for c in split_text(full, pages)]


def test_item_ids_are_the_clause_ids():
    _, clauses = ids(LIST)
    got = [i for i, _ in clauses]
    assert {"A1", "A2", "A3", "A4", "A5", "B1", "B2"} <= set(got)
    assert "A3 a)" in got and "A3 b)" in got


def test_item_glued_after_the_end_of_the_one_before_is_cut():
    _, clauses = ids(LIST)
    text = dict(clauses)
    assert "Complete and sign" not in text["A4"] and text["A5"].startswith("A5. Complete and sign")


def test_citation_and_decimal_do_not_start_clauses():
    _, clauses = ids(LIST)
    got = [i for i, _ in clauses]
    assert "R302.2.3." not in got and "0.45" not in got
    assert "[CRC R302.2.2]" in dict(clauses)["B1"] and "No special inspection" in dict(clauses)["B2"]


def test_a_letter_that_starts_no_series_is_not_an_item_id():
    _, clauses = ids("X1. This line stands alone and is a sentence that shall be read as one.\n\nY2. Another one shall stand.\n")
    assert all(not i.startswith(("X1", "Y2")) for i, _ in clauses)


def test_offsets_and_pages_follow_the_cut():
    text = "A1. First item shall be shown.\n\nA2. Second item shall be shown.\n\nA3. Third. Return it.A4. Fourth shall be shown.\n"
    full, pages = prepare_items(text, [(0, len(text) // 2), (len(text) // 2, len(text))])
    assert len(full) == len(text) + 1 and pages[-1][1] == len(full)
    for c in split_text(full, pages):
        assert c.text == full[c.start:c.end]


def test_lone_number_is_joined_to_its_sentence():
    full, clauses = ids("PART I\n\n1.\nProvide a plot plan to scale.\n\n2. Show the address.\n\n3. Show the north arrow.\n")
    assert dict(clauses)["1"].startswith("1.") and "plot plan" in dict(clauses)["1"]
    assert len(full) == len("PART I\n\n1.\nProvide a plot plan to scale.\n\n2. Show the address.\n\n3. Show the north arrow.\n")


def test_citation_of_an_item():
    assert cle.citation("Doors shall be self-closing. [CRC R302.5.1]") == "CRC R302.5.1"
    assert cle.citation("Indicate drawing scales.") is None


def test_blanks_choices_and_conditions():
    d = cle.describe(type("C", (), {"id": "7", "page": 0, "kind": "numbered",
                                    "text": "7. Provide ( ) paved parking spaces. A min. of (   ) spaces shall be standard"})())
    assert d["blanks"] and d["conditional"]
    d2 = cle.describe(type("C", (), {"id": "8", "page": 0, "kind": "numbered", "text": "8. Indicate drawing scales."})())
    assert not d2["conditional"] and d2["work"] == "presence"


def test_kind_of_work():
    assert cle.kind_of_work("Show a 7' minimum ceiling height for habitable rooms. [CRC R305.1]") == "numeric_limit"
    assert cle.kind_of_work("Change valuation on permit application and pay associated fees.") == "administrative"
    assert cle.kind_of_work("Indicate building type of construction on the first sheet of the plans.") == "presence"


def test_outcome_priority():
    assert cle.outcome_of({"status": "DRAFTED", "mention": False}) == "measured"
    assert cle.outcome_of({"status": "DRAFTED", "mention": True}) == "mention"
    assert cle.outcome_of({"status": "UNRESOLVED", "evidence_found": True}) == "evidence"
    assert cle.outcome_of({"status": "UNRESOLVED", "needs": "stair landings"}) == "question"
    assert cle.outcome_of({"status": "UNRESOLVED"}) == "declined"
