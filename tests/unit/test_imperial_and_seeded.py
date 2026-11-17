"""Drawings and documents written in feet and inches, and rooms separated by their names."""

from __future__ import annotations

import pytest
from shapely.geometry import box

from reviewpulse.annotate.scale import DimPair, consensus, title_block_scale
from reviewpulse.annotate.text_classify import classify
from reviewpulse.interpreter.quantities import one_unit_system
from reviewpulse.perception.seeded import seeds_from_texts, split_region
from reviewpulse.schema import Prov, TextItem


@pytest.mark.parametrize("text,mm", [("12'", 3657.6), ("5'-9 3/4\"", 1771.65), ("15'-0 1/8\"", 4575.175),
                                     ("8\"", 203.2), ("4'-5\"", 1346.2), ("10′-3 5/8″", 3140.075)])
def test_feet_and_inches_are_dimensions(text, mm):
    c = classify(text)
    assert c.kind == "dimension" and c.unit == "mm" and c.value == pytest.approx(mm, abs=0.01)


@pytest.mark.parametrize("text", ["12", "Room 3'", "1/2", "3 ft"])
def test_a_plain_number_or_a_word_is_not_imperial(text):
    assert classify(text).kind != "dimension"


def test_printed_areas_in_square_feet_become_square_metres():
    c = classify("288 SQ FT")
    assert c.kind == "area" and c.unit == "m2" and c.value == pytest.approx(26.756, abs=0.01)
    assert classify("14,5 m2").value == pytest.approx(14.5)


@pytest.mark.parametrize("text,denominator", [('1/4"=1\'', 48), ('SCALE: 1/8" = 1\'-0"', 96), ('3/16" = 1\'', 64),
                                              ("Scale 1:100", 100)])
def test_the_written_scale_is_read(text, denominator):
    t = TextItem(id="t", text=text, bbox=(0, 0, 1, 1), prov=Prov(source="vector", stage="test"))
    assert title_block_scale([t]) == denominator


def _pair(i, ratio):
    return DimPair(f"t{i}", f"l{i}", (0, 0), (1, 0), ratio, 1.0, ratio)


def test_scattered_dimension_pairs_give_no_scale_rather_than_a_confident_wrong_one():
    ratios = [4.7, 75.5, 76.9, 92.8, 114, 120, 120, 222]
    s, inl, _out, conf = consensus([_pair(i, r) for i, r in enumerate(ratios)])
    assert s is None or conf < 0.6


def test_agreeing_pairs_still_give_the_scale():
    s, inl, _out, conf = consensus([_pair(i, r) for i, r in enumerate([100.2, 99.8, 100.5, 99.9, 101, 150])])
    assert s == 100 and len(inl) >= 4 and conf >= 0.6


@pytest.mark.parametrize("before,after", [
    ("at least 54 inches (1370 mm) above the floor", "at least 1370 mm above the floor"),
    ("clear width 1.2 m (4 ft) minimum", "clear width 1.2 m minimum"),
    ("minimum 3 ft 6 in (1.07 m)", "minimum 1.07 m"),
    ("2 m (6.5 m)", "2 m (6.5 m)"),
    ("300 mm (maximum 400 mm)", "300 mm (maximum 400 mm)"),
])
def test_the_equivalent_in_the_other_system_is_dropped(before, after):
    assert one_unit_system(before) == after


def _label(i, text, x, y, kind="room_label", norm=None, value=None):
    return TextItem(id=i, text=text, bbox=(x, y, x + 4 * len(text) / 3, y + 1.0), height=1.0, kind=kind, norm=norm,
                    value=value, prov=Prov(source="vector", stage="test"))


def test_stacked_name_and_area_lines_are_one_seed_and_tags_are_not_seeds():
    texts = [_label("a", "BEDROOM", 10, 20, norm="bedroom"), _label("b", "SUITE", 10, 18.5, norm=None),
             _label("c", "288 SQ FT", 10, 17, kind="area", value=26.7), _label("d", "K1", 30, 20, norm="kitchen"),
             _label("e", "KITCHEN", 40, 20, norm="kitchen")]
    seeds = seeds_from_texts(texts)
    assert len(seeds) == 2
    first = next(s for s in seeds if s["x"] < 20)
    assert first["label"].startswith("SUITE") or "BEDROOM" in first["label"]
    assert first["area_m2"] == pytest.approx(26.7)


def test_two_named_rooms_in_one_space_are_separated_at_the_narrow_part():
    # two 10 m square halls joined by a 1 m doorway whose wall was never drawn as a closed barrier
    from shapely.ops import unary_union

    g = unary_union([box(0, 0, 10, 10), box(10, 4.5, 11, 5.5), box(11, 0, 21, 10)])
    seeds = [{"x": 5.0, "y": 5.0, "label": "A", "norm": None, "area_m2": None},
             {"x": 16.0, "y": 5.0, "label": "B", "norm": None, "area_m2": None}]
    parts = split_region(g, seeds, 1.0)
    assert len(parts) == 2
    areas = sorted(p.area for p, _ in parts)
    assert areas[0] == pytest.approx(100, rel=0.12) and areas[1] == pytest.approx(100, rel=0.12)
    left = next(p for p, s in parts if s["label"] == "A")
    assert left.bounds[2] <= 12.0


