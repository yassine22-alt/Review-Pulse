"""ArchCAD JSON -> Sheet: entity kinds, arc direction, labels kept for evaluation only, stable split.
Built from hand-written entities (the dataset is gated and not needed here)."""

import math

from reviewpulse.eval.adapters import archcad as A


def door(direction):
    # hinge at the origin, leaf to 330 deg, arc back to the jamb at 270 deg (a 60 deg swing),
    # written the way ArchCAD writes it for each direction
    a0, a1 = (330.0, 270.0) if direction == 1 else (270.0, 330.0)
    return {"type": "ARC", "linetype": "Continuous", "center": [0.0, 0.0], "radius": 56.0, "start_angle": a0,
            "end_angle": a1, "direction": direction, "rgb": [0, 0, 0], "semantic": 1, "instance": "d1"}


def test_arc_direction_gives_the_short_swing_either_way():
    for direction in (0, 1):
        p = A.to_sheet([door(direction)], "x").primitives[0]
        assert (p.a0, p.a1) == (270.0, 330.0)            # 60 deg counter-clockwise, never the 300 deg complement


def test_entities_and_labels():
    ents = [
        {"type": "LINE", "linetype": "DASHED", "start": [0, 0], "end": [10, 0], "rgb": [255, 0, 0], "semantic": 20},
        {"type": "LINE", "linetype": "Continuous", "start": [5, 5], "end": [5, 5], "rgb": [0, 0, 0], "semantic": 100},
        {"type": "CIRCLE", "linetype": "Continuous", "center": [1, 2], "radius": 3, "rgb": [0, 0, 0], "semantic": 21,
         "instance": "c1"},
        {"type": "ELLIPSE", "linetype": "Continuous", "center": [0, 0], "major_axis": [10, 0], "ratio": 0.5,
         "start_param": 0.0, "end_param": 2 * math.pi, "is_ccw": True, "rgb": [0, 0, 0], "semantic": 9},
    ]
    s = A.to_sheet(ents, "x")
    kinds = [p.kind for p in s.primitives]
    assert kinds == ["line", "circle", "polyline"]       # zero-length line dropped
    line = s.primitives[0]
    assert line.dashed and line.color == "#ff0000"
    assert line.prov.evidence["gt"] == {"semantic": 20, "instance": -1}
    assert s.primitives[1].prov.evidence["gt"]["instance"] == "c1"
    xs = [x for x, _ in s.primitives[2].pts]
    ys = [y for _, y in s.primitives[2].pts]
    assert max(xs) == 10 and min(xs) == -10 and math.isclose(max(ys), 5, abs_tol=0.05)
    assert s.width == s.height == A.SIZE and not s.texts


def test_split_is_stable_and_proportioned():
    names = [f"n{i}" for i in range(20000)]
    counts = {s: sum(A.split_of(n) == s for n in names) for s in ("test", "val", "train")}
    assert A.split_of("n123") == A.split_of("n123")
    assert 0.04 < counts["test"] / len(names) < 0.06 and 0.04 < counts["val"] / len(names) < 0.06


def test_glass_groups_become_window_instances():
    g = {"type": "LINE", "linetype": "Continuous", "rgb": [0, 0, 0], "semantic": 19}
    ents = [dict(g, start=[0, 0], end=[50, 0]), dict(g, start=[0, 3], end=[50, 3]),     # one window:
            dict(g, start=[0, 0], end=[0, 3]),                                          # joined by an end cap
            dict(g, start=[200, 0], end=[250, 0])]                                      # another window
    inst = [p.prov.evidence["gt"]["instance"] for p in A.to_sheet(ents, "x").primitives]
    assert inst[0] == inst[1] == inst[2] != inst[3] and -1 not in inst


def test_parallel_panes_without_end_caps_are_one_window():
    """Measured on ArchCAD: a window drawn as 4 parallel panes, joined only by wall-labelled jambs,
    was scored as 4 windows. Panes side by side are one window; windows in a row stay apart."""
    g = {"type": "LINE", "linetype": "Continuous", "rgb": [0, 0, 0], "semantic": 19}
    ents = [dict(g, start=[0, y], end=[60, y]) for y in (0, 4, 8, 12)]                  # 0.86 m, 4 panes
    ents += [dict(g, start=[75, y], end=[135, y]) for y in (0, 4, 8, 12)]               # next window, 0.2 m pier
    ents += [dict(g, start=[0, 50], end=[60, 50])]                                      # 0.54 m away: other wall
    inst = [p.prov.evidence["gt"]["instance"] for p in A.to_sheet(ents, "x").primitives]
    assert len(set(inst[:4])) == 1 and len(set(inst[4:8])) == 1 and inst[0] != inst[4]
    assert inst[8] not in (inst[0], inst[4])
