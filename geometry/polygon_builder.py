"""Conversion helpers from OpenCV contours to Shapely geometries."""

from typing import Dict, Iterable, List

import numpy as np
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon
from shapely.validation import make_valid

from utils.config import CONFIG


def contour_to_polygon(contour: np.ndarray) -> Polygon:
    """Convert contour to a valid Shapely polygon when possible."""
    points = contour.reshape(-1, 2)
    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = make_valid(polygon)
    return polygon


def iter_polygons(geometry) -> Iterable[Polygon]:
    """Yield Polygon parts from Polygon/MultiPolygon/GeometryCollection."""
    if geometry is None or geometry.is_empty:
        return
    if isinstance(geometry, Polygon):
        yield geometry
        return
    if isinstance(geometry, MultiPolygon):
        for part in geometry.geoms:
            if not part.is_empty:
                yield part
        return
    if isinstance(geometry, GeometryCollection):
        for part in geometry.geoms:
            if isinstance(part, Polygon) and not part.is_empty:
                yield part


def contour_to_line(contour: np.ndarray) -> LineString:
    """Convert contour to a Shapely line used for wall boundary checks."""
    points = contour.reshape(-1, 2)
    return LineString(points)


def build_geometries(contours_by_type: Dict[str, List[np.ndarray]]) -> Dict[str, List]:
    """Build clean geometry lists for each detected class."""
    rooms = []
    walls = []
    doors = []
    windows = []

    for contour in contours_by_type.get("rooms", []):
        geometry = contour_to_polygon(contour)
        for poly in iter_polygons(geometry):
            if poly.area >= CONFIG.min_room_area:
                rooms.append(poly)

    for contour in contours_by_type.get("walls", []):
        geometry = contour_to_polygon(contour)
        for poly in iter_polygons(geometry):
            if poly.area >= CONFIG.min_wall_area:
                # Using polygon boundaries gives better intersection tests for door contact.
                walls.append(poly.boundary)

    for contour in contours_by_type.get("doors", []):
        geometry = contour_to_polygon(contour)
        for poly in iter_polygons(geometry):
            if poly.area >= CONFIG.min_door_area:
                doors.append(poly)

    for contour in contours_by_type.get("windows", []):
        geometry = contour_to_polygon(contour)
        for poly in iter_polygons(geometry):
            if poly.area >= CONFIG.min_window_area:
                windows.append(poly)

    return {
        "rooms": rooms,
        "walls": walls,
        "doors": doors,
        "windows": windows,
    }
