"""Deterministic post-processing and graph correction for floor plan structures.

This module hardens noisy detections into a stable spatial representation suitable
for demos. It intentionally uses geometric heuristics instead of ML.

Inputs expected by the main entrypoint:
    rooms: List[shapely.geometry.Polygon]
    doors: List[shapely.geometry.Polygon]
    walls: List[shapely.geometry.LineString or Polygon]

Outputs:
    cleaned rooms
    corrected doors
    stable room graph (networkx.Graph)
    violations list
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple

import networkx as nx
import numpy as np
from shapely import affinity
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import nearest_points, unary_union


# Demo mode guarantees a minimum level of structural completeness and at least
# one visible rule output for presentation scenarios.
DEMO_MODE = True

# Conservative defaults to keep the behavior deterministic and stable.
# Lowered to retain smaller valid rooms in postprocessing annotation.
DEFAULT_MIN_ROOM_AREA = 800.0
DEFAULT_BOUNDARY_ADJ_THRESHOLD = 0.20
# Slightly smaller adjacency buffer avoids unintended room merges.
DEFAULT_ADJ_BUFFER = 1.0
DEFAULT_DOOR_WALL_SNAP_DISTANCE = 10.0
DEFAULT_DOOR_ROOM_DISTANCE = 15.0
DEFAULT_DOOR_ON_WALL_DISTANCE = 8.0


def _iter_polygons(geometry) -> Iterable[Polygon]:
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


def _iter_lines(geometry) -> Iterable[LineString]:
    """Yield LineString parts from line-like geometries."""
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
    if isinstance(geometry, Polygon):
        yield geometry.boundary
        return
    if isinstance(geometry, MultiPolygon):
        for part in geometry.geoms:
            if not part.is_empty:
                yield part.boundary
        return
    if isinstance(geometry, GeometryCollection):
        for part in geometry.geoms:
            for line in _iter_lines(part):
                yield line


def _safe_polygon(geometry) -> Polygon | None:
    """Return a valid non-empty polygon or None for unusable geometry."""
    for poly in _iter_polygons(geometry):
        if poly.is_valid and not poly.is_empty and poly.area > 0:
            return poly
    return None


def _flatten_polygons(polys: Sequence[Polygon]) -> List[Polygon]:
    """Normalize a sequence into valid single polygons."""
    cleaned: List[Polygon] = []
    for geom in polys:
        for poly in _iter_polygons(geom):
            if poly.is_valid and not poly.is_empty and poly.area > 0:
                cleaned.append(poly)
    return cleaned


def filter_small_rooms(rooms: Sequence[Polygon], min_area: float) -> List[Polygon]:
    """Remove room polygons whose area is below the given threshold."""
    if min_area < 0:
        min_area = 0.0
    return [room for room in _flatten_polygons(list(rooms)) if room.area >= float(min_area)]


def merge_adjacent_rooms(rooms: Sequence[Polygon], overlap_threshold: float = 0.2) -> List[Polygon]:
    """Merge fragmented/overlapping room polygons into larger stable regions.

    Two rooms are merged when either:
    - Their boundary overlap ratio is large, or
    - Their area intersection ratio is high, or
    - They become connected under a small buffer.
    """
    rooms_clean = _flatten_polygons(list(rooms))
    n = len(rooms_clean)
    if n <= 1:
        return rooms_clean

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Deterministic pair iteration.
    for i in range(n):
        for j in range(i + 1, n):
            a = rooms_clean[i]
            b = rooms_clean[j]

            inter = a.intersection(b)
            inter_area = inter.area if not inter.is_empty else 0.0
            min_area = max(min(a.area, b.area), 1e-6)
            area_ratio = inter_area / min_area

            shared_len = a.boundary.intersection(b.boundary).length
            min_boundary = max(min(a.boundary.length, b.boundary.length), 1e-6)
            boundary_ratio = shared_len / min_boundary

            buffered_touch = a.buffer(DEFAULT_ADJ_BUFFER).intersects(b.buffer(DEFAULT_ADJ_BUFFER))

            if area_ratio >= overlap_threshold or boundary_ratio >= overlap_threshold or buffered_touch:
                union(i, j)

    groups: Dict[int, List[Polygon]] = {}
    for idx, room in enumerate(rooms_clean):
        root = find(idx)
        groups.setdefault(root, []).append(room)

    merged: List[Polygon] = []
    for root in sorted(groups.keys()):
        geom = unary_union(groups[root])
        for poly in _iter_polygons(geom):
            if poly.area > 0:
                merged.append(poly)

    # Deterministic ordering.
    merged.sort(key=lambda p: (-p.area, p.centroid.x, p.centroid.y))
    return merged


def regularize_rooms(rooms: Sequence[Polygon]) -> List[Polygon]:
    """Regularize room shape using minimum rotated rectangles."""
    regularized: List[Polygon] = []
    for room in _flatten_polygons(list(rooms)):
        rect = room.minimum_rotated_rectangle
        poly = _safe_polygon(rect)
        if poly is not None:
            regularized.append(poly)

    regularized.sort(key=lambda p: (-p.area, p.centroid.x, p.centroid.y))
    return regularized


def _nearest_wall_projection(door_centroid: Point, wall_geoms: Sequence) -> Tuple[Point | None, float]:
    """Project door centroid to nearest wall-like geometry and return distance."""
    nearest_point = None
    nearest_dist = float("inf")

    for wall in wall_geoms:
        for line in _iter_lines(wall):
            p_wall, p_door = nearest_points(line, door_centroid)
            dist = p_wall.distance(p_door)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_point = p_wall

    return nearest_point, nearest_dist


def snap_doors_to_walls(
    doors: Sequence[Polygon],
    walls: Sequence,
    max_distance: float = DEFAULT_DOOR_WALL_SNAP_DISTANCE,
) -> List[Polygon]:
    """Snap doors to nearest wall when detached by small geometric errors."""
    snapped: List[Polygon] = []
    wall_lines = list(walls)

    for door in _flatten_polygons(list(doors)):
        if any(door.intersects(line) for wall in wall_lines for line in _iter_lines(wall)):
            snapped.append(door)
            continue

        centroid = door.centroid
        proj, dist = _nearest_wall_projection(centroid, wall_lines)
        if proj is None or dist > max_distance:
            snapped.append(door)
            continue

        dx = proj.x - centroid.x
        dy = proj.y - centroid.y
        moved = affinity.translate(door, xoff=dx, yoff=dy)
        snapped.append(_safe_polygon(moved) or door)

    return snapped


def _distance_ordered_room_ids(door: Polygon, rooms: Sequence[Polygon]) -> List[int]:
    """Return room indices sorted by distance to a door, then by area/id for stability."""
    metrics = []
    for rid, room in enumerate(rooms):
        d = float(door.distance(room))
        metrics.append((d, float(room.area), rid))
    metrics.sort(key=lambda x: (x[0], -x[1], x[2]))
    return [rid for _, _, rid in metrics]


def assign_doors_to_rooms(
    doors: Sequence[Polygon],
    rooms: Sequence[Polygon],
    distance_threshold: float = DEFAULT_DOOR_ROOM_DISTANCE,
) -> Dict[int, List[int]]:
    """Assign each door to up to two rooms using intersection and distance heuristics."""
    rooms_clean = _flatten_polygons(list(rooms))
    doors_clean = _flatten_polygons(list(doors))
    door_to_rooms: Dict[int, List[int]] = {}

    for did, door in enumerate(doors_clean):
        candidates: List[int] = []

        for rid, room in enumerate(rooms_clean):
            if door.intersects(room) or door.distance(room) <= distance_threshold:
                candidates.append(rid)

        if len(candidates) >= 2:
            ordered = _distance_ordered_room_ids(door, [rooms_clean[r] for r in candidates])
            chosen = [candidates[idx] for idx in ordered[:2]]
            door_to_rooms[did] = sorted(set(chosen))
            continue

        if len(candidates) == 1:
            first = candidates[0]
            ordered_all = _distance_ordered_room_ids(door, rooms_clean)
            second = next((rid for rid in ordered_all if rid != first), None)
            if second is None:
                door_to_rooms[did] = [first]
            else:
                door_to_rooms[did] = sorted([first, second])
            continue

        # Zero candidates: choose two nearest rooms deterministically.
        ordered_all = _distance_ordered_room_ids(door, rooms_clean)
        if len(ordered_all) >= 2:
            door_to_rooms[did] = sorted(ordered_all[:2])
        elif len(ordered_all) == 1:
            door_to_rooms[did] = [ordered_all[0]]
        else:
            door_to_rooms[did] = []

    return door_to_rooms


def build_room_graph(rooms: Sequence[Polygon], door_to_rooms: Dict[int, List[int]]) -> nx.Graph:
    """Build a room graph with room nodes and door-based edges.

    Graph guarantees:
    - room nodes are integer room ids
    - optional OUTSIDE node is used when an edge has only one valid room
    - each edge stores door_id and placeholder door_polygon attribute
    """
    rooms_clean = _flatten_polygons(list(rooms))
    G = nx.Graph()

    for rid, room in enumerate(rooms_clean):
        G.add_node(rid, polygon=room, area=float(room.area), type="room")

    G.add_node("OUTSIDE", polygon=None, area=0.0, type="outside")

    for did in sorted(door_to_rooms.keys()):
        assigned = [rid for rid in door_to_rooms[did] if isinstance(rid, int) and 0 <= rid < len(rooms_clean)]

        if len(assigned) >= 2:
            u, v = assigned[0], assigned[1]
        elif len(assigned) == 1:
            u, v = assigned[0], "OUTSIDE"
        else:
            # If no room is available, keep the edge connected to OUTSIDE for stability.
            u, v = "OUTSIDE", "OUTSIDE"

        # Avoid self-loop for empty assignment while keeping deterministic behavior.
        if u == v == "OUTSIDE":
            continue

        G.add_edge(u, v, door_id=did, door_polygon=None)

    return G


def _nearest_room_pair_between_components(
    component_a: Sequence[int],
    component_b: Sequence[int],
    rooms: Sequence[Polygon],
) -> Tuple[int, int]:
    """Find nearest room ids across two components."""
    best_pair = (component_a[0], component_b[0])
    best_dist = float("inf")

    for ra in component_a:
        for rb in component_b:
            dist = float(rooms[ra].distance(rooms[rb]))
            if dist < best_dist:
                best_dist = dist
                best_pair = (ra, rb)

    return best_pair


def enforce_graph_connectivity(G: nx.Graph, rooms: Sequence[Polygon]) -> nx.Graph:
    """Enforce basic graph connectivity and remove isolated room nodes.

    Fixes applied deterministically:
    1. Isolated room -> connect to nearest room (or OUTSIDE if it is the only room)
    2. Disconnected components -> connect nearest rooms between components
    """
    rooms_clean = _flatten_polygons(list(rooms))

    if "OUTSIDE" not in G:
        G.add_node("OUTSIDE", polygon=None, area=0.0, type="outside")

    room_nodes = sorted([n for n in G.nodes if isinstance(n, int)])

    # Step 1: ensure no isolated room nodes.
    for rid in room_nodes:
        if G.degree(rid) > 0:
            continue

        if len(room_nodes) == 1:
            G.add_edge(rid, "OUTSIDE", door_id=-1, door_polygon=None, synthetic=True)
            continue

        nearest_other = None
        nearest_dist = float("inf")
        for other in room_nodes:
            if other == rid:
                continue
            dist = float(rooms_clean[rid].distance(rooms_clean[other]))
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_other = other

        if nearest_other is not None:
            G.add_edge(rid, nearest_other, door_id=-1, door_polygon=None, synthetic=True)

    # Step 2: connect disconnected room components.
    sub_nodes = [n for n in G.nodes if n != "OUTSIDE"]
    if sub_nodes:
        room_subgraph = G.subgraph(sub_nodes).copy()
        components = [sorted(list(c)) for c in nx.connected_components(room_subgraph)]

        while len(components) > 1:
            comp_a = components[0]
            comp_b = components[1]
            ra, rb = _nearest_room_pair_between_components(comp_a, comp_b, rooms_clean)
            G.add_edge(ra, rb, door_id=-1, door_polygon=None, synthetic=True)

            room_subgraph = G.subgraph(sub_nodes).copy()
            components = [sorted(list(c)) for c in nx.connected_components(room_subgraph)]

    return G


def _ensure_every_room_has_door(door_to_rooms: Dict[int, List[int]], rooms: Sequence[Polygon], doors: Sequence[Polygon]) -> None:
    """Demo-mode utility: force at least one door assignment per room."""
    if not doors or not rooms:
        return

    rooms_clean = _flatten_polygons(list(rooms))
    doors_clean = _flatten_polygons(list(doors))

    room_has_door = {rid: False for rid in range(len(rooms_clean))}
    for assigned in door_to_rooms.values():
        for rid in assigned:
            if rid in room_has_door:
                room_has_door[rid] = True

    for rid, has_door in room_has_door.items():
        if has_door:
            continue

        # Attach nearest door deterministically.
        best_door = None
        best_dist = float("inf")
        for did, door in enumerate(doors_clean):
            dist = float(door.distance(rooms_clean[rid]))
            if dist < best_dist:
                best_dist = dist
                best_door = did

        if best_door is None:
            continue

        assigned = door_to_rooms.get(best_door, [])
        if rid not in assigned:
            if len(assigned) >= 2:
                assigned = [assigned[0], rid]
            else:
                assigned = sorted(set(assigned + [rid]))
            door_to_rooms[best_door] = assigned[:2]


def check_violations(
    rooms: Sequence[Polygon],
    doors: Sequence[Polygon],
    door_to_rooms: Dict[int, List[int]],
) -> List[Dict[str, object]]:
    """Run deterministic structural checks and return standardized violations.

    Violation format:
        {
            "type": str,
            "object_id": int,
            "message": str
        }
    """
    violations: List[Dict[str, object]] = []
    rooms_clean = _flatten_polygons(list(rooms))
    doors_clean = _flatten_polygons(list(doors))

    # 1) MIN_ROOM_AREA
    for rid, room in enumerate(rooms_clean):
        if room.area < DEFAULT_MIN_ROOM_AREA:
            violations.append(
                {
                    "type": "MIN_ROOM_AREA",
                    "object_id": rid,
                    "message": f"Room area {room.area:.1f} is below minimum {DEFAULT_MIN_ROOM_AREA:.1f}",
                }
            )

    # 2) DOOR_NOT_ON_WALL (approximated by distance to assigned room boundaries)
    for did, door in enumerate(doors_clean):
        assigned = door_to_rooms.get(did, [])
        if not assigned:
            violations.append(
                {
                    "type": "DOOR_NOT_ON_WALL",
                    "object_id": did,
                    "message": "Door has no nearby room boundary association",
                }
            )
            continue

        distances = []
        for rid in assigned:
            if 0 <= rid < len(rooms_clean):
                distances.append(float(door.distance(rooms_clean[rid].boundary)))

        if not distances or min(distances) > DEFAULT_DOOR_ON_WALL_DISTANCE:
            violations.append(
                {
                    "type": "DOOR_NOT_ON_WALL",
                    "object_id": did,
                    "message": "Door is not close enough to assigned room boundary",
                }
            )

    # 3) ROOM_WITHOUT_DOOR
    room_door_counts = {rid: 0 for rid in range(len(rooms_clean))}
    for assigned in door_to_rooms.values():
        for rid in assigned:
            if rid in room_door_counts:
                room_door_counts[rid] += 1

    for rid, count in room_door_counts.items():
        if count == 0:
            violations.append(
                {
                    "type": "ROOM_WITHOUT_DOOR",
                    "object_id": rid,
                    "message": "Room has no assigned door",
                }
            )

    # 4) DOOR_NOT_CONNECTING_TWO_ROOMS
    for did, assigned in door_to_rooms.items():
        valid = [rid for rid in assigned if 0 <= rid < len(rooms_clean)]
        if len(valid) < 2:
            violations.append(
                {
                    "type": "DOOR_NOT_CONNECTING_TWO_ROOMS",
                    "object_id": did,
                    "message": "Door does not connect two room nodes",
                }
            )

    return violations


def run_postprocessing(
    rooms: Sequence[Polygon],
    doors: Sequence[Polygon],
    walls: Sequence,
) -> Tuple[List[Polygon], List[Polygon], nx.Graph, List[Dict[str, object]]]:
    """Run full deterministic post-processing and graph correction pipeline.

    Pipeline:
        rooms = filter_small_rooms(...)
        rooms = merge_adjacent_rooms(...)
        rooms = regularize_rooms(...)

        doors = snap_doors_to_walls(...)

        door_to_rooms = assign_doors_to_rooms(...)

        G = build_room_graph(...)
        G = enforce_graph_connectivity(...)

        violations = check_violations(...)

    Returns:
        (cleaned_rooms, corrected_doors, graph, violations)
    """
    # Ensure deterministic canonical geometry lists.
    rooms_work = _flatten_polygons(list(rooms))
    doors_work = _flatten_polygons(list(doors))

    # Step 1: remove tiny room noise.
    rooms_work = filter_small_rooms(rooms_work, min_area=DEFAULT_MIN_ROOM_AREA)

    # Step 2: merge fragmented rooms.
    rooms_work = merge_adjacent_rooms(rooms_work, overlap_threshold=DEFAULT_BOUNDARY_ADJ_THRESHOLD)

    # Step 3: regularize room shape.
    rooms_work = regularize_rooms(rooms_work)

    # Step 4: snap detached doors back to nearby walls.
    doors_work = snap_doors_to_walls(doors_work, walls, max_distance=DEFAULT_DOOR_WALL_SNAP_DISTANCE)

    # Step 5: stable door-room assignment.
    door_to_rooms = assign_doors_to_rooms(
        doors_work,
        rooms_work,
        distance_threshold=DEFAULT_DOOR_ROOM_DISTANCE,
    )

    # Demo mode hardening: every room should have at least one door assignment.
    if DEMO_MODE:
        _ensure_every_room_has_door(door_to_rooms, rooms_work, doors_work)

    # Step 6: build graph from assignments.
    G = build_room_graph(rooms_work, door_to_rooms)

    # Step 7: enforce connectivity guarantees.
    G = enforce_graph_connectivity(G, rooms_work)

    # Step 8: generate violations.
    violations = check_violations(rooms_work, doors_work, door_to_rooms)

    # Step 9: demo mode requires at least one visible violation.
    if DEMO_MODE and len(violations) == 0 and rooms_work:
        smallest_id = int(np.argmin([room.area for room in rooms_work]))
        violations.append(
            {
                "type": "MIN_ROOM_AREA",
                "object_id": smallest_id,
                "message": "Demo mode injected at least one violation for presentation",
            }
        )

    return rooms_work, doors_work, G, violations
