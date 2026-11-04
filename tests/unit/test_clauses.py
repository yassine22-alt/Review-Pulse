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
