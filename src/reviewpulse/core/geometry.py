"""Small geometry helpers shared by every stage (pure functions, sheet space, y up)."""

from __future__ import annotations

import math

from shapely.geometry import LineString, Polygon

from ..schema import Point


def seg_len(p: Point, q: Point) -> float:
    return math.hypot(q[0] - p[0], q[1] - p[1])


def seg_angle(p: Point, q: Point) -> float:
    """Undirected angle in degrees within [0, 180)."""
    return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])) % 180.0


def angle_diff(a: float, b: float, period: float = 180.0) -> float:
    d = abs(a - b) % period
    return min(d, period - d)


def side_by_side(a: tuple[Point, Point], b: tuple[Point, Point], max_deg: float = 5.0, share: float = 0.5) -> bool:
    """Two straight strokes drawn side by side, like the panes of one window symbol: parallel, and
    overlapping along their direction by ``share`` of the shorter (strokes of neighbouring windows in
    a row are collinear and do not overlap). Their distance apart is the caller's test."""
    (ax, ay), (bx, by) = a
    dx, dy = bx - ax, by - ay
    la = math.hypot(dx, dy)
    lb = math.hypot(b[1][0] - b[0][0], b[1][1] - b[0][1])
    if not la or not lb:
        return False
    cos = abs(dx * (b[1][0] - b[0][0]) + dy * (b[1][1] - b[0][1])) / (la * lb)
    if cos < math.cos(math.radians(max_deg)):
        return False
    t = sorted(((q[0] - ax) * dx + (q[1] - ay) * dy) / la for q in b)
    return min(la, t[1]) - max(0.0, t[0]) >= share * min(la, lb)


def arc_points(center: Point, radius: float, a0: float, a1: float, n: int = 16) -> list[Point]:
    """Points along a counter-clockwise arc from a0 to a1 (degrees)."""
    sweep = (a1 - a0) % 360.0 or 360.0
    out = []
    for i in range(n + 1):
        t = math.radians(a0 + sweep * i / n)
        out.append((center[0] + radius * math.cos(t), center[1] + radius * math.sin(t)))
    return out


def arc_sweep(a0: float, a1: float) -> float:
    return (a1 - a0) % 360.0 or 360.0


def sector_polygon(center: Point, radius: float, a0: float, a1: float, n: int = 16) -> Polygon:
    return Polygon([center, *arc_points(center, radius, a0, a1, n)])


def width_profile(poly: Polygon, stations: int = 40) -> tuple[float, float]:
    """(min width, median width) measured perpendicular to the long axis of the
    minimum rotated rectangle, at stations between 10% and 90% of its length."""
    if poly.is_empty or poly.area == 0:
        return 0.0, 0.0
    rect = poly.minimum_rotated_rectangle
    xs = list(rect.exterior.coords)[:4]
    e0 = (xs[0], xs[1])
    e1 = (xs[1], xs[2])
    long_e, short_e = (e0, e1) if seg_len(*e0) >= seg_len(*e1) else (e1, e0)
    (ax, ay), (bx, by) = long_e
    L = seg_len(*long_e)
    ux, uy = (bx - ax) / L, (by - ay) / L
    nx_, ny_ = -uy, ux
    span = seg_len(*short_e) * 2 + 1.0
    widths = []
    # the axis runs through the middle of the rectangle
    cx, cy = rect.centroid.x, rect.centroid.y
    for i in range(stations):
        t = 0.1 + 0.8 * i / max(stations - 1, 1)
        s = (t - 0.5) * L
        px, py = cx + ux * s, cy + uy * s
        cut = LineString([(px - nx_ * span, py - ny_ * span), (px + nx_ * span, py + ny_ * span)])
        inter = poly.intersection(cut)
        if inter.is_empty:
            continue
        pieces = getattr(inter, "geoms", [inter])
        from shapely.geometry import Point as SPoint

        ctr = SPoint(px, py)
        best = None
        for g in pieces:
            if g.length <= 0:
                continue
            if g.distance(ctr) < 1e-6:
                best = g.length
                break
            best = g.length if best is None else min(best, g.length)
        if best is not None:
            widths.append(best)
    if not widths:
        return 0.0, 0.0
    widths.sort()
    return widths[0], widths[len(widths) // 2]


class Walkable:
    """Shortest walking distances inside a room polygon (holes are obstacles): a visibility graph
    over the polygon's corners, so a path bends around corners instead of crossing walls."""

    def __init__(self, poly: Polygon):
        import networkx as nx
        from shapely.prepared import prep

        self.poly = poly
        ext = max(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1], 1e-9)
        self._region = prep(poly.buffer(1e-6 * ext))
        rings = [poly.exterior] + list(poly.interiors)
        self.corners = list(dict.fromkeys(tuple(c) for r in rings for c in list(r.coords)[:-1]))
        self.g = nx.Graph()
        for i, a in enumerate(self.corners):
            for b in self.corners[i + 1:]:
                if self.sees(a, b):
                    self.g.add_edge(a, b, weight=seg_len(a, b))

    def sees(self, a: Point, b: Point) -> bool:
        return a == b or self._region.contains(LineString([a, b]))

    def entry(self, p: Point) -> Point:
        """Where a point outside the room (a door on the wall axis) enters it: nearest boundary point."""
        from shapely.geometry import Point as SPoint
        from shapely.ops import nearest_points

        q = SPoint(p)
        if self.poly.covers(q):
            return (q.x, q.y)
        b = nearest_points(self.poly.boundary, q)[0]
        return (b.x, b.y)

    def from_point(self, src: Point) -> dict[Point, float]:
        """Walking distance from ``src`` (inside or on the room) to every corner."""
        import networkx as nx

        g = self.g.copy()
        for c in self.corners:
            if self.sees(src, c):
                g.add_edge(src, c, weight=seg_len(src, c))
        if src not in g:
            return {}
        return nx.single_source_dijkstra_path_length(g, src, weight="weight")

    def distance(self, a: Point, b: Point, from_a: dict[Point, float] | None = None) -> float:
        """Walking distance between two points of the room (inf when no route stays inside)."""
        if self.sees(a, b):
            return seg_len(a, b)
        d = from_a if from_a is not None else self.from_point(a)
        best = math.inf
        for c, dc in d.items():
            if c != a and self.sees(c, b):
                best = min(best, dc + seg_len(c, b))
        return best
