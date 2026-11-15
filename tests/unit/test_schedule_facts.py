"""Heights and sills live in the door and window schedule, not in the plan view: the fact graph joins them by tag."""

import handmade

from reviewpulse.factgraph.from_building import from_building
from reviewpulse.schema import Element


def _node(graph, id_):
    return next(n for n in graph.nodes if n.id == id_)


def _model(heights=True, second_window_scheduled=True):
    m = handmade.build()
    for e in m.edges:
        if e.kind == "window" and e.a == "living":
            e.via = "w1"
    m.elements = [e for e in m.elements if e.id != "w1"]
    m.elements.append(Element(id="w1", cls="window", geom=[(0, 1), (0.2, 1), (0.2, 2), (0, 2)], tag="F1", attrs={"width_m": 1.0}, prov=m.rooms[0].prov))
    rows = [{"tag": "F1", "width_m": 1.0, **({"height_m": 1.2, "sill_m": 0.9} if heights else {})}]
    m.schedules = [{"name": "windows", "rows": rows}]
    return m


def test_window_height_sill_and_area_come_from_the_schedule():
    g = from_building(_model(), complete=True)
    w = _node(g, "w1").attrs
    assert w["height_m"].value == 1.2 and w["sill_height_m"].value == 0.9
    assert abs(w["opening_area_m2"].value - 1.2) < 1e-9
    living = _node(g, "living").attrs
    assert abs(living["window_area_m2"].value - 1.2) < 1e-9
    assert abs(living["window_area_ratio"].value - 1.2 / 34.2) < 1e-3


def test_without_a_scheduled_height_the_area_is_unknown_not_zero():
    g = from_building(_model(heights=False), complete=True)
    assert "opening_area_m2" not in _node(g, "w1").attrs
    assert "window_area_m2" not in _node(g, "living").attrs
