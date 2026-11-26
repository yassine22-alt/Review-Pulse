"""A table in a PDF takes the name of its caption, so "see Table B4" in the text reaches it; a table that goes on over the page
stays one table."""

import pymupdf
import pytest

from reviewpulse.interpreter.context import REFERENCE, assemble_context
from reviewpulse.rules import clauses as cl


def _grid(page, x0, y0, rows, col_w=140, row_h=22):
    cols = len(rows[0])
    for r in range(len(rows) + 1):
        page.draw_line((x0, y0 + r * row_h), (x0 + cols * col_w, y0 + r * row_h))
    for c in range(cols + 1):
        page.draw_line((x0 + c * col_w, y0), (x0 + c * col_w, y0 + len(rows) * row_h))
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            page.insert_text((x0 + c * col_w + 4, y0 + r * row_h + 15), cell, fontsize=9)


@pytest.fixture
def doc(tmp_path):
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((60, 60), "1.1 Fire doors shall have the resistance given in Table B4.", fontsize=10)
    p.insert_text((60, 80), "1.2 Table 3 gives the widths that shall be provided.", fontsize=10)
    p.insert_text((60, 120), "Table B4 Minimum periods of fire resistance", fontsize=10)
    _grid(p, 60, 130, [["Building", "Minutes"], ["Dwelling", "30"], ["Office", "60"]])
    p.insert_text((60, 300), "Table 3 Minimum widths", fontsize=10)
    _grid(p, 60, 310, [["Element", "Width"], ["Corridor", "1200 mm"]])
    q = d.new_page()
    q.insert_text((60, 60), "Table B4 Continued", fontsize=10)
    _grid(q, 60, 70, [["Building", "Minutes"], ["Shop", "90"]])
    path = tmp_path / "tables.pdf"
    d.save(path)
    return path


def test_tables_take_the_name_of_their_caption_and_continue_over_the_page(doc):
    _, clauses = cl.split_document(doc)
    by_id = {c.id: c for c in clauses}
    assert by_id["Table B4"].kind == "table_header" and by_id["Table 3"].kind == "table_header"
    rows = [c.text for c in clauses if c.parent == "Table B4"]
    assert rows == ["Dwelling | 30", "Office | 60", "Shop | 90"]          # the repeated header of page 2 is not a row
    assert [c.id for c in clauses if c.parent == "Table B4"][-1] == "Table B4 row 3"


def test_a_reference_in_the_text_reaches_the_table(doc):
    full, clauses = cl.split_document(doc)
    target = next(c.id for c in clauses if "Fire doors" in c.text)
    bundle = assemble_context("tables.pdf", full, clauses, target)
    got = {c.id for c in bundle.clauses}
    assert {"Table B4", "Table B4 row 1", "Table B4 row 3"} <= got
    assert not [m for m in bundle.missing if "B4" in m]


def test_a_sentence_that_starts_with_a_table_name_is_not_a_caption(doc):
    page = pymupdf.open(doc)[0]
    assert [c[2] for c in cl._captions(page)] == ["Table B4", "Table 3"]


def test_reference_pattern_reads_annex_tables_and_plurals():
    found = [(m.group(1).lower(), m.group(2)) for m in REFERENCE.finditer("see Table B4, Tables C1 and table 12.3 and section 4")]
    assert found == [("table", "B4"), ("tables", "C1"), ("table", "12.3"), ("section", "4")]


def test_the_page_limit_is_a_count_not_a_clock(monkeypatch, doc):
    monkeypatch.setattr(cl, "TABLE_PAGE_BUDGET", 1)
    rows, unscanned = cl._find_tables(doc, [0, 1])
    assert unscanned == [2] and {r[0] for r in rows} == {0}
