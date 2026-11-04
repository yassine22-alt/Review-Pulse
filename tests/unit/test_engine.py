"""J1-J5 on the hand-made model (no perception involved)."""

import random

import networkx as nx
import pytest

from reviewpulse.engine.run import run


def _by_rule(findings, rule):
    return [f for f in findings if f.rule_id == rule]


def test_exit_via_bathroom_fails_with_witness(pack):
    import handmade

    f = _by_rule(run(handmade.build(), pack), "C-T1")
    bad = [x for x in f if x.verdict == "FAIL"]
    assert [x.subject_ids[0] for x in bad] == ["bedB"]
    assert "bath" in bad[0].evidence["blocking"]
    assert bad[0].evidence["polylines"] and len(bad[0].evidence["polylines"][0]) >= 3
    assert all(x.verdict == "PASS" for x in f if x.subject_ids[0] != "bedB")


def test_clean_variant_passes(pack):
    import handmade

    f = run(handmade.build(bed_b_via_bath=False), pack)
    assert not [x for x in f if x.rule_id in ("C-T1", "C-T2", "C-C1") and x.verdict != "PASS"]


def test_narrow_door_fails_t1_and_warns_without_scale(pack):
    import handmade

    m = handmade.build(narrow_door=True)
    assert any(x.verdict == "FAIL" and x.subject_ids == ["d1"] for x in _by_rule(run(m, pack), "C-D1"))
    m.tier = "T3"
    m.sheet.scale.method = "title_block"
    res = _by_rule(run(m, pack), "C-D1")
    assert not any(x.verdict == "FAIL" for x in res)
    assert any(x.verdict == "WARNING" and x.subject_ids == ["d1"] for x in res)


def test_missing_input_is_not_evaluated(pack):
    import handmade

    m = handmade.build()
    m.sheet.scale.metres_per_unit = None
    res = _by_rule(run(m, pack), "C-D1")
    assert res and res[0].verdict == "NOT_EVALUATED" and "scale" in res[0].message


def test_topological_fail_needs_confirmation_on_t2(pack):
    import handmade

    m = handmade.build(tier="T2")
    for e in m.elements:
        e.confirmed = False
    assert not [x for x in _by_rule(run(m, pack), "C-T1") if x.verdict == "FAIL"]
    assert [x for x in _by_rule(run(m, pack, confirmed={"d2", "d3", "d4", "d0"}), "C-T1") if x.verdict == "FAIL"]


def test_draft_rules_do_not_run(pack):
    import handmade

    drafts = [r.model_copy(update={"status": "draft"}) for r in pack]
    assert run(handmade.build(), drafts) == []


@pytest.mark.parametrize("seed", range(25))
def test_exists_path_agrees_with_brute_force(seed, pack):
    """J3: on random graphs the engine agrees with an independent search."""
    import handmade

    rnd = random.Random(seed)
    m = handmade.build()
    types = ["bedroom", "bathroom", "living", "kitchen", "corridor", "wc"]
    for r in m.rooms:
        r.type = rnd.choice(types)
    from reviewpulse.schema import Edge, Prov

    ids = [r.id for r in m.rooms] + ["EXIT"]
    m.edges = [Edge(a=a, b=b, kind="door", prov=Prov(source="user", stage="t"))
               for a in ids for b in ids if a < b and rnd.random() < 0.35]
    rule = next(r for r in pack if r.id == "C-T1")
    got = {f.subject_ids[0]: f.verdict for f in run(m, [rule])}
    g = nx.Graph()
    g.add_nodes_from(ids)
    g.add_edges_from((e.a, e.b) for e in m.edges)
    avoid = {"bathroom", "wc", "bedroom"}
    for r in m.rooms:
        if r.type not in rule.applies_to["room_type"]:
            continue
        keep = [n for n in ids if n == r.id or n == "EXIT" or next(x for x in m.rooms if x.id == n).type not in avoid]
        ok = nx.has_path(g.subgraph(keep), r.id, "EXIT")
        assert got[r.id] == ("PASS" if ok else "FAIL")


def test_untyped_room_is_not_evaluated_not_silently_passed(pack):
    """A room with no type may be a bedroom: room-type rules report it as NOT_EVALUATED."""
    from reviewpulse.engine.run import run
    from reviewpulse.schema import BuildingModel, Prov, Room, Scale, Sheet

    sheet = Sheet(id="s", source_file="x", mode="vector", coord_unit="drawing_unit", width=10, height=10,
                  scale=Scale(metres_per_unit=1.0, method="dxf_units", confidence=1.0))
    rooms = [Room(id="r1", polygon=[(0, 0), (3, 0), (3, 3), (0, 3)], type="bedroom", area_m2=9.0,
                  min_width_m=3.0, prov=Prov(source="derived", stage="t")),
             Room(id="r2", polygon=[(3, 0), (6, 0), (6, 3), (3, 3)], type=None, area_m2=9.0,
                  min_width_m=3.0, prov=Prov(source="derived", stage="t"))]
    fs = run(BuildingModel(sheet=sheet, rooms=rooms, tier="T1"), pack)
    typed_rules = {r.id for r in pack if r.applies_to.get("room_type") and r.status == "approved"}
    # each such rule is either not evaluated at all (inputs missing) or reports the untyped room
    ne = {f.rule_id for f in fs if f.verdict == "NOT_EVALUATED" and ("r2" in f.subject_ids or not f.subject_ids)}
    assert typed_rules and typed_rules <= ne
    assert any(f.verdict == "NOT_EVALUATED" and f.subject_ids == ["r2"] for f in fs)


def test_ocr_absences_are_grouped_per_rule(pack):
    """On OCR'd input, many 'no tag read' absences become one WARNING listing every subject."""
    from reviewpulse.engine.run import run
    from reviewpulse.schema import BuildingModel, Element, Prov, Scale, Sheet

    sheet = Sheet(id="s", source_file="x.png", mode="raster", coord_unit="paper_mm", width=100, height=100,
                  scale=Scale(metres_per_unit=0.05, method="symbol_prior", confidence=0.4))
    doors = [Element(id=f"d{i}", cls="door", geom=[(i, 0), (i + 1, 0), (i + 1, 1), (i, 1)],
                     attrs={"width_m": 0.9}, prov=Prov(source="raster", stage="t", confidence=0.95))
             for i in range(0, 50, 5)]
    fs = [f for f in run(BuildingModel(sheet=sheet, elements=doors, tier="T3"), pack) if f.rule_id == "P-5"]
    assert len(fs) == 1 and fs[0].verdict == "WARNING"
    assert sorted(fs[0].subject_ids) == sorted(d.id for d in doors) and fs[0].evidence["grouped"] == 10
