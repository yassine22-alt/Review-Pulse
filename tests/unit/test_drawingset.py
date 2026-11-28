"""The drawing set model: scales, vocabularies in several languages, views, callouts and their resolution, the index against
title blocks, legends, levels, and the metamorphic properties (rotate a page, rename a sheet number, move a view)."""

from __future__ import annotations

import numpy as np
import pytest

from reviewpulse.drawingset import Line, PageData, build_drawing_set, from_pdf
from reviewpulse.drawingset.pagedata import canonicalize, rename_sheet, rotate_cw90, translate_box
from reviewpulse.drawingset.refs import parse_text_callouts
from reviewpulse.drawingset.scale import parse_scale
from reviewpulse.drawingset.views import classify_kind, read_level
from reviewpulse.drawingset.vocab import load_vocab, norm_id, shape

V = load_vocab()
W, H = 1200.0, 800.0


def ln(text, x, y, size=10.0):
    return Line(text, x, y, x + 0.55 * size * len(text), y + size, size)


def box(x0, y0, x1, y1):
    return [x0, y0, x1, y1]


def title_block(number, title):
    return [ln("SHEET NUMBER", 1110, 700, 8), ln(number, 1110, 650, 30), ln("DATE", 1110, 730, 8),
            ln("DRAWN BY", 1110, 760, 8), ln(title, 1110, 300, 16)]


def view(label, title, scale, x0, y0, x1, y1, rects):
    """A drawn box with a numbered title bar and a scale line under it, as on a real sheet."""
    rects.append(box(x0, y0, x1, y1))
    lines = [ln(title, x0 + 30, y1 + 14, 16), ln(scale, x0 + 30, y1 + 36, 9)]
    if label:
        lines.append(ln(label, x0 + 6, y1 + 14, 16))
    return lines


def sheet_a101():
    rects = []
    lines = title_block("A-101", "FLOOR PLANS")
    lines += view("1", "FLOOR PLAN", "SCALE: 1/4\" = 1'-0\"", 40, 40, 480, 600, rects)
    lines += view("2", "ENLARGED PLAN", "SCALE: 1/2\" = 1'-0\"", 600, 40, 1000, 400, rects)
    lines += [ln("SEE DETAIL 2/A-501 FOR JAMB", 120, 300), ln("3/A-501", 700, 200), ln("VOIR DETAIL 1", 700, 250),
              ln("Detail 2 / Sheet A-501", 700, 300), ln("SEE DETAIL 9/A-501", 700, 350), ln("2/XY99", 120, 360)]
    return PageData(1, W, H, lines, np.array(rects, dtype=float))


def sheet_a501():
    rects = []
    lines = title_block("A-501", "SECTIONS AND DETAILS")
    lines += view("1", "WALL SECTION", "1:20", 40, 40, 480, 600, rects)
    lines += view("2", "JAMB DETAIL", "1\" = 1'-0\"", 600, 40, 1000, 300, rects)
    lines += view("3", "SILL DETAIL", "3\" = 1'-0\"", 600, 400, 1000, 600, rects)
    return PageData(2, W, H, lines, np.array(rects, dtype=float))


def sheet_index_page():
    rects = []
    lines = title_block("G-001", "COVER")
    lines += [ln("SHEET INDEX", 40, 40, 18)]
    for i, (n, t) in enumerate([("G-001", "COVER"), ("A-101", "FLOOR PLANS"), ("A-501", "SECTIONS AND DETAILS"), ("A-901", "SCHEDULES")]):
        lines += [ln(n, 40, 80 + 20 * i), ln(t, 140, 80 + 20 * i)]
    return PageData(0, W, H, lines, np.array(rects).reshape(-1, 4))


def the_set():
    return [sheet_index_page(), sheet_a101(), sheet_a501()]


# ---- vocabularies ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,ratio,system", [
    ("1/4\" = 1'-0\"", 48.0, "imperial"), ("3\" = 1'-0\"", 4.0, "imperial"), ("1 1/2\" = 1'-0\"", 8.0, "imperial"),
    ("1\" = 20'", 240.0, "imperial"), ("M 1:100", 100.0, "metric"), ("Maßstab 1:50", 50.0, "metric"), ("Echelle 1:200", 200.0, "metric"),
])
def test_scales(text, ratio, system):
    s = parse_scale(text, V)
    assert s is not None and s.ratio == pytest.approx(ratio) and s.system == system
    assert s.metres_per_point == pytest.approx(ratio * 0.0254 / 72)


def test_scale_nts_and_slash_needs_label():
    assert parse_scale("NOT TO SCALE", V).nts
    assert parse_scale("N.T.S.", V).nts
    assert parse_scale("ESCALA 1/100", V).ratio == 100
    assert parse_scale("1/100", V) is None            # without a label a fraction is not a scale
    assert parse_scale("10'-1 1/8\"", V) is None      # a dimension, not a scale


