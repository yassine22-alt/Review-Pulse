"""R10 - Rooms and the room graph.

A closed polygon is not a room: rooms are the connected components of free
space left by the barrier (walls + columns + closed openings). Connectivity is
recorded separately by probing each opening on both sides.
"""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from ..annotate.text_classify import match_room
from ..core.geometry import width_profile
from ..core.ids import IdFactory
from ..schema import Edge, Element, Prov, Room, Sheet, TextItem

CLOSING_M = 0.15
MIN_ROOM_M2 = 1.0
PROBE_M = 0.15
ADJ_SHARED_M = 0.30
OUTDOOR_LABEL_M = 3.0       # balcony/terrace label this close to the outer side of a door
ADJ_GAP_M = 0.35            # rooms separated by at most one wall (thickest 0.30 m + tolerance)
GARAGE_DOOR_M = 2.0
ENVELOPE_WARN = 0.40
GRID = 1e-4                 # stored coordinates are rounded to this (sheet units)



def _largest(g):
    """The largest polygon of ``g`` (precision snapping can split a pinched outline), or None."""
    parts = [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon" and not q.is_empty]
    return max(parts, key=lambda q: q.area) if parts else None

def build_barrier(walls: list[Element], columns: list[Element], openings: list[Element]):
    parts = [LineString(w.geom).buffer(w.thickness / 2, cap_style="square", join_style="mitre")
             for w in walls if w.cls == "wall" and w.thickness]
    parts += [Polygon(c.geom) for c in columns]
    parts += [Polygon(o.geom).buffer(0) for o in openings if len(o.geom) >= 3]
    return unary_union(parts) if parts else Polygon()


LEAK_GAP_M = 1.5     # the outside never enters a dwelling through a passage narrower than this
LEAK_MAX_MOUTH = 0.12  # share of a sealed space's perimeter that may touch the true outside
OUTSIDE_RING_M = 3.0   # margin of free space around the building (must stay connected after sealing)


def _seal_envelope_leaks(exterior: list, corners: list, r: float, min_area: float) -> list:
    """Spaces joined to the true outside only through a narrow passage (a gap in the envelope that
    is not a recognised opening) are interior. Erode the outside by ``r``: what is then cut off from
    the sheet corners is interior; dilate it back and keep what is large enough to be a room."""
    out = []
    from shapely.geometry import LineString as _LS

    ring = _LS([(c.x, c.y) for c in corners] + [(corners[0].x, corners[0].y)])   # outer edge of the sheet margin
    for ext in exterior:
        eroded = ext.buffer(-r, join_style="mitre")
        parts = [g for g in getattr(eroded, "geoms", [eroded]) if not g.is_empty]
        outside = [g for g in parts if g.distance(ring) <= r * 1.5]
        cut_off = [g for g in parts if all(g is not o for o in outside)]
        if not cut_off:
            continue
        true_out = unary_union(outside).buffer(r, join_style="mitre") if outside else Polygon()
        rest = ext.difference(true_out)
        for g in getattr(rest, "geoms", [rest]):
            if g.geom_type != "Polygon" or g.area < min_area or not any(g.intersects(c) for c in cut_off):
                continue
            # a room behind an envelope gap touches the outside only through the gap; a facade
            # recess or porch is open along much of its edge and stays outside
            mouth = g.boundary.intersection(true_out.buffer(r * 0.05)).length
            if mouth <= LEAK_MAX_MOUTH * g.length:
                out.append(g)
    return out


def _room_type(label: str | None) -> str | None:
    return match_room(label) if label else None


def detect_rooms(sheet: Sheet, walls: list[Element], columns: list[Element], openings: list[Element],
                 mpu: float, scale_known: bool = True, barrier=None) -> tuple[list[Room], list[Edge], list[str]]:
    """``barrier`` may be given directly (e.g. true wall polygons from a dataset) to test this
    stage alone; otherwise it is built from the wall, column and opening elements."""
    ids = IdFactory(sheet.id)
    warnings: list[str] = []
    walls = [w for w in walls if w.cls == "wall"]
    if barrier is None:
        if not walls:
            return [], [], ["no walls: rooms not built"]
        barrier = build_barrier(walls, columns, openings)
    r = CLOSING_M / mpu
    closed = barrier.buffer(r, join_style="mitre").buffer(-r, join_style="mitre")
    if closed.area > barrier.area * 1.02:
        warnings.append(f"closing of {CLOSING_M} m added {100 * (closed.area / barrier.area - 1):.1f}% barrier area")
    env = box(*closed.bounds).buffer(OUTSIDE_RING_M / mpu, join_style="mitre")
    space = env.difference(closed)
    comps = list(getattr(space, "geoms", [space]))
    corners = [Point(c) for c in list(env.exterior.coords)[:4]]
    exterior = [g for g in comps if any(g.buffer(1e-6).contains(c) for c in corners)]
    min_area = MIN_ROOM_M2 / (mpu * mpu) if scale_known else 0.0005 * env.area
    inner = [g for g in comps if g not in exterior and g.area >= min_area]
    leaked = _seal_envelope_leaks(exterior, corners, LEAK_GAP_M / 2 / mpu, min_area)
    if leaked:
        warnings.append(f"envelope leak sealed: {len(leaked)} space(s) reached the outside only through "
                        f"a gap narrower than {LEAK_GAP_M} m (undrawn wall or unrecognised opening)")
        inner += leaked
    bld = box(*barrier.bounds)
    for g in inner:
        if g.area > ENVELOPE_WARN * bld.area:
            warnings.append("envelope not closed: one space covers more than 40% of the building")

    labels = [t for t in sheet.texts if t.kind == "room_label"]
    areas = [t for t in sheet.texts if t.kind == "area"]
    rooms: list[Room] = []
    for g in sorted(inner, key=lambda g: (-g.centroid.y, g.centroid.x)):
        # snap to the stored precision as a whole: rounding each vertex alone can push two nearly
        # touching edges across each other, and a self-intersecting room breaks every area and
        # overlap computed on it downstream
        g = _largest(shapely.set_precision(g.buffer(0), GRID))
        if g is None:
            continue
        poly = [(round(x, 4), round(y, 4)) for x, y in list(g.exterior.coords)[:-1]]
        holes = [[(round(x, 4), round(y, 4)) for x, y in list(h.coords)[:-1]] for h in g.interiors]
        lab = _pick_label(g, labels)
        stated = None
        if lab is not None and lab.value is not None:
            stated = lab.value
        else:
            near = [t for t in areas if g.contains(Point(_centre(t)))]
            if near:
                ref = Point(_centre(lab)) if lab else g.centroid
                stated = min(near, key=lambda t: Point(_centre(t)).distance(ref)).value
        mn, med = width_profile(g)
        ev = {"label_id": lab.id if lab else None, "median_width_m": round(med * mpu, 4)}
        if lab is not None and lab.prov.evidence.get("label_source"):
            ev["label_source"] = lab.prov.evidence["label_source"]
        rooms.append(Room(
            id=ids("room", poly), polygon=poly, holes=holes, label=lab.text if lab else None,
            type=lab.norm if lab else None, stated_area_m2=stated,
            area_m2=round(g.area * mpu * mpu, 4), min_width_m=round(mn * mpu, 4),
            prov=Prov(source="derived", stage="rooms_v1", confidence=1.0 if scale_known else 0.7,
                      evidence=ev),
        ))

    outdoor_labels = [t for t in sheet.texts if t.kind == "room_label" and t.norm == "terrace"]
    edges = _edges(rooms, openings, mpu, outdoor_labels)
    for room in rooms:
        g = Polygon(room.polygon)
        n_doors = sum(1 for e in edges if room.id in (e.a, e.b) and e.kind in ("door", "opening"))
        med = room.prov.evidence["median_width_m"]
        rect = g.minimum_rotated_rectangle
        cs = list(rect.exterior.coords)[:4]
        e0 = np.hypot(cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e1 = np.hypot(cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        aspect = max(e0, e1) / max(min(e0, e1), 1e-9)
        room.is_corridor = bool(room.type == "corridor" or (aspect >= 3 and med <= 1.8 and n_doors >= 2))
        if room.is_corridor and room.type is None:
            room.type = "corridor"
        room.has_window = any(e.kind == "window" and room.id in (e.a, e.b) and "EXTERIOR" in (e.a, e.b) for e in edges)
    return rooms, edges, warnings


def _centre(t: TextItem):
    return ((t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2)


def _pick_label(g: Polygon, labels: list[TextItem]) -> TextItem | None:
    inside = [t for t in labels if g.contains(Point(_centre(t)))]
    if not inside:
        return None
    c = g.centroid
    return min(inside, key=lambda t: Point(_centre(t)).distance(c))


def _edges(rooms: list[Room], openings: list[Element], mpu: float,
           outdoor_labels: list[TextItem] | None = None) -> list[Edge]:
    polys = [Polygon(r.polygon, r.holes) for r in rooms]
    tree = STRtree(polys) if polys else None
    rtype = {r.id: r.type for r in rooms}
    edges: list[Edge] = []

    def room_at(p) -> str | None:
        if tree is None:
            return None
        pt = Point(p)
        for i in tree.query(pt):
            if polys[i].contains(pt):
                return rooms[i].id
        return None

    for o in openings:
        mid = o.attrs.get("mid")
        nrm = o.attrs.get("normal")
        t = o.attrs.get("thickness") or o.thickness
        if mid is None or nrm is None or t is None:
            poly = Polygon(o.geom) if len(o.geom) >= 3 else Polygon()
            mrr = poly.minimum_rotated_rectangle if not poly.is_empty else None
            if mrr is None or mrr.geom_type != "Polygon":
                continue
            mid = (poly.centroid.x, poly.centroid.y)
            cs = list(mrr.exterior.coords)
            e0 = np.subtract(cs[1], cs[0])
            e1 = np.subtract(cs[2], cs[1])
            short = e0 if np.linalg.norm(e0) < np.linalg.norm(e1) else e1
            t = float(np.linalg.norm(short))
            nrm = tuple(short / (t or 1))
        m, n = np.array(mid), np.array(nrm)
        off = t / 2 + PROBE_M / mpu
        ra, rb = room_at(m + n * off), room_at(m - n * off)
        kind = {"door": "door", "window": "window"}.get(o.cls, "opening")
        width = o.attrs.get("width_m")
        prov = Prov(source="derived", stage="room_graph_v1", confidence=o.prov.confidence,
                    evidence={"probe": [tuple(np.round(m + n * off, 4)), tuple(np.round(m - n * off, 4))]})
        o.attrs["rooms"] = [ra, rb]
        if ra and rb and ra != rb:
            edges.append(Edge(a=ra, b=rb, kind=kind, via=o.id, width_m=width, prov=prov))
        elif ra or rb:
            inside = ra or rb
            if kind == "door":
                garage_vehicle = rtype.get(inside) == "garage" and (width or 0) > GARAGE_DOOR_M
                outside = m - n * off if ra else m + n * off
                # a door onto a labelled balcony / terrace / loggia leads to an outdoor annex, not out
                annex = any(np.hypot(*(np.array(_centre(t)) - outside)) <= OUTDOOR_LABEL_M / mpu
                            for t in (outdoor_labels or []))
                target = "EXTERIOR" if garage_vehicle or annex else "EXIT"
            else:
                target = "EXTERIOR"
            edges.append(Edge(a=inside, b=target, kind=kind, via=o.id, width_m=width, prov=prov))
    # adjacency without a door
    linked = {frozenset((e.a, e.b)) for e in edges}
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            key = frozenset((rooms[i].id, rooms[j].id))
            if key in linked:
                continue
            gap = ADJ_GAP_M / mpu
            if polys[i].distance(polys[j]) > gap:
                continue
            shared = polys[i].buffer(gap / 2 + 1e-6).intersection(polys[j].buffer(gap / 2 + 1e-6))
            if shared.is_empty:
                continue
            length = max(shared.minimum_rotated_rectangle.length / 2 - gap, 0)
            if length >= ADJ_SHARED_M / mpu:
                edges.append(Edge(a=rooms[i].id, b=rooms[j].id, kind="adjacent",
                                  prov=Prov(source="derived", stage="room_graph_v1")))
    return edges
