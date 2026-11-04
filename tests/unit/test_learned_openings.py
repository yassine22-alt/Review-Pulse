"""Windows from the classifier's window lines: the panes of one window symbol are one window even
when they do not touch. Measured on ArchCAD: panes 6 cm apart, joined only by jamb lines the
classifier calls wall, each became a single-line group and was dropped (slice 1a30af18: 1 of 5
windows found; after the fix 5 of 5)."""

from reviewpulse.core.geometry import side_by_side
from reviewpulse.perception.learned.openings import learned_openings
from reviewpulse.schema import Primitive, Prov, Scale, Sheet


def _pane(id_, x0, x1, y):
    return Primitive(id=id_, kind="line", pts=[(x0, y), (x1, y)],
                     prov=Prov(source="vector", stage="test", evidence={"learned_class": "window", "p_window": 0.99}))


def _sheet(prims):
    return Sheet(id="t", source_file="t", mode="vector", coord_unit="drawing_unit", width=20, height=20,
                 scale=Scale(metres_per_unit=1.0, method="user", confidence=1.0), primitives=prims)


def test_parallel_panes_make_one_window_and_a_row_stays_apart():
    panes = [_pane(f"a{k}", 0.0, 0.9, 0.06 * k) for k in range(4)]          # one 0.9 m window, 4 panes
    panes += [_pane(f"b{k}", 1.1, 2.0, 0.06 * k) for k in range(4)]         # the next window, 0.2 m pier
    wins = [e for e in learned_openings(_sheet(panes), [], [], 1.0) if e.cls == "window"]
    assert sorted(len(e.member_ids) for e in wins) == [4, 4]
    assert {frozenset(e.member_ids) for e in wins} == {frozenset(f"a{k}" for k in range(4)),
                                                       frozenset(f"b{k}" for k in range(4))}


def test_side_by_side():
    assert side_by_side(((0, 0), (1, 0)), ((0.2, 0.05), (1.1, 0.05)))     # parallel, overlapping
    assert not side_by_side(((0, 0), (1, 0)), ((1.2, 0), (2, 0)))          # collinear neighbour
    assert not side_by_side(((0, 0), (1, 0)), ((0, 0), (0, 1)))            # perpendicular
