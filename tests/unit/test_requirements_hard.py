"""Requirement documents as people really write them: no numbering, nested legal numbering, codes, bullets, tables,
definitions, repeated numbers across parts, headers and footers on every page. None of this names a plan type."""

from __future__ import annotations

import pytest

from reviewpulse.interpreter.context import assemble_context
from reviewpulse.rules.clauses import split_document, split_text


def ids(text):
    return [c.id for c in split_text(text)]


def test_spans_always_match_the_source():
    for text in (UNSTRUCTURED, LEGAL, CODES, TABLES, REPEATED, MIXED):
        for c in split_text(text):
            assert text[c.start:c.end] == c.text, c.id


def test_unstructured_prose_becomes_one_clause_per_sentence():
    cl = split_text(UNSTRUCTURED)
    assert [c.kind for c in cl] == ["paragraph"] * 4
    assert "30 m" in cl[1].text and "12 m2" in cl[2].text
    assert not any("Design brief" in c.text for c in cl)          # a title is not a requirement


def test_abbreviations_and_decimals_do_not_split_a_sentence():
    cl = split_text("Doors e.g. to stores shall be 0.8 m wide, see Art. 4 for more. Corridors shall be 1.2 m wide.\n")
    assert len(cl) == 2 and cl[0].text.endswith("more.")


def test_nested_legal_numbering_keeps_the_hierarchy():
    cl = {c.id: c for c in split_text(LEGAL)}
    assert cl["Rule 5 (1) (a)"].parent == "Rule 5 (1)"
    assert cl["Rule 5 (1)"].parent == "Rule 5"
    assert "Rule 5 (2)" in cl and "Rule 6 (2)" in cl


def test_repeated_numbers_get_distinct_ids():
    got = ids(REPEATED)
    assert len(got) == len(set(got)) == 4
    assert any("Appendix A" in i for i in got)
    # and the interpreter no longer refuses the document
    full = REPEATED
    clauses = split_text(full)
    assemble_context("d", full, clauses, clauses[-1].id)


def test_codes_bullets_and_section_signs():
    assert ids(CODES)[:3] == ["REQ-001", "REQ-002", "REQ-003"]
    assert "REQ-003 item 1" in ids(CODES)
    assert "§ 2" in ids(MIXED) and "Art. 3" in ids(MIXED)


def test_a_wrapped_line_starting_with_a_number_is_not_a_clause():
    text = "Art. 1 Patients should not walk\n30 m to reach an exit.\nArt. 2 Doors shall open outwards.\n"
    assert ids(text) == ["Art. 1", "Art. 2"]


def test_a_word_and_number_is_structure_only_when_it_repeats():
    assert ids("Rule 5. Doors shall be wide.\nRule 6. Stairs shall be safe.\n") == ["Rule 5", "Rule 6"]
    assert "Rule 5" not in ids("As Rule 5 says nothing here.\nThe corridor shall be 1.2 m wide.\n")


def test_table_rows_keep_their_header_and_tables_are_not_clause_numbers():
    full = TABLES
    cl = split_text(full)
    by = {c.id: c for c in cl}
    assert by["Table 1"].kind == "table_header" and by["Table 1 row 1"].parent == "Table 1"
    ctx = assemble_context("d", full, cl, "2.1")
    got = {c.id for c in ctx.clauses}
    assert {"Table 1", "Table 1 row 1", "Table 1 row 3"} <= got           # the thresholds travel with the clause
    assert "1" in got                                                      # so do the definitions...
    assert not [m for m in ctx.missing if "Table" in m]                    # ...and "Table 1" is found


def test_definitions_travel_with_every_clause():
    full = TABLES
    cl = split_text(full)
    assert next(c for c in cl if c.id == "1").kind == "definition"
    ctx = assemble_context("d", full, cl, "2.2")
    assert "1" in {c.id for c in ctx.clauses}


