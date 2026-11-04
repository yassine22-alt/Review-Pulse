"""R10 exits: a door onto a labelled balcony / terrace is not an exit."""

import json
from pathlib import Path

import ezdxf

from reviewpulse.eval.cli import _model_from
from reviewpulse.synth.make_plan import make_plan


def _exit_doors(model):
    return [e for e in model.edges if e.kind == "door" and "EXIT" in (e.a, e.b)]


def test_balcony_label_outside_a_door_makes_it_an_outdoor_annex(tmp_path):
    p = make_plan(tmp_path, seed=8, png=False, name="annex")
    assert len(_exit_doors(_model_from(p["dxf"]))) == 1
    truth = json.loads(Path(p["truth"]).read_text())
    front = next(o for o in truth["openings"] if o["rooms"][1] == "EXIT")
    x, y = front["midpoint"]
    doc = ezdxf.readfile(p["dxf"])
    t = doc.modelspace().add_text("BALCON", height=0.25, dxfattribs={"layer": "A-ANNO-TEXT"})
    t.set_placement((x, y - 1.2), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    out = tmp_path / "annex_balcony.dxf"
    doc.saveas(out)
    m = _model_from(str(out))
    assert _exit_doors(m) == []
    assert any(e.kind == "door" and "EXTERIOR" in (e.a, e.b) for e in m.edges)