def test_one_seed_leaves_the_space_whole():
    g = box(0, 0, 10, 10)
    parts = split_region(g, [{"x": 5.0, "y": 5.0, "label": "A", "norm": None, "area_m2": None}], 1.0)
    assert len(parts) == 1 and parts[0][0].equals(g)


def test_stacked_lines_of_a_rotated_label_are_one_seed():
    # a plan turned a quarter turn: the name and the area sit side by side on the page, one above the other on the text
    name = _label("n", "CHAMBRE 1", 122.4, 181.9, norm="bedroom")
    name.rotation_deg = 270.0
    name.bbox = (122.4, 181.9, 126.7, 200.1)
    name.height = 3.125
    area = _label("a", "16,98 m2", 119.0, 186.6, kind="area", value=16.98)
    area.rotation_deg = 270.0
    area.bbox = (119.0, 186.6, 122.1, 195.4)
    area.height = 2.25
    seeds = seeds_from_texts([name, area])
    assert len(seeds) == 1 and seeds[0]["area_m2"] == pytest.approx(16.98)


def test_a_stray_text_does_not_cut_a_sliver_room():
    g = box(0, 0, 10, 10)
    seeds = [{"x": 5.0, "y": 5.0, "label": "A", "norm": None, "area_m2": None},
             {"x": 9.7, "y": 9.7, "label": "stray", "norm": None, "area_m2": None}]
    parts = split_region(g, seeds, 1.0)
    assert len(parts) == 1 and parts[0][0].area == pytest.approx(100, rel=0.01)


@pytest.mark.parametrize("texts,denominator", [(["MASSTAB:", "1:100"], 100), (["Maßstab 1:50"], 50), (["Escala 1:75"], 75),
                                               (["M 1:200"], 200), (["1:100", "1:20"], None), (["Schaal 1:100"], 100)])
def test_the_written_scale_in_other_languages_and_on_its_own(texts, denominator):
    items = [TextItem(id=f"t{i}", text=t, bbox=(0, 0, 1, 1), prov=Prov(source="vector", stage="test")) for i, t in enumerate(texts)]
    assert title_block_scale(items) == denominator


def _rooms(*pairs):
    from types import SimpleNamespace

    return [SimpleNamespace(stated_area_m2=s, area_m2=a) for s, a in pairs]


def test_printed_room_areas_that_agree_give_a_scale():
    from reviewpulse.pipeline import area_calibrated_scale

    # every room measures 1.7 times its printed area at the assumed scale: lengths are 1.30 times too long
    found = area_calibrated_scale(_rooms((17.36, 29.5), (15.6, 26.6), (9.57, 16.3), (5.14, 8.7), (6.35, 10.8)), 0.1)
    assert found is not None
    scale, spread = found
    assert scale.method == "stated_areas" and scale.metres_per_unit == pytest.approx(0.1 / 1.30, rel=0.03)
    assert spread < 0.04


def test_scattered_or_too_few_printed_areas_give_no_scale():
    from reviewpulse.pipeline import area_calibrated_scale

    assert area_calibrated_scale(_rooms((17.0, 20.0), (15.0, 60.0), (9.0, 11.0), (5.0, 30.0)), 0.1) is None
    assert area_calibrated_scale(_rooms((17.0, 20.0), (15.0, 17.5)), 0.1) is None
    assert area_calibrated_scale(_rooms((None, 20.0), (None, 17.5), (None, 3.0)), 0.1) is None


def test_what_was_inferred_from_labels_can_never_fail_a_rule():
    """A room cut from a larger space by its name, and the opening that joins the pieces, are guesses: untrusted facts."""
    from reviewpulse.factgraph.from_building import from_building
    from reviewpulse.schema import BuildingModel, Edge, Room, Sheet

    sheet = Sheet(id="s", source_file="x", mode="vector", coord_unit="paper_mm", width=1, height=1)
    sheet.scale.metres_per_unit, sheet.scale.method, sheet.scale.confidence = 0.01, "dimension_consensus", 0.9

    def room(i, inferred):
        ev = {"boundary": "inferred_from_labels"} if inferred else {}
        return Room(id=i, polygon=[(0, 0), (1, 0), (1, 1)], area_m2=12.0, min_width_m=2.5, type="kitchen",
                    prov=Prov(source="derived", stage="t", evidence=ev))

    edge = Edge(a="r1", b="r2", kind="opening", prov=Prov(source="derived", stage="t", evidence={"inferred": "label_seeded_split"}))
    model = BuildingModel(sheet=sheet, rooms=[room("r1", True), room("r2", False)], edges=[edge])
    model.tier = "T1"
    graph = from_building(model, complete=True)
    nodes = {n.id: n for n in graph.nodes}
    assert nodes["r1"].attrs["area_m2"].trusted is False
    assert nodes["r2"].attrs["area_m2"].trusted is True
    assert graph.edges[0].trusted is False
