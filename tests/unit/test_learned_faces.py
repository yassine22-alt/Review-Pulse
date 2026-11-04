"""Single lines the classifier calls walls become wall pieces (learned faces), except the lines of a
small closed outline: an object symbol. Measured case: generated plan 5033 as PDF, where the ArchCAD
model called a bathtub outline walls and a 1 m2 false room cut the bathroom from 10.1 to 8.5 m2."""

from reviewpulse.perception.walls import _learned_faces, _line_pool
from reviewpulse.schema import Primitive, Prov, Scale, Sheet


def _prim(id_, kind, pts, wall=True, **ev):
    return Primitive(id=id_, kind=kind, pts=pts,
                     prov=Prov(source="vector", stage="test", evidence={"learned_wall": wall, **ev}))


def _sheet(prims):
    return Sheet(id="t", source_file="t", mode="vector", coord_unit="drawing_unit", width=20, height=20,
                 scale=Scale(metres_per_unit=1.0, method="user", confidence=1.0), primitives=prims)


def test_closed_object_outline_is_not_a_wall():
    tub = _prim("tub", "polygon", [(1.0, 1.0), (1.7, 1.0), (1.7, 2.6), (1.0, 2.6)])
    segs = _line_pool(_sheet([tub]), 1.0, [])
    assert segs and _learned_faces(segs, [], 1.0) == []


def test_single_line_wall_still_becomes_a_wall():
    wall = _prim("w", "line", [(5.0, 1.0), (9.0, 1.0)])
    tub = _prim("tub", "polygon", [(1.0, 1.0), (1.7, 1.0), (1.7, 2.6), (1.0, 2.6)])
    faces = _learned_faces(_line_pool(_sheet([wall, tub]), 1.0, []), [], 1.0)
    assert [f.members for f in faces] == [{"w"}]


def test_wall_drawn_as_a_closed_thin_outline_still_pairs():
    """A wall body drawn as one closed rectangle (0.2 m thick, 2.5 m long) is not an object: its two
    long faces pair into a wall; a 0.7 m wide bathtub outline does not."""
    from reviewpulse.perception.walls import _object_outlines, _pairs

    body = _prim("wall_body", "polygon", [(0.0, 0.0), (2.5, 0.0), (2.5, 0.2), (0.0, 0.2)], wall=None)
    tub = _prim("tub", "polygon", [(4.0, 0.0), (4.7, 0.0), (4.7, 1.6), (4.0, 1.6)], wall=None)
    segs = _line_pool(_sheet([body, tub]), 1.0, [])
    assert _object_outlines(segs, 1.0) == {next(s.group for s in segs if s.prim.id == "tub")}
    pieces = _pairs(segs, 1.0)
    assert any(p.members == {"wall_body"} for p in pieces)
    assert not any("tub" in p.members for p in pieces)


def test_l_shaped_wall_body_is_not_an_object():
    """Generated plans draw wall runs with their corners as one closed outline: an L of 0.2 m thick
    walls has a wide bounding box but fits only a small circle, so it is a wall, not an object."""
    from reviewpulse.perception.walls import _object_outlines

    ell = _prim("ell", "polygon", [(0.0, 0.0), (2.5, 0.0), (2.5, 0.2), (0.2, 0.2), (0.2, 2.0), (0.0, 2.0)], wall=None)
    assert _object_outlines(_line_pool(_sheet([ell]), 1.0, []), 1.0) == set()


def _piece(y, t, members, source="pairs", x1=5.0):
    import numpy as np

    from reviewpulse.perception.walls import WallPiece

    return WallPiece(np.array([0.0, y]), np.array([x1, y]), t, set(members), 0.0, False, source=source)


def test_a_learned_face_never_makes_a_true_wall_too_thick():
    """Measured on FloorPlanCAD 0460-0018: a learned face (assumed 0.25 m body) beside a 0.35 m wall
    made them "too thick together" and true walls were dropped; a room was lost."""
    from reviewpulse.perception.walls import _drop_glued

    wall, face = _piece(0.0, 0.35, {"f1", "f2"}), _piece(0.30, 0.25, {"f3"}, source="learned_face")
    assert len(_drop_glued([wall, face], 1.0, {"f1": (0.9, 5), "f2": (0.9, 5), "f3": (0.98, 5)})) == 2


def test_glued_bodies_keep_the_one_the_classifier_believes():
    """Two measured bodies too thick together (0.35 + 0.3 m, touching): the one whose lines the
    classifier calls walls stays, even when the other has the more common thickness."""
    from reviewpulse.perception.walls import _drop_glued

    wall, counter = _piece(0.0, 0.35, {"w1", "w2"}), _piece(0.325, 0.3, {"o1", "o2"})
    common = [_piece(10.0 + k, 0.3, {f"c{k}"}) for k in range(3)]               # 0.3 m is common
    p = {"w1": (0.95, 5), "w2": (0.9, 5), "o1": (0.3, 5), "o2": (0.1, 5), **{f"c{k}": (0.9, 5) for k in range(3)}}
    kept = [id(w) for w in _drop_glued([wall, counter] + common, 1.0, p)]
    assert id(wall) in kept and id(counter) not in kept
    kept = [id(w) for w in _drop_glued([wall, counter] + common, 1.0, None)]    # rules only: thickness decides
    assert id(counter) in kept and id(wall) not in kept


def test_fusion_rejects_a_pair_with_one_believed_face():
    """Two equal faces, one called a wall (0.7) and one not (0.13): with yes/no calls the share tied
    at 0.5 and the pair stayed (hatched strips cut a hall in 8); by mean probability it is rejected."""
    from reviewpulse.perception.learned.fuse import fuse_walls
    from reviewpulse.schema import Element

    a = _prim("a", "line", [(0.0, 0.0), (5.0, 0.0)], wall=True, p_wall=0.7)
    b = _prim("b", "line", [(0.0, 0.25), (5.0, 0.25)], wall=False, p_wall=0.13)
    e = Element(id="w", cls="wall", geom=[(0.0, 0.125), (5.0, 0.125)], thickness=0.25, member_ids=["a", "b"],
                prov=Prov(source="vector", stage="walls_pairs_v1"))
    out, stats = fuse_walls(_sheet([a, b]), [e], [], threshold=0.5)
    assert stats["rejected"] == 1 and out[0].cls == "other" and out[0].prov.evidence["learned_wall_prob"] == 0.415
