"""Requirement documents that arrive as spreadsheets, web pages, scans or lists drawn with symbol-font bullets."""

from reviewpulse.rules import readers
from reviewpulse.rules.clauses import split_document, split_text

ITEMS = ["Hallways must be at least 0.9 m wide.", "Every habitable room shall have a window.",
         "Doors serving exits shall be at least 0.8 m wide."]


def _texts(path):
    _, cl = split_document(path)
    return [" ".join(c.text.split()).lstrip("-* ") for c in cl if c.kind != "heading"]


def test_a_spreadsheet_checklist_gives_one_clause_per_row(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for i, t in enumerate(ITEMS, 1):
        ws.append([i, t, "yes / no / n.a."])
    f = tmp_path / "check.xlsx"
    wb.save(str(f))
    got = _texts(f)
    assert [t.removeprefix("") for t in got] == ITEMS               # the answer column is not part of the requirement
    f.unlink()                                                       # the workbook is closed: Windows can delete it


def test_a_csv_with_semicolons_and_commas_in_the_text_is_cut_into_its_columns(tmp_path):
    import csv

    f = tmp_path / "c.csv"
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Code", "Requirement"])
        for i, t in enumerate(ITEMS, 1):
            w.writerow([f"R{i}", t + " Also, check the drawing; note it."])
    text = readers.sheet_text(f)
    assert "R1" in text and "Hallways must be at least 0.9 m wide." in text
    assert ";" in text                                               # the semicolon inside the sentence survived


def test_a_web_page_keeps_headings_list_items_and_table_rows(tmp_path):
    f = tmp_path / "p.html"
    f.write_text("<html><head><style>li{color:red}</style><script>var x=1;</script></head><body><h2>Doors</h2><ul>"
                 "<li>Doors shall be at least 0.8 m wide.</li><li>Exit doors shall open outwards.</li></ul>"
                 "<table><tr><th>Room</th><th>Minimum area</th></tr><tr><td>Bedroom</td><td>7 m2</td></tr></table></body></html>",
                 encoding="utf-8")
    text = readers.html_text(f)
    assert "# Doors" in text and "- Doors shall be at least 0.8 m wide." in text
    assert "Bedroom | 7 m2" in text and "var x" not in text and "color:red" not in text


def test_a_list_drawn_with_symbol_font_bullets_is_one_clause_per_bullet():
    txt = "Floor Plans\n\n Intended use of each room\n Location of all smoke detectors\n Plans must be to scale\n"
    cl = split_text(txt)
    assert [c.kind for c in cl] == ["subitem"] * 3
    assert cl[2].scope == "Floor Plans"


def test_a_list_item_cut_by_a_page_break_is_one_clause():
    txt = (" Basements and every sleeping room shall have one operable window or exterior\n\n"
           "door approved for emergency egress.\n\n"
           " Location of all smoke detectors\n")
    cl = split_text(txt)
    assert len(cl) == 2
    assert "door approved for emergency egress." in cl[0].text


def test_ocr_lines_that_wrap_are_joined_into_sentences():
    lines = ["- Hallways must be at least", "0.9 m wide.", "- Doors shall open outwards."]
    assert readers.join_ocr_lines(lines).splitlines() == ["- Hallways must be at least 0.9 m wide.", "- Doors shall open outwards."]


def test_a_scanned_pdf_is_read_with_ocr(tmp_path):
    import pytest

    if not readers.ocr_available():
        pytest.skip("OCR is not installed")
    import pymupdf

    page_doc = pymupdf.open()
    page = page_doc.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(50, 60, 545, 300), "Hallways must be at least 0.9 m wide.\nEvery bedroom shall have a window.",
                        fontsize=14)
    raster = pymupdf.open()
    pix = page_doc[0].get_pixmap(dpi=170)
    p = raster.new_page(width=595, height=842)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    f = tmp_path / "scan.pdf"
    raster.save(str(f))
    text = " ".join(" ".join(c.text.split()) for c in split_document(f)[1]).lower()
    assert "hallways must be at least 0.9 m wide" in text
    assert "bedroom" in text