@pytest.mark.parametrize("title,kind", [
    ("FLOOR PLAN", "plan"), ("GRUNDRISS EG", "plan"), ("Plan du 1er etage", "plan"), ("PLANTA BAJA", "plan"),
    ("COUPE A-A", "section"), ("Schnitt B-B", "section"), ("SECCION TRANSVERSAL", "section"),
    ("FRONT ELEVATION", "elevation"), ("Ansicht Nord", "elevation"), ("ALZADO SUR", "elevation"),
    ("WINDOW DETAIL", "detail"), ("Detail de seuil", "detail"), ("DETALLE DE ZOCALO", "detail"),
    ("DOOR SCHEDULE", "schedule"), ("Fensterliste", "schedule"), ("CUADRO DE VENTANAS", "schedule"),
    ("LEGEND", "legend"), ("Zeichenerklärung", "legend"), ("LEYENDA", "legend"), ("ABBREVIATIONS", "legend"),
    ("GENERAL NOTES:", "notes"), ("Remarques", "notes"), ("Hinweise", "notes"),
    ("SHEET INDEX", "index"), ("Planverzeichnis", "index"), ("Liste des plans", "index"),
    ("SITE PLAN", "site"), ("Lageplan", "site"),
])
def test_view_kind_words_in_four_languages(title, kind):
    assert classify_kind(title, V) == kind


def test_level_words():
    assert read_level("FIRST FLOOR PLAN", V) == ("level 1", 1)
    assert read_level("2ND FLOOR PLAN", V) == ("level 2", 2)
    assert read_level("Grundriss EG", V) == ("ground", 0)
    assert read_level("Grundriss 1. Obergeschoss", V) == ("level 1", 1)
    assert read_level("Untergeschoss", V)[0] == "basement"
    assert read_level("Plan du 2eme etage", V)[1] == 2
    assert read_level("PLANTA BAJA", V)[0] == "ground"
    assert read_level("ROOF PLAN", V)[0] == "roof"


def test_callout_grammars_in_four_languages():
    def refs(*texts):
        pg = PageData(0, W, H, [ln(t, 10, 10 + 20 * i) for i, t in enumerate(texts)])
        return [(c.view_label, c.target_sheet, c.kind) for c in parse_text_callouts(pg, V, None)]

    assert refs("3/A-501") == [("3", "A-501", None)]
    assert refs("SEE DETAIL 4") == [("4", None, "detail")]
    assert refs("voir détail 4") == [("4", None, "detail")]
    assert refs("siehe Schnitt A-A") == [("A-A", None, "section")]
    assert refs("ver detalle 7") == [("7", None, "detail")]
    assert refs("Detail 2 / Sheet 5") == [("2", "5", "detail")]
    assert refs("détail 3, feuille A3") == [("3", "A3", "detail")]
    assert refs("Detail 4 auf Blatt 7") == [("4", "7", "detail")]
    assert refs("DETAIL 6-S3") == [("6", "S3", "detail")]
    assert refs("SEE SHEET A-501") == [(None, "A-501", None)]
    assert refs("2 X 6 STUDS @ 16\" O.C.") == []
    assert refs("1/4\" = 1'-0\"") == []


def test_ids():
    assert norm_id("A-5.01") == norm_id("a501") == "A501"
    assert shape("A3.01") == "A9.99" and shape("S2") == "A9"


# ---- the model ------------------------------------------------------------------------------------------------------

def test_sheets_numbers_titles_views_and_own_scales():
    ds = build_drawing_set(the_set(), "t")
    nums = {s.index: s.number for s in ds.sheets}
    assert nums == {0: "G-001", 1: "A-101", 2: "A-501"}
    assert ds.sheets[1].title == "FLOOR PLANS"
    v1 = ds.sheets[1].views
    assert sorted(v.kind for v in v1) == ["plan", "plan"]
    scales = sorted(v.scale.ratio for v in v1)
    assert scales == [24.0, 48.0]                       # two views, two scales, each its own
    assert all(v.scale_source == "title" for v in v1)
    v2 = ds.sheets[2].views
    assert sorted(v.kind for v in v2) == ["detail", "detail", "section"]
    assert {v.kind: v.scale.ratio for v in v2 if v.kind == "section"} == {"section": 20.0}
    assert {v.scale.system for v in v2} == {"metric", "imperial"}


