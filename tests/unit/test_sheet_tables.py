"""Sheet table reader: header meaning, units, rows by tag, planted schedules in three languages, metamorphic checks, and the door
fire rating of the old reader as a special case."""

import copy
import random

import pytest

from reviewpulse.interpreter.units import convert
from reviewpulse.schedules import (
    bind_to_tags,
    canonical_unit,
    door_fire_rows,
    header_unit,
    match_header,
    read_pdf_tables,
)
from reviewpulse.schedules.planted import draw_pdf, make_table_spec
from reviewpulse.schedules.reader import Word, read_tables, words_from_page
from reviewpulse.schedules.text_sheet import text_sheet
from reviewpulse.schedules.values import quantity, size


def _words(rows, y0=100.0, pitch=14.0, x0=40.0, col_w=90.0):
    out = []
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            x = x0 + c * col_w
            for k, part in enumerate(str(text).split(" ")):
                out.append(Word(part, x + k * 22, y0 + r * pitch, x + k * 22 + 5 * len(part), y0 + r * pitch + 9))
    return out


@pytest.mark.parametrize("header,meaning", [
    ("Fire Rating", "fire_rating"), ("Résistance au feu", "fire_rating"), ("Feuerwiderstandsklasse", "fire_rating"),
    ("Brüstungshöhe", "sill"), ("Largeur (mm)", "width"), ("Höhe [cm]", "height"), ("Hauteur sous plafond", "ceiling_height"),
    ("Revêtement de sol", "finish_floor"), ("Bodenbelag", "finish_floor"), ("Qté", "quantity"), ("Mark", "tag"),
    ("Door Width", "width"), ("Fläche (m²)", "area"),
])
def test_header_meaning(header, meaning):
    assert match_header(header).meaning == meaning


def test_unknown_header_is_not_typed():
    assert match_header("Zorblax").meaning is None


@pytest.mark.parametrize("header,unit", [("Width (mm)", "mm"), ("Area [m²]", "m2"), ("Fire rating (HR)", "h"), ("Width, cm", "cm"),
                                          ("Width", None), ("Hauteur (m)", "m")])
def test_header_unit(header, unit):
    assert header_unit(header) == unit


@pytest.mark.parametrize("cell,expect", [
    ("900", (900.0, None)), ("0,9", (0.9, None)), ("900 mm", (900.0, "mm")), ("3'-0\"", (36.0, "in")), ("36\"", (36.0, "in")),
    ("6'8\"", (80.0, "in")), ("2 1/2\"", (2.5, "in")), ("12.5 sf", (12.5, "ft2")), ("1-1/2 HR", (1.5, "h")), ("abc", None),
])
def test_quantity(cell, expect):
    assert quantity(cell) == expect


def test_size_cell():
    assert size("900 x 2100 mm") == [(900.0, "mm"), (2100.0, "mm")]
    assert size("3'-0\" x 6'-8\"") == [(36.0, "in"), (80.0, "in")]


def test_unruled_door_schedule_from_words():
    rows = [["DOOR SCHEDULE"], ["Mark", "Width (mm)", "Height (mm)", "Fire Rating"], ["D-1", "900", "2100", "20 MIN"],
            ["D-2", "800", "2100", "1 HR"], ["D3", "1000", "2400", "NR"]]
    t = read_tables(_words(rows), "s")
    assert len(t) == 1 and t[0].kind == "doors"
    got = {(c.entity_tag, c.meaning): c for c in t[0].candidates}
    assert got[("D1", "width")].value_si == pytest.approx(0.9)
    assert got[("D2", "fire_rating")].value == 60.0 and got[("D2", "fire_rating")].unit == "min"
    assert got[("D3", "fire_rating")].value == 0.0
    assert got[("D1", "width")].cell_text == "900" and got[("D1", "width")].sheet == "s"
    assert bind_to_tags(t[0].candidates, {"D 1": "el1"}) == 3 and got[("D1", "width")].element_id == "el1"


def test_prose_is_not_a_table():
    words = _words([["The door width and height are given in the schedule on sheet A5."], ["Fire rating notes follow"]])
    assert read_tables(words, "s") == []


@pytest.mark.parametrize("lang", ["en", "fr", "de"])
@pytest.mark.parametrize("ruled", [False, True])
def test_planted_door_and_window_recall_precision(tmp_path, lang, ruled):
    right = truth_n = emitted = 0
    for seed in range(6):
        kind = "doors" if seed % 2 == 0 else "windows"
        spec = make_table_spec(kind, lang, random.Random(seed), unit=["mm", "cm", "m"][seed % 3], ruled=ruled)
        p = draw_pdf(str(tmp_path / f"{lang}{ruled}{seed}.pdf"), [spec], seed=seed)
        tables = read_pdf_tables(p.path)
        found = {(c.entity_tag, c.meaning): c for t in tables for c in t.candidates if c.entity_tag}
        for (_, tag, meaning), want in p.truth.items():
            truth_n += 1
            c = found.get((tag, meaning))
            if c is None:
                continue
            got = c.value if isinstance(want, str) or meaning == "quantity" else c.value_si
            if (isinstance(want, str) and str(got).lower() == want) or (not isinstance(want, str) and got is not None
                                                                      and abs(got - want) < 1e-6):
                right += 1
        emitted += len(found)
    assert right / truth_n >= 0.95
    assert right / emitted >= 0.9


