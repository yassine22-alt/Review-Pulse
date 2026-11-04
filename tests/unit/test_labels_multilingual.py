"""Room labels in any language (lexicon + mined + fuzzy OCR + LLM fallback), label/area stacking,
SVG text runs, and the engine's guards for labels and absences read from estimated input."""

import pytest

from reviewpulse.annotate.label_llm import apply_llm_labels
from reviewpulse.annotate.text_classify import classify_items, match_room, match_room_fuzzy, room_lexicon
from reviewpulse.schema import Prov, TextItem


@pytest.mark.parametrize("text,rtype", [
    ("MH 2", "bedroom"), ("Schlafzimmer", "bedroom"), ("dormitorio 3", "bedroom"), ("غرفة نوم", "bedroom"),
    ("KH", "bathroom"), ("Badezimmer", "bathroom"), ("bagno", "bathroom"), ("OLESKELU+RUOK", "living"),
    ("Soggiorno", "living"), ("Küche", "kitchen"), ("keittiö", "kitchen"), ("مطبخ", "kitchen"),
    ("Sovrum 2", "bedroom"), ("ULKOTILA", "terrace"), ("varanda", "terrace"), ("TK", "entry"),
    ("Abstellraum", "storage"), ("escritório", "office"), ("SÉJOUR / SALON", "living")])
def test_multilingual_lexicon(text, rtype):
    assert match_room(text) == rtype


def test_lexicon_has_no_conflicts_and_covers_languages():
    lex = room_lexicon()
    assert len(lex) > 400
    assert match_room("nothing here") is None


@pytest.mark.parametrize("text,rtype", [("OLOHUOME", "living"), ("keiltio", "kitchen"), ("TEKNTILA", "storage"),
                                        ("UH", None), ("HO", None)])
def test_fuzzy_only_for_long_unambiguous_words(text, rtype):
    assert match_room_fuzzy(text) == rtype


def _t(i, text, bbox, rot=0.0, h=2.0, src="ocr"):
    return TextItem(id=i, text=text, bbox=bbox, rotation_deg=rot, height=h, prov=Prov(source=src, stage="t"))


def test_number_stacked_under_label_is_its_area():
    items = [_t("a", "MH", (78, 86, 80, 89), 90), _t("b", "14.1", (80.2, 86, 82.2, 89), 90),
             _t("c", "OLOHUONE", (10, 50, 26, 52)), _t("d", "575", (14, 47.5, 20, 49.5)),
             _t("e", "3.40", (60, 10, 66, 12))]
    classify_items(items)
    k = {t.id: t for t in items}
    assert (k["a"].kind, k["a"].norm, k["a"].value) == ("room_label", "bedroom", 14.1)
    assert k["b"].kind == "area"
    assert k["d"].kind == "note"                 # 575 m2 is no room: a lost decimal point
    assert (k["e"].kind, k["e"].value) == ("dimension", 3.4)


def test_fuzzy_applies_to_ocr_text_only():
    items = [_t("a", "OLOHUOME", (0, 0, 10, 2)), _t("b", "OLOHUOME", (0, 10, 10, 12), src="vector")]
    classify_items(items)
    assert items[0].kind == "room_label" and items[0].prov.evidence["label_match"] == "fuzzy"
    assert items[1].kind == "note"


class _StubLLM:
    model = "stub"

    def __init__(self, answers):
        self.answers, self.calls = answers, 0

    def complete(self, system, user, schema):
        self.calls += 1
        lines = [ln.split(". ", 1)[1] for ln in user.splitlines()[1:]]
        return {"labels": [{"text": s, "room_type": self.answers.get(s, "not_a_room")} for s in lines]}


def test_llm_fallback_marks_and_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEWPULSE_LABEL_LLM", "1")
    stub = _StubLLM({"zzroom": "bedroom"})
    items = [_t("a", "ZZROOM", (0, 0, 10, 2)), _t("b", "NORTH", (0, 10, 10, 12))]
    classify_items(items)
    assert apply_llm_labels(items, stub, tmp_path / "c.json") == 1
    assert (items[0].kind, items[0].norm, items[0].prov.evidence["label_source"]) == ("room_label", "bedroom", "llm")
    assert items[1].kind == "note" and items[0].prov.confidence <= 0.6
    again = [_t("a", "ZZROOM", (0, 0, 10, 2))]
    classify_items(again)
    apply_llm_labels(again, stub, tmp_path / "c.json")
    assert stub.calls == 1                       # second plan answered from the cache