def test_views_do_not_overlap_and_have_a_frame_in_page_points():
    ds = build_drawing_set(the_set(), "t")
    for s in ds.sheets[1:]:
        for a in s.views:
            assert a.bbox[2] > a.bbox[0] and a.bbox[3] > a.bbox[1]
            for b in s.views:
                if a is not b:
                    ix = min(a.bbox[2], b.bbox[2]) - max(a.bbox[0], b.bbox[0])
                    iy = min(a.bbox[3], b.bbox[3]) - max(a.bbox[1], b.bbox[1])
                    assert not (ix > 0 and iy > 0)
    v = ds.sheets[1].views[0]
    assert v.scale.metres_per_point > 0


def test_callouts_resolve_to_views_and_unresolved_say_why():
    ds = build_drawing_set(the_set(), "t")
    by = {c.text: c for c in ds.callouts}
    c = by["SEE DETAIL 2/A-501"] if "SEE DETAIL 2/A-501" in by else next(c for c in ds.callouts if c.view_label == "2" and c.target_sheet == "A-501")
    assert c.status == "view"
    tv = {v.id: v for v in ds.views()}[c.target_view]
    assert tv.title == "JAMB DETAIL" and tv.sheet == 2
    c3 = next(c for c in ds.callouts if c.text == "3/A-501")
    assert tv.kind == "detail" and {v.id: v for v in ds.views()}[c3.target_view].title == "SILL DETAIL"
    local = next(c for c in ds.callouts if c.grammar == "ref_kind_view_local")
    assert local.status == "view" and {v.id: v for v in ds.views()}[local.target_view].title == "FLOOR PLAN"
    sheet_form = next(c for c in ds.callouts if c.grammar == "kind_view_sheetword_sheet")
    assert sheet_form.status == "view"
    missing = next(c for c in ds.callouts if c.view_label == "9")
    assert missing.status == "partial" and "no view 9" in missing.reason
    rejected = next(c for c in ds.callouts if c.target_sheet == "XY99")
    assert rejected.status == "rejected_shape"


def test_index_against_title_blocks():
    ds = build_drawing_set(the_set(), "t")
    st = {e.number: e.status for e in ds.index}
    assert st["A-101"] == "match" and st["A-501"] == "match" and st["G-001"] == "match"
    assert st["A-901"] == "not in set"
    assert ds.index_missing == []


def test_legend_rows_are_kept_with_their_symbol():
    rects = []
    lines = title_block("A-001", "LEGEND") + [ln("LEGEND", 40, 40, 18), ln("SMOKE ALARM", 100, 100), ln("EXIT SIGN", 100, 140)]
    rects += [box(60, 100, 90, 112), box(60, 140, 90, 152)]
    ds = build_drawing_set([PageData(0, W, H, lines, np.array(rects, dtype=float))], "t")
    assert [v.kind for v in ds.views()] == ["legend"]
    rows = {e.words: e for e in ds.legend}
    assert set(rows) == {"SMOKE ALARM", "EXIT SIGN"}
    assert all(e.symbol_bbox is not None and e.n_paths == 1 for e in rows.values())


def test_plan_views_get_levels_from_title_words():
    rects = []
    lines = title_block("A-102", "PLANS") + view("1", "FIRST FLOOR PLAN", "1/4\" = 1'-0\"", 40, 40, 480, 600, rects) \
        + view("2", "SECOND FLOOR PLAN", "1/4\" = 1'-0\"", 600, 40, 1000, 600, rects)
    ds = build_drawing_set([PageData(0, W, H, lines, np.array(rects, dtype=float))], "t")
    assert sorted((v.level, v.level_rank) for v in ds.views()) == [("level 1", 1), ("level 2", 2)]


def test_a_sheet_with_one_scale_for_all_is_marked_as_sheet_default():
    rects = []
    lines = title_block("A-1", "PLAN") + [ln("SCALE: 1:50", 1110, 200, 8), ln("FLOOR PLAN", 100, 640, 16), ln("1", 70, 640, 16)]
    rects.append(box(40, 40, 900, 620))
    ds = build_drawing_set([PageData(0, W, H, lines, np.array(rects, dtype=float))], "t")
    v = ds.views()[0]
    assert v.kind == "plan" and v.scale.ratio == 50 and v.scale_source == "sheet"


# ---- metamorphic ----------------------------------------------------------------------------------------------------

def sig(ds):
    views = {v.id: v for v in ds.views()}
    cs = sorted((c.sheet, c.text, c.status, views[c.target_view].title if c.target_view else None) for c in ds.callouts)
    vs = sorted((v.sheet, v.kind, v.title, tuple(v.labels), v.scale.text if v.scale else None) for v in ds.views())
    return cs, vs, [(e.number, e.status) for e in ds.index]


