"""Exact noded wall-line faces. Gaps remain gaps; no guessed closing tolerance."""
from __future__ import annotations

from shapely.geometry import LineString
from shapely.ops import polygonize_full, unary_union

from ..core.ids import IdFactory
from ..schema import Prov, Room


def polygonized_regions(lines, sheet_id):
    linework = [LineString(points) for points in lines if len(points) >= 2]
    if not linework:
        return [], {"input_lines": 0, "faces": 0, "dangles": 0, "cuts": 0, "invalid_rings": 0}
    faces, cuts, dangles, invalid = polygonize_full(unary_union(linework))
    ids = IdFactory(sheet_id)
    rooms = []
    for polygon in faces.geoms:
        outline = list(polygon.exterior.coords)[:-1]
        rooms.append(Room(id=ids("polygonized", outline), polygon=outline,
            holes=[list(ring.coords)[:-1] for ring in polygon.interiors],
            prov=Prov(source="derived", stage="polygonize", confidence=0,
                      evidence={"enclosure_basis": "exact noded linework", "classification_confirmed": False,
                                "area_basis": "not measured; centerline faces are not net room areas"})))
    return rooms, {"input_lines": len(linework), "faces": len(rooms), "cuts": len(cuts.geoms),
                   "dangles": len(dangles.geoms), "invalid_rings": len(invalid.geoms), "automatic_gap_closing": False}
