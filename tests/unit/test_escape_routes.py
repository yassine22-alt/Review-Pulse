"""Escape routes on the hand-made flat (metres): travel distance from the farthest point of a room,
walked around corners and door to door (C-T5), and door swing in the direction of escape (C-T6).
Expected values are worked out by hand from the fixture's geometry."""

import math

import pytest
from shapely.geometry import Polygon

from reviewpulse.core.geometry import Walkable
from reviewpulse.engine.run import run


def _rule(pack, rid, **check):
    r = next(x for x in pack if x.id == rid)
    if check:
        r = r.model_copy(update={"check": r.check.model_copy(update=check)})
    return r


def _detected(findings, room):
    return float(next(f for f in findings if f.subject_ids == [room]).detected.split()[0])


def test_travel_distance_from_the_farthest_corner(pack):
    import handmade

    f = run(handmade.build(bed_b_via_bath=False), [_rule(pack, "C-T5")])
    # living: exit d0 at (1.5, 0); farthest corner (9, 3.8)
    assert _detected(f, "living") == pytest.approx(math.hypot(7.5, 3.8), abs=0.01)
    # bedroom A: farthest corner (0, 8) or (3, 8) to d1 (1.5, 5), then hall 1.2 m, then living 3.8 m
    assert _detected(f, "bedA") == pytest.approx(math.hypot(1.5, 3.0) + 1.2 + 3.8, abs=0.01)


def test_travel_distance_fails_beyond_the_limit_with_its_route(pack):
    import handmade

    f = run(handmade.build(bed_b_via_bath=False), [_rule(pack, "C-T5", value=8.0)])
    bad = {x.subject_ids[0]: x for x in f if x.verdict == "FAIL"}
    assert {"living", "bedA"} <= set(bad)               # 8.41 m and 8.35 m against 8 m
    route = bad["bedA"].evidence["polylines"][0]
    assert len(route) == 4                                # corner, d1, d4, d0
    assert bad["bedA"].evidence["deciding_ids"] == ["d1", "d4", "d0"]


def test_walk_goes_around_corners():
    room = Walkable(Polygon([(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]))
    d = room.distance((3.5, 0.5), (0.5, 3.5))
    assert d == pytest.approx(2 * math.hypot(2.5, 0.5), abs=1e-6)     # via the inner corner (1, 1)
    assert d > math.hypot(3, 3)                                         # never straight through the wall


def _with_exit_swing(handmade, outward: bool):
    m = handmade.build(bed_b_via_bath=False)
    d0 = next(e for e in m.elements if e.id == "d0")
    y = -0.9 if outward else 0.9                         # quarter disc outside (y < 0) or into the living room
    d0.attrs["swing_polygon"] = [(1.0, 0.0), (1.9, 0.0), (1.0, y)]
    return m


def test_exit_door_opening_inward_fails_and_outward_passes(pack):
    import handmade

    rule = [_rule(pack, "C-T6")]
    f_in = run(_with_exit_swing(handmade, outward=False), rule, include_drafts=True)
    f_out = run(_with_exit_swing(handmade, outward=True), rule, include_drafts=True)
    assert [(x.subject_ids, x.verdict) for x in f_in] == [(["d0"], "FAIL")]
    assert "opens into SEJOUR" in f_in[0].message and "outside" in f_in[0].message
    assert [x.verdict for x in f_out] == ["PASS"]


def test_door_without_a_drawn_swing_is_not_evaluated(pack):
    import handmade

    f = run(handmade.build(bed_b_via_bath=False), [_rule(pack, "C-T6")], include_drafts=True)
    assert [(x.subject_ids, x.verdict) for x in f] == [(["d0"], "NOT_EVALUATED")]
    assert "swing" in f[0].message


def test_route_scope_checks_every_door_on_the_way_out(pack):
    import handmade

    m = handmade.build(bed_b_via_bath=False)
    swings = {"d1": [(1.0, 5.0), (1.9, 5.0), (1.0, 5.9)],     # into bedroom A: against the escape
              "d4": [(1.0, 3.8), (1.9, 3.8), (1.0, 2.9)],     # into the living room: with the escape
              "d0": [(1.0, 0.0), (1.9, 0.0), (1.0, -0.9)]}    # outward: with the escape
    for e in m.elements:
        if e.id in swings:
            e.attrs["swing_polygon"] = swings[e.id]
    rule = _rule(pack, "C-T6").model_copy(update={"applies_to": {"room_type": ["bedroom"]}})
    rule = rule.model_copy(update={"check": rule.check.model_copy(update={"doors": "route"})})
    verdicts = {x.subject_ids[0]: x.verdict for x in run(m, [rule], include_drafts=True)}
    assert verdicts["d1"] == "FAIL" and verdicts["d4"] == "PASS" and verdicts["d0"] == "PASS"
