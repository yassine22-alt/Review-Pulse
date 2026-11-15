"""A kept rule wall that pairs a believed wall face with a line the classifier rejects (a lift car
inside a shaft) reaches into the room; walls rebuilt from believed lines replace it. Measured on 40
FloorPlanCAD drawings: matched rooms within 5% of the reference area 43% -> 57% (model v6)."""

from reviewpulse.perception.learned.fuse import fuse_walls
from reviewpulse.schema import Element, Primitive, Prov, Scale, Sheet


def _line(id_, y, wall, p):
    return Primitive(id=id_, kind="line", pts=[(0.0, y), (5.0, y)],
                     prov=Prov(source="vector", stage="test", evidence={"learned_wall": wall, "p_wall": p}))


def _wall(id_, y, t, members):
    return Element(id=id_, cls="wall", geom=[(0.0, y), (5.0, y)], thickness=t, member_ids=members,
                   prov=Prov(source="vector", stage="walls_pairs_v1"))


def _sheet(prims):
    return Sheet(id="t", source_file="t", mode="vector", coord_unit="drawing_unit", width=20, height=20,
                 scale=Scale(metres_per_unit=1.0, method="user", confidence=1.0), primitives=prims)


def _case():
    # true wall: faces at y=0 and y=0.2; a lift car line at y=0.45 inside the shaft
    face_out, face_in, car = _line("out", 0.0, True, 0.95), _line("in", 0.2, True, 0.9), _line("car", 0.45, False, 0.3)
    rule = _wall("rule", 0.325, 0.25, ["car", "in"])          # face paired with the car: 0.25 m into the shaft
    rebuilt = _wall("rebuilt", 0.1, 0.2, ["in", "out"])        # the true wall, believed lines only
    return _sheet([face_out, face_in, car]), rule, rebuilt


def test_mixed_rule_wall_is_replaced_by_the_believed_rebuild():
    sheet, rule, rebuilt = _case()
    out, stats = fuse_walls(sheet, [rule], [rebuilt], threshold=0.5)
    walls = [e for e in out if e.cls == "wall"]
    assert stats["replaced"] == 1 and [e.id for e in walls] == ["rebuilt"]
    assert any(e.id == "rule" and e.attrs.get("replaced") for e in out)


def test_a_rule_wall_stays_without_a_rebuilt_alternative():
    sheet, rule, _ = _case()
    out, stats = fuse_walls(sheet, [rule], [], threshold=0.5)
    assert stats["replaced"] == 0 and [e.id for e in out if e.cls == "wall"] == ["rule"]


def test_a_partial_rebuild_does_not_replace():
    """The rebuilt walls must carry the believed face along (nearly) its whole length."""
    sheet, rule, rebuilt = _case()
    short = rebuilt.model_copy(update={"geom": [(0.0, 0.1), (2.0, 0.1)]})
    out, stats = fuse_walls(sheet, [rule], [short], threshold=0.5)
    assert stats["replaced"] == 0 and "rule" in [e.id for e in out if e.cls == "wall"]