def test_a_code_reference_links_the_clauses():
    full = CODES
    cl = split_text(full)
    ctx = assemble_context("d", full, cl, "REQ-003")
    assert "REQ-002" in {c.id for c in ctx.clauses}


def test_multi_page_pdf_without_headers_and_footers(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for n in range(1, 6):
        page = doc.new_page()
        page.insert_text((50, 30), "ACME Design Standard - Issue 4", fontsize=9)
        page.insert_text((50, 80), f"Corridors on level {n} shall be at least 1.{n} m wide.", fontsize=11)
        page.insert_text((50, 110), "Doors on an escape route shall open in the direction of escape.", fontsize=11)
        page.insert_text((250, 820), f"Page {n} of 5", fontsize=9)
    path = tmp_path / "standard.pdf"
    doc.save(path)
    full, cl = split_document(path)
    assert "ACME Design Standard" not in full and "Page 3 of 5" not in full
    assert sum("Corridors on level" in c.text for c in cl) == 5
    assert all(full[c.start:c.end] == c.text for c in cl)


UNSTRUCTURED = """Design brief for the Harbour Clinic.

The clinic must keep every corridor at least 1.8 m wide because trolleys pass each other. Patients should never have to walk more than 30 m to reach a stair or an exit. Treatment rooms need an area of no less than 12 m2, unless they are used for consultation only, where 9 m2 is enough.

Waiting areas shall provide one seat per 2 m2 of floor.
"""

LEGAL = """PART II - MEANS OF ESCAPE

Rule 5. Travel distance
(1) The travel distance to the nearest exit shall not exceed 45 m.
    (a) in a room used for sleeping the distance is limited to 18 m;
    (b) in a stairwell there is no limit.
(2) Where two exits are provided the distance may be increased by 50 %.

Rule 6. Doors
(1) Doors on an escape route shall open in the direction of escape.
(2) Clear width of at least 0.9 m.

PART III - SERVICES
Rule 5. Plant rooms
(1) Plant rooms shall be ventilated.
"""

CODES = """REQ-001 Every bedroom shall have a window.
REQ-002 The area of each bedroom shall be at least 9 m2.
REQ-003 Corridors shall be at least 1.2 m wide, see REQ-002 for rooms.

- The main entrance door must be at least 1000 mm wide.
- Stairs shall have a riser height of at most 190 mm.
* Every storey shall have a second exit.
"""

TABLES = """1 Definitions
In this document, "habitable room" means a bedroom, a living room or a kitchen.

2 Requirements
2.1 Habitable rooms shall have a floor area as given in Table 1.

Table 1 | Room type | Minimum area
 | Bedroom | 9 m2
 | Living room | 14 m2
 | Kitchen | 6 m2

2.2 Each habitable room shall have a window of at least 10 % of its floor area.
"""

REPEATED = """1. General
1.1 Corridors shall be 1.2 m wide.
Appendix A
1. General
1.1 Doors shall be 0.8 m wide.
"""

MIXED = """Titre II : Dispositions

Article 3 : Les chambres doivent avoir une surface minimale de 9 m².
§ 2. Les couloirs doivent avoir une largeur d'au moins 1,20 m.
Art. 4.- Chaque logement doit disposer d'une issue.
"""


@pytest.mark.parametrize("style", __import__("reviewpulse.xeval.doc_styles", fromlist=["STYLES"]).STYLES)
def test_no_requirement_is_lost_or_merged_in_any_document_style(style):
    from reviewpulse.xeval.doc_styles import ITEMS, measure

    m = measure(ITEMS, style)
    assert m["recall"] == 1.0 and m["merged"] == 0, m
    if m["context"] is not None:
        assert m["context"] == 1.0, m


def test_word_document_numbering_and_headings_are_restored(tmp_path):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_heading("Safety requirements", level=1)
    d.add_paragraph("Corridors shall be at least 1.2 m wide.", style="List Number")
    d.add_paragraph("Doors shall open in the direction of escape.", style="List Number")
    d.add_paragraph("Stairs shall have handrails.", style="List Bullet")
    t = d.add_table(rows=2, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Table 1 Room", "Minimum area"
    t.rows[1].cells[0].text, t.rows[1].cells[1].text = "Bedroom", "9 m2"
    path = tmp_path / "r.docx"
    d.save(path)
    full, cl = split_document(path)
    assert "Corridors shall be at least 1.2 m wide." in full
    labels = [c.text.split()[0] for c in cl if c.kind != "table_row"]
    assert "1." in labels and "2." in labels, (labels, full)
    assert any(c.kind == "table_row" and c.parent == "Table 1" for c in cl)


def test_a_definition_travels_only_with_clauses_that_use_its_term():
    full = ('1 Definitions\nIn this document, "habitable room" means a bedroom or a kitchen.\n'
            '"Escape route" means a path from a room to an exit.\n\n'
            '2.1 A habitable room shall have a window.\n2.2 Stairs shall have a handrail.\n')
    cl = split_text(full)
    with_window = {c.id for c in assemble_context("d", full, cl, "2.1").clauses}
    with_stairs = {c.id for c in assemble_context("d", full, cl, "2.2").clauses}
    assert "1" in with_window and "1" not in with_stairs


def test_a_long_document_is_split_once_and_an_edit_is_never_served_stale(tmp_path, monkeypatch):
    from reviewpulse.rules import clauses as C

    doc = tmp_path / "req.md"
    doc.write_text(TABLES, encoding="utf-8")
    first = C.split_cached(doc, tmp_path / "cache")
    calls = []
    real = C.split_document
    monkeypatch.setattr(C, "split_document", lambda p: calls.append(p) or real(p))
    assert C.split_cached(doc, tmp_path / "cache") == first and not calls          # served from the cache
    doc.write_text(TABLES + "\n2.3 Every kitchen shall have a window.\n", encoding="utf-8")
    third = C.split_cached(doc, tmp_path / "cache")
    assert calls and len(third[1]) == len(first[1]) + 1                             # the edit is read
    assert len(list((tmp_path / "cache").glob("split_*.json"))) == 1                # old splits are dropped
    (next((tmp_path / "cache").glob("split_*.json"))).write_text("not json", encoding="utf-8")
    assert len(C.split_cached(doc, tmp_path / "cache")[1]) == len(third[1])         # a damaged cache is rebuilt


def test_many_clauses_read_at_once_never_collide_on_the_split_cache(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from reviewpulse.rules.clauses import split_cached

    doc = tmp_path / "req.md"
    doc.write_text(TABLES * 20, encoding="utf-8")
    with ThreadPoolExecutor(8) as pool:
        got = list(pool.map(lambda _: len(split_cached(doc, tmp_path / "cache")[1]), range(24)))
    assert len(set(got)) == 1 and got[0] > 0


def test_a_two_column_page_is_read_one_column_after_the_other(tmp_path):
    import pymupdf

    from reviewpulse.rules.clauses import split_document

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((40, 60), "Plan review checklist", fontsize=16)
    left = ["Rooms", "Label every room.", "Show the size of every room.", "Show the use of every room.", "Stairs",
            "Show the landings of every stair."]
    right = ["Doors", "Show the size of every door.", "Egress door min. 32 inches wide.", "Windows",
             "Show the egress windows of every sleeping room.", "Show the size of every window."]
    for k, line in enumerate(left):
        page.insert_text((40, 120 + 40 * k), line, fontsize=11)
    for k, line in enumerate(right):
        page.insert_text((320, 120 + 40 * k), line, fontsize=11)
    path = tmp_path / "form.pdf"
    doc.save(path)
    full, _clauses = split_document(path)
    order = [full.index(x) for x in ("Label every room", "Show the landings of every stair", "Show the size of every door",
                                       "Show the size of every window")]
    assert order == sorted(order), "the left column must be read entirely before the right column"