@pytest.mark.parametrize("k", [1, 2, 3])
def test_rotating_every_page_changes_nothing(k):
    pages = the_set()
    base = sig(build_drawing_set(pages, "t"))
    rot = []
    for p in pages:
        q = p
        for _ in range(k):
            q = rotate_cw90(q)
        rot.append(canonicalize(q))
    assert sig(build_drawing_set(rot, "t")) == base


def test_renaming_a_sheet_number_everywhere_keeps_every_reference():
    pages = the_set()
    base = build_drawing_set(pages, "t")
    ren = build_drawing_set(rename_sheet(pages, "A-501", "Z-77"), "t")
    assert [s.number for s in ren.sheets] == ["G-001", "A-101", "Z-77"]
    a = sorted((c.sheet, c.status, c.target_sheet_index, c.target_view and c.target_view.split(".")[0]) for c in base.callouts)
    b = sorted((c.sheet, c.status, c.target_sheet_index, c.target_view and c.target_view.split(".")[0]) for c in ren.callouts)
    assert a == b
    assert sum(c.status == "view" for c in ren.callouts) == sum(c.status == "view" for c in base.callouts) > 0


def test_a_renamed_target_that_is_only_renamed_in_the_title_block_loses_the_reference():
    """Negative control: if the callouts are not renamed they must stop resolving to that sheet."""
    pages = the_set()
    pages2 = [p for p in pages]
    sh = next(p for p in pages2 if p.index == 2)
    for line in sh.lines:
        if line.text == "A-501":
            line.text = "Z-77"
    ds = build_drawing_set(pages2, "t")
    assert any(c.status == "unresolved_sheet" for c in ds.callouts)


def test_moving_a_view_keeps_references_and_moves_its_frame():
    pages = the_set()
    base = build_drawing_set(pages, "t")
    v = next(v for v in base.sheets[2].views if v.title == "JAMB DETAIL")
    moved = [p if p.index != 2 else translate_box(p, (v.bbox[0] - 2, v.bbox[1] - 2, v.bbox[2] + 2, v.bbox[3] + 2), 40, 0) for p in pages]
    ds = build_drawing_set(moved, "t")
    assert sig(ds)[0] == sig(base)[0]
    v2 = next(v for v in ds.sheets[2].views if v.title == "JAMB DETAIL")
    assert v2.bbox[0] == pytest.approx(v.bbox[0] + 40, abs=12)
    assert v2.scale.ratio == v.scale.ratio


# ---- the production reader ------------------------------------------------------------------------------------------

def _pdf(path, rotation=0):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=1200, height=800)
    for t, x, y, size in [("SHEET NUMBER", 1110, 90, 8), ("A-101", 1110, 130, 30), ("DATE", 1110, 160, 8), ("DRAWN BY", 1110, 180, 8),
                          ("FLOOR PLAN", 100, 650, 16), ("1", 70, 650, 16), ("SCALE: 1/4\" = 1'-0\"", 100, 672, 9),
                          ("WALL SECTION", 600, 650, 16), ("2", 570, 650, 16), ("1:20", 600, 672, 9), ("SEE DETAIL 2", 300, 300, 10)]:
        page.insert_text((x, y), t, fontsize=size)
    page.draw_rect(pymupdf.Rect(40, 40, 480, 620))
    page.draw_rect(pymupdf.Rect(560, 40, 1000, 620))
    page.set_rotation(rotation)
    doc.save(str(path))


def test_pdf_reader_and_page_rotation(tmp_path):
    outs = []
    for rot in (0, 90, 180, 270):
        p = tmp_path / f"r{rot}.pdf"
        _pdf(p, rot)
        ds = build_drawing_set(from_pdf(p), "t")
        outs.append(sig(ds))
        assert ds.sheets[0].number == "A-101"
        assert sorted((v.kind, v.scale.ratio) for v in ds.views()) == [("plan", 48.0), ("section", 20.0)]
        assert [c.status for c in ds.callouts] == ["view"]
    assert all(o == outs[0] for o in outs)


def test_ocr_lines_are_merged_without_duplicates():
    from reviewpulse.drawingset.pagedata import from_ocr_words, merge_ocr

    pg = sheet_a501()
    n = len(pg.lines)
    ocr = from_ocr_words(1, W, H, [("SEE", 120, 300, 150, 312), ("DETAIL", 155, 300, 200, 312), ("2/A-501", 205, 300, 260, 312),
                                   ("WALL", 100, 500, 130, 512)])
    merged = merge_ocr(pg, ocr.lines)
    assert len(merged.lines) == n + 2          # the two OCR rows are new; the original page is untouched
    assert len(pg.lines) == n
    ds = build_drawing_set([sheet_a101(), merged], "t")
    assert any(c.text == "2/A-501" and c.sheet == 1 for c in ds.callouts)
