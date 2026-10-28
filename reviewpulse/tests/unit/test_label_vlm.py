"""Second reader for scanned labels (the vision model is replaced by a stub: no Ollama needed)."""

import numpy as np

from reviewpulse.annotate import label_vlm
from reviewpulse.annotate.text_classify import classify_items
from reviewpulse.engine.run import run
from reviewpulse.schema import Prov, TextItem


def _item(id_, text, box):
    return TextItem(id=id_, text=text, bbox=box, prov=Prov(source="ocr", stage="ocr", confidence=0.5))


def test_misread_label_is_reread_and_marked(monkeypatch):
    items = [_item("a", "CHANBRF", (10, 10, 60, 20)),       # OCR misread of CHAMBRE
             _item("b", "SEJOUR", (100, 10, 150, 20)),       # already readable: never re-read
             _item("c", "12", (200, 10, 210, 20))]           # a number: not a candidate
    classify_items(items)
    seen = []

    def stub(crop):
        seen.append(crop.shape)
        return "CHAMBRE"

    monkeypatch.setattr(label_vlm, "transcribe", stub)
    gained = label_vlm.reread_labels(items, np.zeros((100, 300), np.uint8), lambda b: b)
    assert gained == 1 and len(seen) == 1
    a = items[0]
    assert a.kind == "room_label" and a.norm == "bedroom"
    assert a.prov.evidence["label_source"] == "vlm" and a.prov.evidence["vlm_text"] == "CHAMBRE"


def test_a_fail_never_rests_on_a_vision_read_room_type(pack):
    import handmade

    m = handmade.build(narrow_door=False)
    bed = next(r for r in m.rooms if r.id == "bedA")
    bed.area_m2 = 6.0                                     # below the 9 m2 of C-D3
    rule = [r for r in pack if r.id == "C-D3"]
    assert any(f.verdict == "FAIL" for f in run(m, rule))
    bed.prov.evidence["label_source"] = "vlm"
    res = [f for f in run(m, rule) if bed.id in f.subject_ids]
    assert res and all(f.verdict == "WARNING" for f in res) and "verify room type" in res[0].message


def test_an_invented_reading_is_rejected(monkeypatch):
    """Measured: for a blank crop the model answered "10'x20' Living Room"."""
    items = [_item("a", "CHANBRF", (10, 10, 60, 20)), _item("b", "xx", (100, 10, 150, 20))]
    classify_items(items)
    monkeypatch.setattr(label_vlm, "transcribe", lambda crop: "10'x20' Living Room")
    assert label_vlm.reread_labels(items, np.zeros((100, 300), np.uint8), lambda b: b) == 0
    assert all(t.kind != "room_label" for t in items)
    assert items[0].prov.evidence["vlm_rejected"].startswith("10'x20'")


def test_agreement_gate():
    from reviewpulse.annotate.label_vlm import agrees

    assert agrees("CHANBRF", "CHAMBRE") and agrees("OLOHUOME", "OLOHUONE") and agrees("KEITTI0", "KEITTIÖ")
    assert not agrees("CHANBRF", "Living Room") and not agrees("WC", "BEDROOM") and not agrees("", "SDB")
