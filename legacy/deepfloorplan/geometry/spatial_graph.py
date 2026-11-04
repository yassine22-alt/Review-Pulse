"""Spatial graph construction for room-door connectivity."""

from typing import Dict, List

import networkx as nx
from shapely.geometry import Polygon

from utils.config import CONFIG


def build_spatial_graph(rooms: List[Polygon], doors: List[Polygon]) -> nx.Graph:
    """Build a room connectivity graph where edges represent doors.

    Args:
        rooms: List of room polygons.
        doors: List of door polygons.

    Returns:
        Undirected graph with room nodes and door edges.
    """
    graph = nx.Graph()

    for room_id, room in enumerate(rooms):
        graph.add_node(room_id, geometry=room, type="room")

    room_door_map = compute_room_door_map(
        rooms,
        doors,
        buffer_px=CONFIG.room_door_buffer_px,
        max_distance_px=CONFIG.room_door_max_distance_px,
        adaptive_distance_scale=CONFIG.room_door_adaptive_distance_scale,
    )

    for door_id, door in enumerate(doors):
        touching_rooms = [room_id for room_id, door_ids in room_door_map.items() if door_id in door_ids]

        # Connect all room pairs touched by this door.
        if len(touching_rooms) >= 2:
            for i in range(len(touching_rooms)):
                for j in range(i + 1, len(touching_rooms)):
                    graph.add_edge(
                        touching_rooms[i],
                        touching_rooms[j],
                        door_id=door_id,
                        door_geometry=door,
                    )

    return graph


def compute_room_door_map(
    rooms: List[Polygon],
    doors: List[Polygon],
    buffer_px: float = 0.0,
    max_distance_px: float | None = None,
    adaptive_distance_scale: float = 0.0,
) -> Dict[int, List[int]]:
    """Compute a map from room index to door indices with spatial tolerance.

    Args:
        rooms: Room polygons.
        doors: Door polygons.
        buffer_px: Positive value expands room polygons before intersection checks.
        max_distance_px: Optional max distance threshold for nearest-door fallback.
        adaptive_distance_scale: Scale factor applied to room size for dynamic
            distance tolerance. Example: 0.08 means 8% of sqrt(room_area).
    """
    room_doors: Dict[int, List[int]] = {idx: [] for idx in range(len(rooms))}

    expanded_rooms = [room.buffer(buffer_px) if buffer_px > 0 else room for room in rooms]

    for room_id, room in enumerate(expanded_rooms):
        base_room = rooms[room_id]
        dynamic_threshold = 0.0
        if adaptive_distance_scale > 0:
            dynamic_threshold = (base_room.area ** 0.5) * adaptive_distance_scale

        effective_max_distance = max_distance_px
        if effective_max_distance is None:
            effective_max_distance = dynamic_threshold if dynamic_threshold > 0 else None
        elif dynamic_threshold > 0:
            effective_max_distance = max(effective_max_distance, dynamic_threshold)

        for door_id, door in enumerate(doors):
            if door.intersects(room):
                room_doors[room_id].append(door_id)

        # Fallback: near-boundary doors can be slightly detached due to segmentation noise.
        if len(room_doors[room_id]) == 0 and effective_max_distance is not None:
            near_door_ids = [
                door_id
                for door_id, door in enumerate(doors)
                if base_room.boundary.distance(door) <= effective_max_distance
            ]
            room_doors[room_id].extend(near_door_ids)

    return room_doors
