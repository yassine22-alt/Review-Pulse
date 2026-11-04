"""R9: a window wider than a door-size gap (glazed bay) is still a window and still closes its room."""

import ezdxf
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from reviewpulse.eval.cli import _model_from


def _room_with_wide_window(path, win_w=4.0):
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    t = 0.3
    W, H = 8.0, 5.0
    walls = unary_union([LineString(s).buffer(t / 2, cap_style="square") for s in
                         [((0, 0), (W, 0)), ((W, 0), (W, H)), ((W, H), (0, H)), ((0, H), (0, 0))]])
    x0 = (W - win_w) / 2
    cut_win = box(x0, -t, x0 + win_w, t)
    cut_door = box(-t, 1.0, t, 1.9)
    body = walls.difference(cut_win).difference(cut_door)
    for g in getattr(body, "geoms", [body]):
        for ring in [g.exterior, *g.interiors]:
            cs = list(ring.coords)
            for a, b in zip(cs, cs[1:]):
                msp.add_line(a, b, dxfattribs={"layer": "A-WALL"})
    for off in (-t / 2, 0.0, t / 2):
        msp.add_line((x0, off), (x0 + win_w, off), dxfattribs={"layer": "A-GLAZ"})
    hinge = (t / 2, 1.0)
    msp.add_arc(hinge, 0.9, 0, 90, dxfattribs={"layer": "A-DOOR"})
    msp.add_line(hinge, (t / 2, 1.9), dxfattribs={"layer": "A-DOOR"})
    t_ = msp.add_text("SEJOUR", height=0.25)
    t_.set_placement((4, 2.5), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    doc.saveas(path)


def test_four_metre_window_is_detected_and_room_closes(tmp_path):
    p = tmp_path / "wide.dxf"
    _room_with_wide_window(p)
    m = _model_from(str(p))
    wins = [e for e in m.elements if e.cls == "window"]
    assert len(wins) == 1 and abs(wins[0].attrs["width_m"] - 4.0) < 0.05
    assert len(m.rooms) == 1 and m.rooms[0].type == "living"
    assert m.rooms[0].has_window
