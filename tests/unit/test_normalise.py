import math

from reviewpulse.core.normalise import fit_arcs, tag_door_leaves, tag_glazing
from reviewpulse.schema import Primitive, Prov, Sheet

P = Prov(source="vector", stage="t")


def _line(i, a, b, layer="0"):
    return Primitive(id=f"l{i}", kind="line", pts=[a, b], layer=layer, prov=P.model_copy(deep=True))


def _sheet(prims):
    return Sheet(id="s", source_file="x", mode="vector", coord_unit="drawing_unit", width=20, height=20,
                 primitives=prims)


def test_arc_recovered_from_segments_and_leaf_kept():
    c, r = (5.0, 5.0), 0.9
    pts = [(c[0] + r * math.cos(math.radians(90 * i / 12)), c[1] + r * math.sin(math.radians(90 * i / 12)))
           for i in range(13)]
    prims = [_line(i, a, b) for i, (a, b) in enumerate(zip(pts, pts[1:]))]
    prims.append(_line(99, c, pts[-1]))                       # leaf continues the chain
    s = _sheet(prims)
    assert fit_arcs(s) == 1
    arc = next(p for p in s.primitives if p.kind == "arc")
    assert abs(arc.radius - r) < 1e-3 and abs(arc.center[0] - c[0]) < 1e-3
    assert not next(p for p in s.primitives if p.id == "l99").hidden
    assert tag_door_leaves(s) == 1


def test_square_polygon_is_not_an_arc():
    sq = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    s = _sheet([_line(i, a, b) for i, (a, b) in enumerate(zip(sq, sq[1:]))])
    assert fit_arcs(s) == 0


def test_window_symbol_tagged_but_not_stairs():
    win = [_line(i, (0, y), (1.2, y)) for i, y in enumerate((0.0, 0.1, 0.2))]
    stairs = [_line(10 + i, (5, 0.28 * i), (6.0, 0.28 * i)) for i in range(10)]
    s = _sheet(win + stairs)
    tag_glazing(s, 1.0)
    assert all(p.prov.evidence.get("glazing") for p in win)
    assert not any(p.prov.evidence.get("glazing") for p in stairs)
