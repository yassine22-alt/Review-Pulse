"""E2 - Synthetic adapter: truth.json -> our own objects (metres, DXF drawing units)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon

from ...schema import Element, Prov


def load_truth(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def truth_walls(t: dict) -> list[Element]:
    out = []
    for w in t["walls"]:
        out.append(Element(id=w["id"], cls="wall", geom=[tuple(p) for p in w["centreline"]], thickness=w["thickness"],
                           attrs={"connected": [True, True]}, confirmed=True,
                           prov=Prov(source="user", stage="truth", confidence=1.0)))
    return out


def truth_columns(t: dict) -> list[Element]:
    return [Element(id=f"column:{i}", cls="column", geom=[tuple(p) for p in c], confirmed=True,
                    prov=Prov(source="user", stage="truth")) for i, c in enumerate(t.get("columns", []))]


def truth_openings(t: dict) -> list[Element]:
    out = []
    for o in t["openings"]:
        poly = Polygon(o["polygon"])
        cs = list(poly.minimum_rotated_rectangle.exterior.coords)
        e0, e1 = np.subtract(cs[1], cs[0]), np.subtract(cs[2], cs[1])
        short = e0 if np.linalg.norm(e0) < np.linalg.norm(e1) else e1
        th = float(np.linalg.norm(short))
        attrs = {"width_m": o["width_m"], "mid": tuple(o["midpoint"]), "normal": tuple(short / th), "thickness": th}
        if o.get("swing_polygon"):
            attrs["swing_polygon"] = [tuple(p) for p in o["swing_polygon"]]
            attrs["hinge"] = tuple(o["hinge"])
        out.append(Element(id=o["id"], cls=o["cls"], geom=[tuple(p) for p in o["polygon"]], attrs=attrs,
                           tag=o.get("tag") or None, confirmed=True, prov=Prov(source="user", stage="truth")))
    return out


def truth_room_polys(t: dict) -> dict[str, Polygon]:
    return {r["id"]: Polygon(r["polygon"]) for r in t["rooms"]}


def truth_wall_lines(t: dict) -> list[tuple[LineString, float]]:
    return [(LineString(w["centreline"]), w["thickness"]) for w in t["walls"]]


def truth_model(t: dict, sheet):
    """The oracle BuildingModel: exact walls, openings, rooms, graph, dimensions and schedule.
    ``sheet`` supplies texts/title block (read exactly from the DXF); geometry comes from truth."""
    from ...core.geometry import width_profile
    from ...schema import BuildingModel, Dimension, Edge, Room, Scale

    sheet = sheet.model_copy(deep=True)
    sheet.scale = Scale(metres_per_unit=1.0, method="dxf_units", confidence=1.0)
    walls, cols, ops = truth_walls(t), truth_columns(t), truth_openings(t)
    rooms = []
    for r in t["rooms"]:
        poly = Polygon(r["polygon"])
        mn, med = width_profile(poly)
        has_win = any(o["cls"] == "window" and r["id"] in o["rooms"] for o in t["openings"])
        rooms.append(Room(id=r["id"], polygon=[tuple(p) for p in r["polygon"]], label=r.get("label"),
                          type=r["type"] if r.get("label") else None, stated_area_m2=r.get("stated_area_m2"),
                          area_m2=round(poly.area, 4), min_width_m=round(mn, 4), is_corridor=r["type"] == "corridor",
                          has_window=has_win, prov=Prov(source="user", stage="truth",
                                                        evidence={"median_width_m": round(med, 4)})))
    edges = []
    for o in t["openings"]:
        a, b = o["rooms"]
        kind = "door" if o["cls"] == "door" else "window"
        edges.append(Edge(a=a, b=b, kind=kind, via=o["id"], width_m=o["width_m"], prov=Prov(source="user", stage="truth")))
    dims = []
    for d in t["dimensions"]:
        dims.append(Dimension(id=d["id"], value_m=d["stated_m"], measured_m=d["measured_m"], p1=tuple(d["p1"]),
                              p2=tuple(d["p2"]), chain_id=d["chain"],
                              prov=Prov(source="user", stage="truth", evidence={"overall": d["overall"]})))
    sheet.dimensions = dims
    sched = [{"name": "openings", "rows": [{k: v for k, v in r.items() if k in ("tag", "width_m", "height_m")}
                                           for r in t["schedule"]]}]
    return BuildingModel(sheet=sheet, elements=walls + cols + ops, rooms=rooms, edges=edges, schedules=sched, tier="T1")
