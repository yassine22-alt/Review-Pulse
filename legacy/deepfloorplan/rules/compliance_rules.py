"""Compliance rule checks for floor plan elements."""

from typing import Dict, List, Sequence

from shapely.geometry import Polygon
from shapely.ops import unary_union

from geometry.spatial_graph import compute_room_door_map
from utils.config import CONFIG


Violation = Dict[str, object]


def _door_touches_any_wall(door: Polygon, walls: Sequence) -> bool:
    """Check if a door touches wall geometry with tolerant distance checks."""
    if not walls:
        # If wall extraction fails, do not produce guaranteed false positives.
        return True

    tolerance = CONFIG.door_wall_touch_tolerance_px
    expanded_door = door.buffer(tolerance) if tolerance > 0 else door

    for wall in walls:
        if expanded_door.intersects(wall):
            return True

        if tolerance > 0:
            # Boundary distance is usually more stable than polygon-overlap for thin structures.
            if door.boundary.distance(wall) <= tolerance:
                return True
            if door.distance(wall) <= tolerance:
                return True

    return False


def _rule_min_room_size(rooms: Sequence[Polygon]) -> List[Violation]:
    violations: List[Violation] = []
    for room_id, room in enumerate(rooms):
        if room.area < CONFIG.min_room_area_rule:
            violations.append(
                {
                    "type": "MIN_ROOM_AREA",
                    "room_id": room_id,
                    "value": float(room.area),
                    "threshold": float(CONFIG.min_room_area_rule),
                    "message": "Room area is below minimum threshold",
                }
            )
    return violations


def _rule_door_must_touch_wall(doors: Sequence[Polygon], walls: Sequence) -> List[Violation]:
    if not walls:
        return []

    violations: List[Violation] = []
    for door_id, door in enumerate(doors):
        touches_wall = _door_touches_any_wall(door, walls)
        if not touches_wall:
            violations.append(
                {
                    "type": "DOOR_NOT_TOUCHING_WALL",
                    "door_id": door_id,
                    "message": "Door does not intersect any wall boundary",
                }
            )
    return violations


def _rule_room_must_have_door(rooms: Sequence[Polygon], doors: Sequence[Polygon]) -> List[Violation]:
    violations: List[Violation] = []
    room_door_map = compute_room_door_map(
        list(rooms),
        list(doors),
        buffer_px=CONFIG.room_door_buffer_px,
        max_distance_px=CONFIG.room_door_max_distance_px,
        adaptive_distance_scale=CONFIG.room_door_adaptive_distance_scale,
    )

    for room_id, door_ids in room_door_map.items():
        if len(door_ids) == 0:
            violations.append(
                {
                    "type": "ROOM_WITHOUT_DOOR",
                    "room_id": room_id,
                    "message": "Room has no intersecting door",
                }
            )
    return violations


def _rule_door_connects_two_rooms(
    rooms: Sequence[Polygon],
    doors: Sequence[Polygon],
    walls: Sequence,
) -> List[Violation]:
    violations: List[Violation] = []
    building_boundary = None
    if rooms:
        building_boundary = unary_union(list(rooms)).boundary

    def _is_exterior_door(door: Polygon, connected_room_ids: List[int]) -> bool:
        """Return True when a door is likely an exterior entry door."""
        if not CONFIG.allow_exterior_doors:
            return False
        if len(connected_room_ids) != 1:
            return False
        if building_boundary is None:
            return False

        tol = CONFIG.exterior_door_boundary_tolerance_px
        expanded_door = door.buffer(tol) if tol > 0 else door
        return expanded_door.intersects(building_boundary)

    room_door_map = compute_room_door_map(
        list(rooms),
        list(doors),
        buffer_px=CONFIG.room_door_buffer_px,
        max_distance_px=CONFIG.room_door_max_distance_px,
        adaptive_distance_scale=CONFIG.room_door_adaptive_distance_scale,
    )

    for door_id, door in enumerate(doors):
        # Skip connectivity check for doors that already fail basic wall-contact.
        # This avoids flooding the report with duplicate low-confidence violations.
        if not _door_touches_any_wall(door, walls):
            continue

        connected_room_ids = [
            room_id for room_id, door_ids in room_door_map.items() if door_id in door_ids
        ]

        if _is_exterior_door(door, connected_room_ids):
            continue

        if len(connected_room_ids) < 2:
            violations.append(
                {
                    "type": "DOOR_NOT_CONNECTING_TWO_ROOMS",
                    "door_id": door_id,
                    "connected_rooms": connected_room_ids,
                    "message": "Door intersects fewer than two rooms",
                }
            )
    return violations


def check_compliance(rooms: Sequence[Polygon], doors: Sequence[Polygon], walls: Sequence) -> List[Violation]:
    """Run all compliance checks and return violations."""
    violations: List[Violation] = []
    violations.extend(_rule_min_room_size(rooms))
    violations.extend(_rule_door_must_touch_wall(doors, walls))
    violations.extend(_rule_room_must_have_door(rooms, doors))
    violations.extend(_rule_door_connects_two_rooms(rooms, doors, walls))
    return violations
