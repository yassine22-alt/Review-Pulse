"""Visualization layer for detections and compliance violations."""

from typing import Dict, List, Sequence

import cv2
import numpy as np
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon


def _iter_polygons(geometry):
    """Yield polygon parts from single or multi-part geometries."""
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


def _iter_lines(geometry):
    """Yield line parts from single or multi-part line geometries."""
    if geometry is None or geometry.is_empty:
        return
    if isinstance(geometry, LineString):
        yield geometry
        return
    if isinstance(geometry, MultiLineString):
        for part in geometry.geoms:
            if not part.is_empty:
                yield part
        return
    if isinstance(geometry, GeometryCollection):
        for part in geometry.geoms:
            if isinstance(part, LineString) and not part.is_empty:
                yield part


def _draw_polygon_outline(image: np.ndarray, polygon: Polygon, color: tuple, thickness: int = 2) -> None:
    for part in _iter_polygons(polygon):
        coords = np.array(part.exterior.coords, dtype=np.int32)
        cv2.polylines(image, [coords], isClosed=True, color=color, thickness=thickness)


def _draw_filled_polygon(alpha_layer: np.ndarray, polygon: Polygon, color: tuple) -> None:
    for part in _iter_polygons(polygon):
        coords = np.array(part.exterior.coords, dtype=np.int32)
        cv2.fillPoly(alpha_layer, [coords], color=color)


def _violation_target_polygon(
    violation: Dict[str, object],
    rooms: Sequence[Polygon],
    doors: Sequence[Polygon],
) -> Polygon | None:
    if "room_id" in violation:
        room_id = int(violation["room_id"])
        if 0 <= room_id < len(rooms):
            return rooms[room_id]
    if "door_id" in violation:
        door_id = int(violation["door_id"])
        if 0 <= door_id < len(doors):
            return doors[door_id]
    return None


def render_overlay(
    image: np.ndarray,
    rooms: Sequence[Polygon],
    doors: Sequence[Polygon],
    violations: Sequence[Dict[str, object]],
    walls: Sequence | None = None,
    windows: Sequence[Polygon] | None = None,
) -> np.ndarray:
    """Render detections and violations over original image.

    Color scheme:
    - Rooms: transparent blue fill
    - Walls: black lines
    - Doors: green
    - Windows: cyan
    - Violations: red boxes and labels
    """
    annotated = image.copy()
    overlay = image.copy()

    for room in rooms:
        _draw_filled_polygon(overlay, room, (255, 0, 0))
    annotated = cv2.addWeighted(overlay, 0.25, annotated, 0.75, 0.0)

    if walls:
        for wall in walls:
            for line in _iter_lines(wall):
                coords = np.array(line.coords, dtype=np.int32)
                cv2.polylines(annotated, [coords], isClosed=False, color=(0, 0, 0), thickness=2)

    for door in doors:
        _draw_polygon_outline(annotated, door, (0, 255, 0), thickness=2)

    if windows:
        for window in windows:
            _draw_polygon_outline(annotated, window, (0, 255, 255), thickness=2)

    for violation in violations:
        target = _violation_target_polygon(violation, rooms, doors)
        if target is None:
            continue

        minx, miny, maxx, maxy = map(int, target.bounds)
        cv2.rectangle(annotated, (minx, miny), (maxx, maxy), color=(255, 0, 0), thickness=2)

        label = str(violation.get("type", "VIOLATION"))
        cv2.putText(
            annotated,
            label,
            (minx, max(20, miny - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 0),
            1,
            cv2.LINE_AA,
        )

    return annotated