def test_svg_text_runs_positions_and_rotation(tmp_path):
    from reviewpulse.ingest.svg_reader import extract_svg

    svg = tmp_path / "t.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
                   '<text transform="matrix(1 0 0 1 0 100)" font-size="5"><tspan y="-20" x="10 13 16">3,40</tspan></text>'
                   '<text transform="matrix(0 -1 1 0 0 100)" font-size="5"><tspan y="50" x="30 33">12</tspan></text>'
                   '<line x1="0" y1="0" x2="10" y2="0" stroke="black"/></svg>', encoding="utf-8")
    s = extract_svg(svg, "s")
    a, b = s.texts
    assert a.text == "3,40" and abs(a.bbox[0] - 10) < 1e-6 and a.rotation_deg % 360 == pytest.approx(0)
    assert b.rotation_deg % 360 == pytest.approx(90)
    assert a.bbox != b.bbox


def _model(texts, room_ev=None, label=None, rtype=None, area=12.0):
    from reviewpulse.schema import BuildingModel, Room, Scale, Sheet

    sheet = Sheet(id="s", source_file="x", mode="vector", coord_unit="drawing_unit", width=10, height=10,
                  scale=Scale(metres_per_unit=1.0, method="dxf_units", confidence=1.0), texts=texts)
    room = Room(id="r1", polygon=[(0, 0), (3, 0), (3, 2), (0, 2)], label=label, type=rtype, area_m2=area,
                min_width_m=2.0, prov=Prov(source="derived", stage="t", evidence=room_ev or {}))
    return BuildingModel(sheet=sheet, rooms=[room], tier="T1")


def _verdict(model, rule_id, pack):
    from reviewpulse.engine.run import run

    fs = [f for f in run(model, [r for r in pack if r.id == rule_id]) if "r1" in f.subject_ids]
    return fs[0].verdict if fs else None


def test_absence_on_ocr_text_never_fails(pack):
    assert _verdict(_model([_t("n", "note", (5, 5, 6, 6), src="vector")]), "P-1", pack) == "FAIL"
    assert _verdict(_model([_t("n", "note", (5, 5, 6, 6), src="ocr")]), "P-1", pack) == "WARNING"


def test_llm_typed_room_never_decides_a_fail(pack):
    small = dict(label="ZZROOM", rtype="bedroom", area=4.0)
    assert _verdict(_model([], **small), "C-D3", pack) == "FAIL"
    assert _verdict(_model([], room_ev={"label_source": "llm"}, **small), "C-D3", pack) == "WARNING"


@pytest.mark.parametrize("method,capped", [("dimension_consensus", True), ("dxf_units", False), ("user", False)])
def test_not_to_scale_note_caps_estimated_scale(monkeypatch, method, capped):
    from reviewpulse.annotate import scale as sc
    from reviewpulse.schema import Scale, Sheet

    sheet = Sheet(id="s", source_file="x", mode="raster", coord_unit="paper_mm", width=10, height=10,
                  texts=[_t("n", "SUUNTAA-ANTAVA, EI MITTAKAAVASSA", (0, 0, 9, 1))])
    monkeypatch.setattr(sc, "_recover_scale", lambda s, c=None: (
        Scale(metres_per_unit=0.05, method=method, confidence=1.0), sc.ScaleReport(method=method)))
    got, _rep = sc.recover_scale(sheet)
    assert (got.confidence == sc.NTS_MAX_CONFIDENCE) == capped
    assert any("not to scale" in w for w in sheet.warnings)


def _doors(widths_m, mpu):
    from reviewpulse.schema import Element

    return [Element(id=f"d{i}", cls="door", geom=[(0, 0)], attrs={"width_m": w},
                    prov=Prov(source="raster", stage="t")) for i, w in enumerate(widths_m)]


def test_scale_rejected_when_doors_are_implausible():
    from reviewpulse.perception.raster.build import check_scale_with_doors
    from reviewpulse.schema import Scale, Sheet

    def sheet(texts=()):
        return Sheet(id="s", source_file="x", mode="raster", coord_unit="paper_mm", width=10, height=10,
                     texts=list(texts))

    bad = Scale(metres_per_unit=0.186, method="dimension_consensus", confidence=1.0)
    doors = _doors([1.49, 1.6, 1.63, 1.7], 0.186)               # 8-9 mm on paper at 1:186
    ok = Scale(metres_per_unit=0.1, method="dimension_consensus", confidence=1.0)
    assert check_scale_with_doors(sheet(), ok, _doors([0.86, 0.9, 0.8], 0.1), 0.1) is ok
    capped = check_scale_with_doors(s := sheet(), bad, doors, 0.186)
    assert capped.confidence == 0.5 and capped.metres_per_unit == 0.186 and s.warnings
    tb = check_scale_with_doors(sheet([_t("e", "ECHELLE 1:100", (0, 0, 9, 1))]), bad, doors, 0.186)
    assert (tb.method, tb.metres_per_unit) == ("title_block", 0.1)
    user = Scale(metres_per_unit=0.186, method="user", confidence=1.0)
    assert check_scale_with_doors(sheet(), user, doors, 0.186) is user
