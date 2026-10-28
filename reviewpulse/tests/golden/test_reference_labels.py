"""The rule fallback of the learned pass ("the classifier rejected every wall the rules found: keep the
rule result") guards against the classifier, never against true labels. Measured case: FloorPlanCAD
0029-0526, a car park whose labels mark no walls; the reference fell back to the rule walls (bay lines,
car outlines) and scored three false rooms as truth."""

from pathlib import Path

from reviewpulse.annotate.text_classify import classify_items
from reviewpulse.ingest.dxf_reader import extract_dxf
from reviewpulse.pipeline import build_model
from reviewpulse.synth.make_plan import make_plan


def _no_walls(model):
    for p in model.sheet.primitives:
        p.prov.evidence.update(learned_wall=False, learned_class="other", p_wall=0.0, p_door=0.0, p_window=0.0)
    return len(model.sheet.primitives)


def _sheet(synth_dir):
    p = make_plan(synth_dir, seed=32, png=False, name="ref32")
    s = extract_dxf(Path(p["dxf"]), "ref32")
    classify_items(s.texts)
    return s


def test_true_labels_without_walls_give_no_rooms(synth_dir):
    m = build_model(_sheet(synth_dir), learned=True, annotator=_no_walls, learned_mode="rebuild")
    assert not any(e.cls == "wall" for e in m.elements) and m.rooms == []


def test_a_classifier_rejecting_every_wall_still_falls_back_to_the_rules(synth_dir, monkeypatch):
    from reviewpulse.perception.learned import classifier

    monkeypatch.setattr(classifier, "annotate_primitives", _no_walls)
    m = build_model(_sheet(synth_dir), learned=True, learned_mode="rebuild")
    assert m.rooms and any("rule result kept" in w for w in m.sheet.warnings)
