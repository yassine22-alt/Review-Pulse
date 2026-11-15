from pathlib import Path

from reviewpulse.rules.clauses import split_document, split_text

DOC = Path(__file__).parents[2] / "docs" / "requirements_example.md"


def test_example_document_articles():
    full, cl = split_document(DOC)
    ids = [c.id for c in cl]
    for want in ("Art. 1", "Art. 2", "Art. 6.1", "Art. 6.3", "Art. 9", "Art. 9 a)", "Art. 9 h)"):
        assert want in ids, want
    for c in cl:
        assert c.text == full[c.start:c.end]
    six3 = next(c for c in cl if c.id == "Art. 6.3")
    assert "9.00" in six3.text and "2.20" in six3.text


def test_english_numbered_and_subitems():
    txt = ("Chapter 3 Dwellings\n"
           "3.1 Doors. Every door shall have a clear width of at least 800 mm.\n"
           "3.2 Corridors. Corridors shall be at least 1.0 m wide.\n"
           "a) except in storage rooms;\n"
           "b) except where a wider route exists.\n")
    cl = split_text(txt)
    assert [c.id for c in cl] == ["3.1", "3.2", "3.2 a)", "3.2 b)"]
    assert cl[2].parent == "3.2"
    assert all(c.text == txt[c.start:c.end] for c in cl)


def test_french_article_variants():
    txt = "Article 12 - Les portes ont 0,90 m.\nARTICLE 13 Les couloirs.\nArt. 14.2 Les chambres.\n"
    assert [c.id for c in split_text(txt)] == ["Art. 12", "Art. 13", "Art. 14.2"]


def test_a_reference_at_the_start_of_a_wrapped_line_does_not_start_a_clause():
    txt = ("233.3.1 Minimum Number. Where facilities contain 15 or fewer dwelling units, the requirements of\n"
           "233.3.1.1 and 233.3.1.2 shall apply to the total number of units constructed under one contract.\n"
           "\n"
           "233.3.2 Other Facilities. Facilities shall provide at least 5 percent accessible units.\n")
    ids = [c.id for c in split_text(txt)]
    assert ids == ["233.3.1", "233.3.2"]


def test_a_numbered_clause_after_a_finished_sentence_still_starts_a_clause():
    txt = ("3.1 Doors. Every door shall be at least 800 mm wide.\n"
           "3.2 Corridors. Corridors shall be at least 1.0 m wide.\n")
    assert [c.id for c in split_text(txt)] == ["3.1", "3.2"]


def test_a_heading_in_plain_type_is_not_the_tail_of_the_clause_above_it():
    txt = ("8.2\tCavity barriers should be provided to reduce the spread of fire.\n"
           "\n"
           "Junctions and cavity closures\n"
           "\n"
           "8.3\tCavity barriers should be provided at all of the following locations.\n")
    cl = split_text(txt)
    assert [c.id for c in cl] == ["8.2", "8.3"]
    assert "Junctions" not in cl[0].text
    assert cl[1].scope == "Junctions and cavity closures"
    assert cl[0].scope == ""


def test_a_short_sentence_before_a_numbered_clause_is_not_taken_for_a_heading():
    txt = ("8.2 Cavity barriers should be provided.\n"
           "\n"
           "Barriers shall be fitted.\n"
           "\n"
           "8.3 Another requirement shall apply.\n")
    cl = split_text(txt)
    assert "Barriers shall be fitted." in cl[0].text