def test_planted_other_kinds_typed(tmp_path):
    for kind in ("rooms", "finishes", "fixtures"):
        spec = make_table_spec(kind, "fr", random.Random(3), unit="m")
        p = draw_pdf(str(tmp_path / f"{kind}.pdf"), [spec])
        t = read_pdf_tables(p.path)
        assert len(t) == 1 and t[0].kind == kind


def test_metamorphic_value_and_unit(tmp_path):
    import pymupdf

    spec = make_table_spec("doors", "en", random.Random(2), unit="mm", n_rows=5)
    p = draw_pdf(str(tmp_path / "m.pdf"), [spec], seed=2)
    words = words_from_page(pymupdf.open(p.path)[0])
    base = {(c.entity_tag, c.meaning): c for t in read_tables(words, "s") for c in t.candidates}
    w = [c for c in base.values() if c.meaning == "width"]
    target = w[0]
    w2 = copy.deepcopy(words)
    hit = next(x for x in w2 if x.text == target.cell_text)
    hit.text = "777"
    alt = {(c.entity_tag, c.meaning): c for t in read_tables(w2, "s") for c in t.candidates}
    changed = [k for k in base if base[k].cell_text != alt[k].cell_text]
    assert len(changed) >= 1 and all(alt[k].value == 777.0 for k in changed)
    w3 = copy.deepcopy(words)
    for x in w3:
        if x.text == "(mm)":
            x.text = "(cm)"
    alt = {(c.entity_tag, c.meaning): c for t in read_tables(w3, "s") for c in t.candidates}
    for k, c in base.items():
        if c.meaning in ("width", "height"):
            assert alt[k].unit == "cm" and alt[k].value == c.value
            assert alt[k].value_si == pytest.approx(convert(c.value, "cm", "m"))


def test_imperial_equals_metric():
    rows = [["Mark", "Width", "Height"], ["D1", "3'-0\"", "6'-8\""], ["D2", "2'-8\"", "6'-8\""]]
    t = read_tables(_words(rows), "s")
    c = {(x.entity_tag, x.meaning): x for x in t[0].candidates}
    assert c[("D1", "width")].unit == "in" and c[("D1", "width")].value == 36.0
    assert c[("D1", "width")].value_si == pytest.approx(0.9144)


def test_door_fire_special_case_matches_old_reader(tmp_path):
    import pymupdf

    from reviewpulse.annotate.schedules import find_schedules
    from reviewpulse.annotate.text_classify import classify_items

    pytest.importorskip("pymupdf")
    for seed, lang in enumerate(["en", "fr", "de", "en"]):
        spec = make_table_spec("doors", lang, random.Random(seed), ruled=False)
        p = draw_pdf(str(tmp_path / f"f{seed}.pdf"), [spec], seed=seed)
        sheet = text_sheet(pymupdf.open(p.path)[0], "o")
        classify_items(sheet.texts)
        old = {r["tag"]: r["fire_rating_min"] for s in find_schedules(sheet)[0] for r in s["rows"] if "fire_rating_min" in r}
        new = door_fire_rows(read_pdf_tables(p.path))
        for k, v in old.items():
            assert new.get(k) == v
    assert canonical_unit("HR") == "h"


def test_abbreviation_list_is_not_a_table():
    rows = [["CLG", "- CEILING"], ["CLR", "- CLEAR"], ["CMU", "- CONCRETE MASONRY UNIT"], ["D", "- DEPTH"], ["DIM", "- DIMENSION"]]
    assert read_tables(_words(rows), "s") == []


def test_header_words_in_a_longer_header_do_not_type_it():
    assert match_header("Wall Description").meaning != "finish_wall"
    assert match_header("Bottom of Glass").score < 0.6
    assert match_header("Wall").meaning == "finish_wall"


def test_numbers_under_a_text_header_are_not_typed():
    rows = [["Mark", "Floor", "Qty"], ["D1", "1", "2"], ["D2", "2", "1"]]
    t = read_tables(_words(rows), "s")
    assert t and [c.meaning for c in t[0].columns][1] is None


def test_fire_column_of_dashes_is_unknown_not_zero_minutes():
    rows = [["Door", "Fire Label", "Width (in)"], ["D1", "-", "36"], ["D2", "NR", "30"], ["D3", "1 HR", "36"]]
    t = read_tables(_words(rows), "s")
    got = {c.entity_tag: c.value for c in t[0].candidates if c.meaning == "fire_rating"}
    assert got.get("D3") == 60.0
    assert "D1" not in got                  # a dash says nothing: no rating stated, so no value at all
    assert got.get("D2") == 0.0             # "NR" says not rated
