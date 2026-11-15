"""Hand-made BuildingModel for the Judge (engine-level tests from day 1).

A small flat, metres, scale exact (T1):

    +---------+---------+---------+
    | BED A   | BATH    | BED B   |      BED B reaches the exit only through BATH (C-T1 FAIL)
    +--d1-----+--d2-----+--d3-----+      BED B door into BATH, not into the hall
    |            HALL             |
    +---d4--------+---------------+
    | LIVING  (exit d0)           |
    +-----------------------------+

The proposal's worked example (Table 13) should replace this once its exact
content is copied from the PDF; the structure of the test stays the same.
"""

from __future__ import annotations

from reviewpulse.schema import BuildingModel, Edge, Element, Prov, Room, Scale, Sheet

P = Prov(source="user", stage="handmade", confidence=1.0)


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def door(id_, x0, y0, x1, y1, width, tag=None, swing=None):
    return Element(id=id_, cls="door", geom=rect(x0, y0, x1, y1), tag=tag, confirmed=True,
                   attrs={"width_m": width, "mid": ((x0 + x1) / 2, (y0 + y1) / 2),
                          **({"swing_polygon": swing} if swing else {})}, prov=P)


def build(bed_b_via_bath: bool = True, narrow_door: bool = False, tier: str = "T1") -> BuildingModel:
    sheet = Sheet(id="handmade", source_file="handmade", mode="vector", coord_unit="drawing_unit", width=9, height=9,
                  scale=Scale(metres_per_unit=1.0, method="dxf_units", confidence=1.0))
    rooms = [
        Room(id="bedA", polygon=rect(0, 5, 3, 8), label="CHAMBRE 1", type="bedroom", area_m2=9.0,
             min_width_m=3.0, has_window=True, prov=P),
        Room(id="bath", polygon=rect(3, 5, 6, 8), label="SDB", type="bathroom", area_m2=9.0, min_width_m=3.0,
             has_window=True, prov=P),
        Room(id="bedB", polygon=rect(6, 5, 9, 8), label="CHAMBRE 2", type="bedroom", area_m2=9.0,
             min_width_m=3.0, has_window=True, prov=P),
        Room(id="hall", polygon=rect(0, 3.8, 9, 5), label="DEGAGEMENT", type="corridor", area_m2=10.8,
             min_width_m=1.2, is_corridor=True, has_window=False, prov=P),
        Room(id="living", polygon=rect(0, 0, 9, 3.8), label="SEJOUR", type="living", area_m2=34.2,
             min_width_m=3.8, has_window=True, prov=P),
    ]
    els = [
        door("d0", 1, -0.1, 2, 0.1, 0.90, "P1"),
        door("d1", 1, 4.9, 2, 5.1, 0.70 if narrow_door else 0.85, "P2"),
        door("d2", 4, 4.9, 5, 5.1, 0.80, "P3"),
        door("d4", 1, 3.7, 2, 3.9, 0.90, "P5"),
    ]
    edges = [
        Edge(a="living", b="EXIT", kind="door", via="d0", width_m=0.90, prov=P),
        Edge(a="bedA", b="hall", kind="door", via="d1", width_m=els[1].attrs["width_m"], prov=P),
        Edge(a="bath", b="hall", kind="door", via="d2", width_m=0.80, prov=P),
        Edge(a="hall", b="living", kind="door", via="d4", width_m=0.90, prov=P),
    ]
    if bed_b_via_bath:
        els.append(door("d3", 5.9, 6, 6.1, 7, 0.80, "P4"))
        edges.append(Edge(a="bedB", b="bath", kind="door", via="d3", width_m=0.80, prov=P))
    else:
        els.append(door("d3", 7, 4.9, 8, 5.1, 0.80, "P4"))
        edges.append(Edge(a="bedB", b="hall", kind="door", via="d3", width_m=0.80, prov=P))
    for r in rooms:
        if r.has_window:
            edges.append(Edge(a=r.id, b="EXTERIOR", kind="window", prov=P))
    els.append(Element(id="w1", cls="window", geom=rect(0, 1, 0.2, 2), attrs={"width_m": 1.0}, prov=P))
    model = BuildingModel(sheet=sheet, elements=els, rooms=rooms, edges=edges, tier=tier)
    # every object shares the module's Prov above; a round trip gives each its own copy, so one test that edits a room's
    # provenance (for example marks its label as read by a model) cannot change the plans other tests build
    return BuildingModel.model_validate(model.model_dump())


if __name__ == "__main__":     # writes tests/fixtures/handmade_model.json
    from pathlib import Path

    from reviewpulse.schema import save

    save(build(), Path(__file__).with_name("handmade_model.json"))
