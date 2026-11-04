"""J3 - Traversal checks on the room graph, each with a witness.

- exists_path (C-T1, C-T2): reach EXIT through doors/openings avoiding room
  types; the witness is the shortest path ignoring ``avoid`` and its blockers.
- forbidden_link (C-T3), dead_end_no_window (C-T4), count_exits /
  disjoint_paths (C-C1).
- shortest_path_m (C-T5): travel distance from the farthest point of the room, walked around corners
  inside each room and from door to door (_EscapeField).
- swing_with_escape (C-T6): doors on the escape route open in the direction of travel.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
from shapely.geometry import Polygon

from ..core.geometry import Walkable
from ..rules.schema import Rule
from .context import EXIT, EXTERIOR, Context
from .policy import Raw, compare


def _via_graph(ctx: Context, via: list[str]) -> nx.Graph:
    """Simple graph keeping, per room pair, the edges of allowed kinds (list of element ids)."""
    g = nx.Graph()
    g.add_nodes_from(ctx.graph.nodes(data=True))
    for a, b, d in ctx.graph.edges(data=True):
        if d["kind"] not in via:
            continue
        if g.has_edge(a, b):
            g[a][b]["vias"].append(d.get("via"))
        else:
            g.add_edge(a, b, vias=[d.get("via")], kind=d["kind"])
    return g


def _opening_mid(ctx: Context, eid):
    el = ctx.element(eid) if eid else None
    if el is None:
        return None
    m = el.attrs.get("mid")
    if m is not None:
        return tuple(m)
    c = Polygon(el.geom).centroid
    return (c.x, c.y)


def _path_polyline(ctx: Context, g: nx.Graph, path: list[str]) -> tuple[list, list[str]]:
    pts, doors = [], []
    for i, node in enumerate(path):
        c = ctx.centroid(node)
        if c is not None:
            pts.append(c)
        if i + 1 < len(path):
            vias = g[node][path[i + 1]]["vias"]
            eid = vias[0] if vias else None
            if eid:
                doors.append(eid)
                m = _opening_mid(ctx, eid)
                if m is not None:
                    pts.append(m)
    return pts, doors


def _matches(ctx: Context, node: str, avoid: dict) -> bool:
    r = ctx.room(node)
    if r is None:
        return False
    types = avoid.get("room_type", [])
    return r.type in types


def fn_exists_path(rule: Rule, ctx: Context) -> list[Raw]:
    via = rule.check.via_edges or ["door", "opening"]
    target = rule.check.to or EXIT
    avoid = rule.check.avoid or {}
    g = _via_graph(ctx, via)
    out = []
    for room in ctx.rooms_for(rule.applies_to):
        blocked = {n for n in g.nodes if n != room.id and _matches(ctx, n, avoid)}
        h = g.subgraph([n for n in g.nodes if n not in blocked])
        ok = target in h and nx.has_path(h, room.id, target)
        vars_ = {"room": {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}}
        if ok:
            path = nx.shortest_path(h, room.id, target)
            pts, doors = _path_polyline(ctx, g, path)
            out.append(Raw([room.id], False, deciding_ids=doors, vars=vars_,
                           detected="reachable", required=f"path to {target}",
                           evidence={"polylines": [pts], "path": path}))
            continue
        if nx.has_path(g, room.id, target):
            path = nx.shortest_path(g, room.id, target)
            blockers = [n for n in path[1:] if n in blocked]
            pts, doors = _path_polyline(ctx, g, path)
            names = ", ".join(ctx.name(b) for b in blockers)
            vars_["witness"] = {"blocking": names, "__str__": names}
            ev = {"polylines": [pts], "path": path, "blocking": blockers,
                  "polygons": [ctx.room(b).polygon for b in blockers if ctx.room(b)],
                  "labels": [{"at": ctx.centroid(b), "text": "blocks"} for b in blockers]}
            out.append(Raw([room.id] + blockers, True, deciding_ids=doors, vars=vars_,
                           detected=f"only via {names}", required=f"path to {target} avoiding {avoid.get('room_type')}",
                           evidence=ev))
        else:
            reach = sorted(nx.node_connected_component(g, room.id))
            vars_["witness"] = {"blocking": "no connection at all", "__str__": "no connection"}
            ev = {"reachable": reach, "polygons": [ctx.room(n).polygon for n in reach if ctx.room(n)]}
            # deciding elements: every door of the reachable set (one may be missing)
            doors = [d.get("via") for a, b, d in ctx.graph.edges(data=True)
                     if (a in reach or b in reach) and d.get("via")]
            out.append(Raw([room.id], True, deciding_ids=doors, vars=vars_, detected="no route",
                           required=f"path to {target}", evidence=ev))
    return out


def fn_forbidden_link(rule: Rule, ctx: Context) -> list[Raw]:
    pairs = [frozenset(p) for p in rule.check.model_extra.get("pairs", [])]
    via = rule.check.via_edges or ["door", "opening"]
    out = []
    hits = set()
    for a, b, d in ctx.graph.edges(data=True):
        if d["kind"] not in via:
            continue
        ra, rb = ctx.room(a), ctx.room(b)
        if not ra or not rb:
            continue
        if frozenset((ra.type, rb.type)) in pairs:
            hits.add((a, b))
            m = _opening_mid(ctx, d.get("via"))
            el = ctx.element(d.get("via")) if d.get("via") else None
            out.append(Raw([a, b], True, deciding_ids=[d["via"]] if d.get("via") else [],
                           vars={"room": {"label": ctx.name(a), "__str__": ctx.name(a)},
                                 "other": {"label": ctx.name(b), "__str__": ctx.name(b)}},
                           detected=f"{d['kind']} {ra.type}-{rb.type}", required="no direct link",
                           evidence={"points": [m] if m else [], "polygons": [el.geom] if el else []}))
    if not out:
        out.append(Raw([], False, detected="none", required="no forbidden link"))
    return out


def fn_dead_end_no_window(rule: Rule, ctx: Context) -> list[Raw]:
    out = []
    for room in ctx.rooms_for(rule.applies_to):
        links = [(o, d) for _, o, d in ctx.graph.edges(room.id, data=True)
                 if d["kind"] in ("door", "opening") and o != EXTERIOR]
        dead = len(links) == 1 and room.has_window is False
        vars_ = {"room": {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}}
        out.append(Raw([room.id], dead, deciding_ids=[d["via"] for _, d in links if d.get("via")],
                       vars=vars_, detected=f"{len(links)} door(s), window: {room.has_window}",
                       required="second exit or a window",
                       evidence={"polygons": [room.polygon]} if dead else {}))
    return out


def fn_count_exits(rule: Rule, ctx: Context) -> list[Raw]:
    exits = [d for a, b, d in ctx.graph.edges(data=True) if EXIT in (a, b)]
    n = len(exits)
    violated, beyond = compare(n, rule.check.op or ">=", float(rule.check.value or 1), 0)
    pts = [p for p in (_opening_mid(ctx, d.get("via")) for d in exits) if p]
    return [Raw([d["via"] for d in exits if d.get("via")], violated, beyond_band=beyond,
                deciding_ids=[d["via"] for d in exits if d.get("via")],
                detected=str(n), required=f"{rule.check.op} {rule.check.value}", evidence={"points": pts})]


def fn_disjoint_paths(rule: Rule, ctx: Context) -> list[Raw]:
    via = rule.check.via_edges or ["door", "opening"]
    g = _via_graph(ctx, via)
    exits = [(a if b == EXIT else b, d) for a, b, d in ctx.graph.edges(data=True) if EXIT in (a, b)]
    h = nx.Graph(g.subgraph([n for n in g.nodes if n not in (EXIT, EXTERIOR)]))
    h.add_node("SINK")
    for i, (room, d) in enumerate(exits):
        node = f"EXIT:{d.get('via') or i}"
        h.add_edge(room, node)
        h.add_edge(node, "SINK")
    out = []
    for room in ctx.rooms_for(rule.applies_to):
        try:
            paths = list(nx.node_disjoint_paths(h, room.id, "SINK")) if nx.has_path(h, room.id, "SINK") else []
        except nx.NetworkXNoPath:
            paths = []
        n = len(paths)
        violated, beyond = compare(n, rule.check.op or ">=", float(rule.check.value or 1), 0)
        out.append(Raw([room.id], violated, beyond_band=beyond, detected=str(n),
                       required=f"{rule.check.op} {rule.check.value}",
                       vars={"room": {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}}))
    return out


class _EscapeField:
    """Walking distance from every door to the nearest exit door.

    A route goes from door to door through the rooms they connect, walked inside each room
    (around its corners); an exit door is at distance 0. ``nxt[d]`` is the door taken after ``d``
    (EXIT when ``d`` is an exit door) and ``into[d]`` the room entered through ``d`` on the way out
    (None: outside)."""

    def __init__(self, ctx: Context, via: list[str]):
        self.ctx = ctx
        self.walk: dict[str, Walkable] = {}
        self.sides: dict[str, tuple[str, str]] = {}
        self.doors_of: dict[str, list[str]] = {}
        exits = set()
        for a, b, d in ctx.graph.edges(data=True):
            eid = d.get("via")
            if d["kind"] not in via or not eid or _opening_mid(ctx, eid) is None:
                continue
            self.sides[eid] = (a, b)
            for r in (a, b):
                if ctx.room(r) is not None:
                    self.doors_of.setdefault(r, []).append(eid)
            if EXIT in (a, b):
                exits.add(eid)
        h = nx.Graph()
        h.add_nodes_from(self.sides)
        for r, doors in self.doors_of.items():
            w = self.walkable(r)
            for k, d1 in enumerate(doors):
                for d2 in doors[k + 1:]:
                    dist = w.distance(self.entry(d1, r), self.entry(d2, r))
                    if np.isfinite(dist):
                        h.add_edge(d1, d2, weight=dist)
        for e in exits:
            h.add_edge(e, EXIT, weight=0.0)
        self.dist, paths = nx.single_source_dijkstra(h, EXIT) if EXIT in h else ({}, {})
        self.nxt = {d: p[-2] for d, p in paths.items() if d != EXIT}
        self.into = {}
        for d, n in self.nxt.items():
            a, b = self.sides[d]
            if n == EXIT:
                self.into[d] = None
            else:
                na, nb = self.sides[n]
                self.into[d] = a if a in (na, nb) else b

    def walkable(self, room_id: str) -> Walkable:
        if room_id not in self.walk:
            r = self.ctx.room(room_id)
            self.walk[room_id] = Walkable(Polygon(r.polygon, r.holes))
        return self.walk[room_id]

    def entry(self, door: str, room_id: str):
        return self.walkable(room_id).entry(_opening_mid(self.ctx, door))

    def farthest(self, room_id: str):
        """(travel distance from the room's farthest corner, that corner, the door taken) or None."""
        doors = [d for d in self.doors_of.get(room_id, []) if d in self.dist]
        if not doors:
            return None
        w = self.walkable(room_id)
        best = {}
        for d in doors:
            for c, dc in w.from_point(self.entry(d, room_id)).items():
                v = dc + self.dist[d]
                if c in w.corners and (c not in best or v < best[c][0]):
                    best[c] = (v, d)
        if not best:
            return None
        c = max(best, key=lambda k: best[k][0])
        return best[c][0], c, best[c][1]

    def route(self, door: str) -> list[str]:
        out = [door]
        while out[-1] in self.nxt and self.nxt[out[-1]] != EXIT:
            out.append(self.nxt[out[-1]])
        return out


def fn_shortest_path_m(rule: Rule, ctx: Context) -> list[Raw]:
    field = _EscapeField(ctx, rule.check.via_edges or ["door", "opening"])
    mpu = ctx.mpu
    out = []
    for room in ctx.rooms_for(rule.applies_to):
        far = field.farthest(room.id)
        if far is None:
            out.append(Raw([room.id], None, note="no route to an exit"))
            continue
        dist_u, corner, door = far
        dist = dist_u * mpu
        limit = float(rule.check.value)
        tol = max(0.01 * limit, 0.10)
        violated, beyond = compare(dist, rule.check.op or "<=", limit, tol)
        doors = field.route(door)
        pts = [corner] + [_opening_mid(ctx, d) for d in doors]
        out.append(Raw([room.id], violated, beyond_band=beyond, metric=True, deciding_ids=doors,
                       detected=f"{dist:.2f} m", required=f"{rule.check.op} {limit:.2f} m",
                       vars={"room": {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}},
                       evidence={"polylines": [pts], "points": [corner]},
                       note="walked from the farthest corner of the room, around corners, door to door"))
    return out


def fn_swing_with_escape(rule: Rule, ctx: Context) -> list[Raw]:
    """Doors open in the direction of escape: the drawn swing lies on the side the route goes to.
    ``doors: exit`` checks exit doors; ``doors: route`` every door on the escape routes of the rooms
    the rule applies to."""
    field = _EscapeField(ctx, rule.check.via_edges or ["door", "opening"])
    scope = rule.check.model_extra.get("doors", "exit")
    if scope == "route":
        doors = []
        for room in ctx.rooms_for(rule.applies_to):
            far = field.farthest(room.id)
            if far is not None:
                doors += [d for d in field.route(far[2]) if d not in doors]
    else:
        doors = [d for d, n in field.nxt.items() if n == EXIT]
    out = []
    for d in doors:
        el = ctx.element(d)
        if el is None or el.cls != "door":
            continue
        name = {"label": el.tag or d, "__str__": el.tag or d}
        swing = el.attrs.get("swing_polygon")
        if not swing or len(swing) < 3:
            out.append(Raw([d], None, vars={"door": name}, note="door swing not drawn or not recognised"))
            continue
        sp = Polygon(swing).buffer(0)
        a, b = field.sides[d]
        area = {s: sp.intersection(Polygon(ctx.room(s).polygon)).area if ctx.room(s) else None for s in (a, b)}
        known = sum(v for v in area.values() if v is not None)
        area = {s: (v if v is not None else max(sp.area - known, 0.0)) for s, v in area.items()}
        opens = max(area, key=area.get)
        target = field.into[d]
        target_side = target if target is not None else next(s for s in (a, b) if ctx.room(s) is None)
        violated = opens != target_side

        def label(s):
            return ctx.name(s) if ctx.room(s) else "outside"

        out.append(Raw([d], violated, deciding_ids=[d], vars={"door": name},
                       detected=f"opens into {label(opens)}", required=f"opens toward {label(target_side)}",
                       evidence={"polygons": [list(sp.exterior.coords)[:-1]],
                                 "points": [_opening_mid(ctx, d)]}))
    if not out:
        out.append(Raw([], None, note="no door on an escape route"))
    return out


def fn_isolated_rooms(rule: Rule, ctx: Context) -> list[Raw]:
    """P-6: every enclosed room is reachable: it has at least one door or opening."""
    via = set(rule.check.via_edges or ["door", "opening"])
    out = []
    for room in ctx.rooms_for(rule.applies_to):
        n = sum(1 for _a, _b, d in ctx.graph.edges(room.id, data=True) if d["kind"] in via)
        name = {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}
        out.append(Raw([room.id], n == 0, detected=f"{n} door(s) or opening(s)", required=">= 1",
                       vars={"room": name}, evidence={"polygons": [room.polygon]} if n == 0 else {}))
    return out
