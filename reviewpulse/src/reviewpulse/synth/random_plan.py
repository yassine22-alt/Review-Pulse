"""Randomised synthetic plans for testing generality (perception stages R2-R10).

Unlike ``make_plan`` (one layout family with planted rule violations), every
plan here draws its own:
- footprint (rectangle or L shape) and room subdivision (recursive splits),
- wall thicknesses (exterior 0.20-0.40 m, interior 0.07-0.20 m),
- rotation angle of the whole plan (any angle),
- units (m or mm) and PDF scale (1:50, 1:100, 1:200),
- layer naming scheme (AIA, French, numeric, everything on layer 0),
- wall drawing style (outlines, closed polylines, outlines + hatch, fill only),
- door style (arc + leaf, arc only, bulge polyline, block INSERT, arc as line
  segments, double doors) and doorless pass-throughs,
- room label wording (French/English variants, abbreviations).
Ground truth (walls, openings, rooms, room graph) is exact.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

LAYER_SCHEMES = {
    "aia": {"wall": "A-WALL", "door": "A-DOOR", "glaz": "A-GLAZ", "text": "A-ANNO-TEXT", "dims": "A-ANNO-DIMS",
            "furn": "A-FURN", "hatch": "A-WALL-PATT"},
    "fr": {"wall": "MURS", "door": "MENUISERIES", "glaz": "MENUISERIES", "text": "TEXTES", "dims": "COTATIONS",
           "furn": "MOBILIER", "hatch": "HACHURES"},
    "numeric": {"wall": "1", "door": "2", "glaz": "3", "text": "4", "dims": "5", "furn": "6", "hatch": "7"},
    "none": {k: "0" for k in ("wall", "door", "glaz", "text", "dims", "furn", "hatch")},
}
WALL_STYLES = ["lines", "polylines", "hatched", "filled"]
DOOR_STYLES = ["arc_leaf", "arc_only", "bulge", "block", "segments"]
LABELS = {
    "bedroom": ["CHAMBRE", "Ch.", "Chambre", "BEDROOM", "Bedroom"],
    "living": ["SEJOUR", "Séjour", "SALON", "LIVING ROOM"],
    "kitchen": ["CUISINE", "Cuisine", "KITCHEN"],
    "bathroom": ["SDB", "S.D.B", "Salle de bain", "BATHROOM", "Salle d'eau"],
    "wc": ["WC", "W.C.", "Toilettes"],
    "corridor": ["DEGAGEMENT", "Dgt", "HALL", "Couloir", "CORRIDOR"],
    "storage": ["RANGEMENT", "Cellier", "STORAGE"],
    "office": ["BUREAU", "OFFICE"],
}


@dataclass
class RDrawing:
    lines: list = field(default_factory=list)      # (role, a, b)
    arcs: list = field(default_factory=list)       # (role, c, r, a0, a1, style)
    polys: list = field(default_factory=list)      # (role, pts, filled)
    plines: list = field(default_factory=list)     # (role, pts, closed)  -- LWPOLYLINE outlines
    texts: list = field(default_factory=list)      # (role, text, (x, y), h, rot)
    blocks: list = field(default_factory=list)     # (hinge, closed angle, open angle, radius)


# ---------------------------------------------------------------------------
# Layout

def _split(rect, rnd, min_side, max_area, depth=0):
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    if (w * h <= max_area and depth > 0 and rnd.random() < 0.6) or (w < 2 * min_side and h < 2 * min_side):
        return [rect]
    vertical = w >= h if abs(w - h) > 0.5 else rnd.random() < 0.5
    if vertical and w >= 2 * min_side:
        c = round(rnd.uniform(x0 + min_side, x1 - min_side), 2)
        return _split((x0, y0, c, y1), rnd, min_side, max_area, depth + 1) + \
            _split((c, y0, x1, y1), rnd, min_side, max_area, depth + 1)
    if h >= 2 * min_side:
        c = round(rnd.uniform(y0 + min_side, y1 - min_side), 2)
        return _split((x0, y0, x1, c), rnd, min_side, max_area, depth + 1) + \
            _split((x0, c, x1, y1), rnd, min_side, max_area, depth + 1)
    return [rect]


def _assign_types(rooms, rnd):
    order = sorted(range(len(rooms)), key=lambda i: -_area(rooms[i]))
    types = {}
    types[order[0]] = "living"
    rest = order[1:]
    small = sorted(rest, key=lambda i: _area(rooms[i]))
    pool = ["bathroom", "wc", "storage"]
    for i in small[:min(len(pool), max(0, len(small) - 2))]:
        types[i] = pool.pop(0)
    big_rest = [i for i in rest if i not in types]
    if big_rest:
        types[big_rest[-1]] = "kitchen"
    for i in big_rest[:-1]:
        types[i] = rnd.choice(["bedroom", "bedroom", "office"])
    for i in range(len(rooms)):
        types.setdefault(i, "bedroom")
    for i, r in enumerate(rooms):
        w, h = r[2] - r[0], r[3] - r[1]
        if min(w, h) <= 1.6 and max(w, h) / max(min(w, h), 1e-9) >= 2.5:
            types[i] = "corridor"
    return types


def _area(r):
    return (r[2] - r[0]) * (r[3] - r[1])


def _segments(rooms, footprint):
    """Elementary wall segments (local frame, axis aligned) with the rooms on each side."""
    xs = sorted({r[0] for r in rooms} | {r[2] for r in rooms})
    ys = sorted({r[1] for r in rooms} | {r[3] for r in rooms})

    def room_at(p):
        for i, r in enumerate(rooms):
            if r[0] < p[0] < r[2] and r[1] < p[1] < r[3]:
                return i
        return None

    segs = {}
    eps = 1e-3
    for y in ys:
        for x0, x1 in zip(xs, xs[1:]):
            m = ((x0 + x1) / 2, y)
            a, b = room_at((m[0], y - eps)), room_at((m[0], y + eps))
            if a != b:
                segs[("h", x0, y)] = dict(p=(x0, y), q=(x1, y), o="h", rooms=(a, b))
    for x in xs:
        for y0, y1 in zip(ys, ys[1:]):
            m = (x, (y0 + y1) / 2)
            a, b = room_at((x - eps, m[1])), room_at((x + eps, m[1]))
            if a != b:
                segs[("v", x, y0)] = dict(p=(x, y0), q=(x, y1), o="v", rooms=(a, b))
    return segs


def _merge_runs(segs):
    """Join consecutive elementary segments that separate the same two rooms (one wall)."""
    by = {}
    for s in segs.values():
        key = (s["o"], s["p"][1] if s["o"] == "h" else s["p"][0], frozenset(s["rooms"]))
        by.setdefault(key, []).append(s)
    walls = []
    for (o, _c, _rooms), ss in by.items():
        ss.sort(key=lambda s: s["p"][0] if o == "h" else s["p"][1])
        cur = dict(ss[0])
        for s in ss[1:]:
            if s["p"] == cur["q"]:
                cur["q"] = s["q"]
            else:
                walls.append(cur)
                cur = dict(s)
        walls.append(cur)
    return walls


def _len(s):
    return math.dist(s["p"], s["q"])


# ---------------------------------------------------------------------------
def random_plan(out_dir: str | Path, seed: int = 0, png: bool = False, name: str | None = None,
                **force) -> dict:
    rnd = random.Random(seed)
    cfg = dict(
        scheme=rnd.choice(list(LAYER_SCHEMES)), wall_style=rnd.choice(WALL_STYLES),
        door_style=rnd.choice(DOOR_STYLES), units=rnd.choice(["m", "mm"]), denominator=rnd.choice([50, 100, 200]),
        angle=rnd.choice([0.0, 0.0, 90.0, round(rnd.uniform(-45, 45), 1)]),
        t_ext=round(rnd.uniform(0.20, 0.40), 2), t_int=round(rnd.uniform(0.07, 0.20), 2),
        L_shape=rnd.random() < 0.35)
    cfg["clutter"] = random.Random(seed + 104729).random() < 0.7   # own stream: layouts stay seed-stable
    cfg.update(force)
    name = name or f"rand_{seed:04d}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    W, H = round(rnd.uniform(8, 15), 2), round(rnd.uniform(7, 12), 2)
    base = [(0.0, 0.0, W, H)]
    rects = _split(base[0], rnd, 2.4, 22.0)
    footprint = box(0, 0, W, H)
    if cfg["L_shape"] and len(rects) > 3:
        # drop rooms in one corner to make an L
        cx, cy = rnd.choice([(0, 0), (W, 0), (0, H), (W, H)])
        corner = min(rects, key=lambda r: Point(cx, cy).distance(box(*r)))
        if _area(corner) < 0.35 * W * H:
            rects.remove(corner)
            footprint = footprint.difference(box(*corner))
    types = _assign_types(rects, rnd)
    segs = _segments(rects, footprint)
    walls = _merge_runs(segs)
    for w in walls:
        w["ext"] = None in w["rooms"]
        w["t"] = cfg["t_ext"] if w["ext"] else cfg["t_int"]

    # junction extension (half the thickest perpendicular wall at each end)
    node: dict[tuple, dict] = {}
    for w in walls:
        for pt in (w["p"], w["q"]):
            node.setdefault(pt, {"h": 0.0, "v": 0.0})
        # walls passing through a node also count (T junctions)
    for w in walls:
        for pt, d in node.items():
            if LineString([w["p"], w["q"]]).distance(Point(pt)) < 1e-6:
                d[w["o"]] = max(d[w["o"]], w["t"])

    def ext(w, pt):
        return node[pt]["v" if w["o"] == "h" else "h"] / 2

    rects_geo = []
    for w in walls:
        u = _unit(w)
        a = (w["p"][0] - u[0] * ext(w, w["p"]), w["p"][1] - u[1] * ext(w, w["p"]))
        b = (w["q"][0] + u[0] * ext(w, w["q"]), w["q"][1] + u[1] * ext(w, w["q"]))
        rects_geo.append(LineString([a, b]).buffer(w["t"] / 2, cap_style="flat", join_style="mitre"))
    solid = unary_union(rects_geo)

    # ---- openings: spanning tree of doors + a few extra, exits, windows, pass-throughs --------
    adj = {}
    for wi, w in enumerate(walls):
        a, b = w["rooms"]
        if a is not None and b is not None and _len(w) >= 1.3:
            adj.setdefault(frozenset((a, b)), []).append(wi)
    living = next(i for i, t in types.items() if t == "living")
    seen, frontier, tree_edges = {living}, [living], []
    pairs = list(adj)
    rnd.shuffle(pairs)
    while frontier:
        cur = frontier.pop(0)
        for pr in pairs:
            if cur in pr:
                other = next(iter(pr - {cur}))
                if other not in seen:
                    seen.add(other)
                    frontier.append(other)
                    tree_edges.append(pr)
    extra = [p for p in pairs if p not in tree_edges and rnd.random() < 0.25]
    openings = []
    used_walls: dict[int, list] = {}

    def place(wi, width):
        w = walls[wi]
        L = _len(w)
        margin = 0.25 + w["t"]
        if L < width + 2 * margin:
            return None
        for _ in range(20):
            c = rnd.uniform(margin + width / 2, L - margin - width / 2)
            if all(abs(c - c2) > (width + w2) / 2 + 0.4 for c2, w2 in used_walls.get(wi, [])):
                used_walls.setdefault(wi, []).append((c, width))
                return c
        return None

    for pr in tree_edges + extra:
        wi = max(adj[pr], key=lambda i: _len(walls[i]))
        a, b = sorted(pr)
        pass_through = types[a] in ("living", "corridor") and types[b] in ("living", "corridor", "kitchen") \
            and rnd.random() < 0.3
        double = not pass_through and rnd.random() < 0.12 and _len(walls[wi]) > 2.6
        width = round(rnd.uniform(0.9, 1.6), 2) if pass_through else \
            round(rnd.uniform(1.3, 1.6), 2) if double else round(rnd.uniform(0.70, 0.95), 2)
        c = place(wi, width)
        if c is None and not pass_through:
            width = 0.70
            c = place(wi, width)
        if c is None:
            continue
        kind = "opening" if pass_through else "door"
        openings.append(dict(kind=kind, wall=wi, c=c, width=width, rooms=(a, b), double=double,
                             swing=rnd.choice([a, b])))
    # exits: one or two exterior doors from living / corridor / kitchen
    ext_walls = [i for i, w in enumerate(walls) if w["ext"] and _len(w) >= 1.6]
    for target in [living] + [i for i, t in types.items() if t in ("corridor", "kitchen") and rnd.random() < 0.3]:
        cands = [i for i in ext_walls if target in walls[i]["rooms"]]
        if cands:
            wi = rnd.choice(cands)
            width = round(rnd.uniform(0.85, 1.0), 2)
            c = place(wi, width)
            if c is not None:
                openings.append(dict(kind="door", wall=wi, c=c, width=width, rooms=(target, "EXIT"), double=False,
                                     swing=target))
    for i, t in types.items():
        if t in ("corridor", "storage") or rnd.random() < 0.1:
            continue
        cands = [wi for wi in ext_walls if i in walls[wi]["rooms"]]
        if not cands:
            continue
        wi = rnd.choice(cands)
        width = round(rnd.uniform(0.6, min(1.8, _len(walls[wi]) - 1.2)), 2) if _len(walls[wi]) > 1.9 else None
        if width is None:
            continue
        c = place(wi, width)
        if c is not None:
            openings.append(dict(kind="window", wall=wi, c=c, width=width, rooms=(i, "EXTERIOR"), double=False))

    dr = RDrawing()
    cuts = []
    open_truth = []
    for o in openings:
        w = walls[o["wall"]]
        u = _unit(w)
        n = (-u[1], u[0])
        s0, s1 = o["c"] - o["width"] / 2, o["c"] + o["width"] / 2

        def at(s, off=0.0, w=w, u=u, n=n):
            return (w["p"][0] + u[0] * s + n[0] * off, w["p"][1] + u[1] * s + n[1] * off)

        cuts.append(Polygon([at(s0, -w["t"] / 2 - 0.01), at(s1, -w["t"] / 2 - 0.01),
                             at(s1, w["t"] / 2 + 0.01), at(s0, w["t"] / 2 + 0.01)]))
        foot = [at(s0, -w["t"] / 2), at(s1, -w["t"] / 2), at(s1, w["t"] / 2), at(s0, w["t"] / 2)]
        open_truth.append(dict(cls="opening" if o["kind"] == "opening" else o["kind"], polygon=foot,
                               width_m=o["width"], rooms=list(o["rooms"]), double=o["double"], midpoint=at(o["c"])))
        if o["kind"] == "window":
            for off in (-w["t"] / 2, 0.0, w["t"] / 2):
                dr.lines.append(("glaz", at(s0, off), at(s1, off)))
        elif o["kind"] == "door":
            room = o["swing"] if o["swing"] != "EXIT" else o["rooms"][0]
            rc = Point(_centre(rects[room]))
            mid = at(o["c"])
            sgn = 1 if (rc.x - mid[0]) * n[0] + (rc.y - mid[1]) * n[1] > 0 else -1
            leaves = [(s0, s1)] if not o["double"] else [(s0, o["c"]), (s1, o["c"])]
            for hs, cs in leaves:
                r = abs(cs - hs)
                hinge = at(hs, sgn * w["t"] / 2)
                closed = at(cs, sgn * w["t"] / 2)
                open_end = (hinge[0] + sgn * n[0] * r, hinge[1] + sgn * n[1] * r)
                ac = math.degrees(math.atan2(closed[1] - hinge[1], closed[0] - hinge[0])) % 360
                ao = math.degrees(math.atan2(open_end[1] - hinge[1], open_end[0] - hinge[0])) % 360
                a0, a1 = (ac, ao) if abs((ao - ac) % 360 - 90) < 1e-6 else (ao, ac)
                style = cfg["door_style"]
                if style == "block":
                    dr.blocks.append((hinge, ac, ao, r))
                else:
                    dr.arcs.append(("door", hinge, r, a0, a1, style))
                    if style != "arc_only":
                        dr.lines.append(("door", hinge, open_end))

    walls_cut = solid.difference(unary_union(cuts)) if cuts else solid
    style = cfg["wall_style"]
    for g in getattr(walls_cut, "geoms", [walls_cut]):
        rings = [list(g.exterior.coords)] + [list(i.coords) for i in g.interiors]
        if style in ("lines", "hatched"):
            for cs in rings:
                for a, b in zip(cs, cs[1:]):
                    dr.lines.append(("wall", a, b))
        elif style == "polylines":
            for cs in rings:
                dr.plines.append(("wall", cs[:-1], True))
        if style in ("hatched", "filled"):
            dr.polys.append(("hatch" if style == "hatched" else "wall", [list(r) for r in rings], True))

    # ---- rooms truth, labels, dimensions -------------------------------------------------
    rooms_truth = []
    for i, r in enumerate(rects):
        net = box(*r).difference(solid)
        if net.geom_type == "MultiPolygon":
            net = max(net.geoms, key=lambda g: g.area)
        rooms_truth.append(dict(id=f"r{i}", type=types[i], polygon=list(net.exterior.coords)[:-1],
                                area_m2=round(net.area, 4)))
        label = rnd.choice(LABELS.get(types[i], ["PIECE"]))
        if types[i] == "bedroom" and rnd.random() < 0.6:
            label += f" {sum(1 for j in range(i + 1) if types[j] == 'bedroom')}"
        rooms_truth[-1]["label"] = label
        c = net.representative_point()
        dr.texts.append(("text", label, (c.x, c.y), 0.22, 0.0))
        if rnd.random() < 0.7:
            dr.texts.append(("text", f"{net.area:.2f}".replace(".", ",") + " m²", (c.x, c.y - 0.38), 0.16, 0.0))

    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    dims = []
    yb = -cfg["t_ext"] / 2
    for x0, x1 in zip(xs, xs[1:]):
        dims.append(dict(p1=(x0, yb), p2=(x1, yb), base=-1.0, measured=x1 - x0))
    dims.append(dict(p1=(xs[0], yb), p2=(xs[-1], yb), base=-1.8, measured=xs[-1] - xs[0], overall=True))
    for d in dims:
        _dim_draw(dr, d)

    if cfg["clutter"]:
        _clutter(dr, rooms_truth, open_truth, walls_cut, cfg, random.Random(seed * 7919 + 13))

    # ---- rotate everything about the origin ----------------------------------------------
    ang = cfg["angle"]

    def R(p):
        q = affinity.rotate(Point(p), ang, origin=(0, 0))
        return (round(q.x, 6), round(q.y, 6))

    dr.lines = [(r, R(a), R(b)) for r, a, b in dr.lines]
    dr.arcs = [(r, R(c), rr, (a0 + ang) % 360, (a1 + ang) % 360, st) for r, c, rr, a0, a1, st in dr.arcs]
    dr.polys = [(r, [[R(p) for p in ring] for ring in rings], f) for r, rings, f in dr.polys]
    dr.plines = [(r, [R(p) for p in pts], c) for r, pts, c in dr.plines]
    rotated = []
    for r, t, p, h, rot in dr.texts:
        if r == "text" and t.endswith("m²") and rotated and rotated[-1][0] == "text":
            # the area line stays just under its label on the page, whatever the plan rotation
            lp = rotated[-1][2]
            rotated.append((r, t, (lp[0], lp[1] - 0.38), h, rot))
            continue
        rotated.append((r, t, R(p), h, (rot + ang) % 360 if r == "dims" else rot))
    dr.texts = rotated
    dr.blocks = [(R(h), (ac + ang) % 360, (ao + ang) % 360, r) for h, ac, ao, r in dr.blocks]

    truth = dict(
        name=name, seed=seed, config=cfg, units="m",
        walls=[dict(centreline=[R(a), R(b)], thickness=w["t"], exterior=w["ext"])
               for wi, w in enumerate(walls) for a, b in _solid_pieces(w, [o for o in openings if o["wall"] == wi])],
        openings=[dict(o, polygon=[R(p) for p in o["polygon"]], midpoint=R(o["midpoint"])) for o in open_truth],
        rooms=[dict(r, polygon=[R(p) for p in r["polygon"]]) for r in rooms_truth],
        edges=[dict(a=f"r{o['rooms'][0]}", b=_node(o["rooms"][1]), kind=o["kind"]) for o in openings],
    )
    unit_k = 1000.0 if cfg["units"] == "mm" else 1.0
    paths = dict(truth=out_dir / f"{name}.truth.json", dxf=out_dir / f"{name}.dxf", pdf=out_dir / f"{name}.pdf")
    _write_dxf(dr, paths["dxf"], cfg, unit_k)
    truth["pdf_transform"] = _write_pdf(dr, paths["pdf"], cfg)
    truth["dxf_unit_m"] = 1.0 / unit_k
    paths["truth"].write_text(json.dumps(truth, indent=1), encoding="utf-8")
    if png:
        from .make_plan import _write_png

        paths["png"] = out_dir / f"{name}.png"
        _write_png(paths["pdf"], paths["png"])
    return {k: str(v) for k, v in paths.items()}


def _solid_pieces(w, ops):
    """Centreline intervals of a wall where material exists (between openings)."""
    u = _unit(w)
    L = _len(w)
    cuts = sorted((o["c"] - o["width"] / 2, o["c"] + o["width"] / 2) for o in ops)
    pieces, s = [], 0.0
    for a, b in cuts:
        if a > s:
            pieces.append((s, a))
        s = max(s, b)
    if s < L:
        pieces.append((s, L))
    p = w["p"]
    return [((p[0] + u[0] * a, p[1] + u[1] * a), (p[0] + u[0] * b, p[1] + u[1] * b)) for a, b in pieces if b - a > 1e-6]


def _circle(c, r, n=24):
    return [(c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


class _Placer:
    """Places furniture inside one room, against its walls, clear of door swings and windows."""

    SIDES = ("bottom", "top", "left", "right")

    def __init__(self, room: Polygon, keep_clear, rnd: random.Random):
        self.room = room
        self.keep_clear = keep_clear
        self.bounds = room.bounds
        self.sides = list(self.SIDES)
        rnd.shuffle(self.sides)

    def fits(self, pts) -> bool:
        poly = Polygon(pts)
        return poly.within(self.room.buffer(1e-6)) and not poly.intersects(self.keep_clear)

    def along(self, depth: float, length: float, offset: float = 0.0, side: str | None = None):
        """Rectangle against one wall face (depth into the room), never longer than that wall;
        without ``side``, the first wall (random order) where it fits."""
        x0, y0, x1, y1 = self.bounds
        if side is None:
            side = next((s for s in self.sides if self.fits(self.along(depth, length, offset, s))), self.sides[0])
        wall_len = (x1 - x0) if side in ("bottom", "top") else (y1 - y0)
        length = max(0.1, min(length, wall_len - offset - 0.05))
        if side == "bottom":
            return _rect(x0 + offset, y0, x0 + offset + length, y0 + depth)
        if side == "top":
            return _rect(x0 + offset, y1 - depth, x0 + offset + length, y1)
        if side == "left":
            return _rect(x0, y0 + offset, x0 + depth, y0 + offset + length)
        return _rect(x1 - depth, y0 + offset, x1, y0 + offset + length)


def _clutter(dr: RDrawing, rooms: list[dict], openings: list[dict], walls_body, cfg: dict, rnd: random.Random) -> None:
    """Real-world clutter, all in the local (unrotated) frame, nothing touching door swings or windows:
    furniture against walls (counters and wardrobes 0.6 m deep: their front line is a classic false wall),
    sanitary fixtures with curves, exploded hatch patterns inside walls, a sheet frame and grid axes."""
    # doors need their swing (one leaf width) clear; windows and pass-throughs only their recess
    keep_clear = unary_union([Polygon(o["polygon"]).buffer(o["width_m"] if o["cls"] == "door" else 0.1)
                              for o in openings])

    def lines(seglist, role="furn"):
        for a, b in seglist:
            dr.lines.append((role, a, b))

    for room in rooms:
        pl = _Placer(Polygon(room["polygon"]), keep_clear, rnd)   # furniture stays inside its room
        x0, y0, x1, y1 = pl.bounds
        w, h = x1 - x0, y1 - y0
        t = room["type"]
        along = pl.along

        def put(pts, role="furn", closed=True, pl=pl):
            if not pl.fits(pts):
                return False
            dr.plines.append((role, pts, closed))
            return True

        span = max(w, h)
        if t == "kitchen" and span > 2.0:
            counter = along(0.6, span - 0.2, 0.1)
            if put(counter):
                cx = sum(p[0] for p in counter) / 4
                cy = sum(p[1] for p in counter) / 4
                for dx in (-0.35, 0.35):                       # hob rings
                    dr.plines.append(("furn", _circle((cx + dx, cy), 0.09), True))
                dr.plines.append(("furn", _rect(cx - 1.2, cy - 0.2, cx - 0.7, cy + 0.2), True))   # sink
        elif t in ("bedroom", "office") and span > 2.4:
            put(along(0.6, min(2.0, span - 0.6), 0.3))      # wardrobe
            bx, by = x0 + w / 2 - 0.7, y0 + h / 2 - 1.0
            bed = _rect(bx, by, bx + 1.4, by + 2.0)
            if put(bed):
                lines([((bx, by + 1.6), (bx + 1.4, by + 1.6))])                       # pillow line
                dr.plines.append(("furn", _rect(bx + 0.1, by + 1.65, bx + 0.65, by + 1.95), True))
        elif t == "living" and span > 2.6:
            sofa = along(0.9, 2.2, 0.4)
            if put(sofa):
                xs_ = [p[0] for p in sofa]
                ys_ = [p[1] for p in sofa]
                dr.plines.append(("furn", _rect(min(xs_) + 0.15, min(ys_) + 0.15, max(xs_) - 0.15, max(ys_) - 0.15), True))
            put(_circle((x0 + w / 2, y0 + h / 2), 0.55))    # round table
        elif t == "bathroom" and span > 1.8:
            tub = along(0.75, 1.7, 0.05)
            if put(tub):
                xs_ = [p[0] for p in tub]
                ys_ = [p[1] for p in tub]
                cx, cy = (min(xs_) + max(xs_)) / 2, (min(ys_) + max(ys_)) / 2
                dr.plines.append(("furn", [(cx + 0.7 * math.cos(a) * (max(xs_) - min(xs_)) / 1.7,
                                            cy + 0.3 * math.sin(a) * (max(ys_) - min(ys_)) / 0.75)
                                           for a in [2 * math.pi * i / 32 for i in range(32)]], True))
            put(_circle((x0 + w * 0.7, y0 + h * 0.7), 0.22))   # basin
        elif t == "wc" and span > 0.9:
            cx, cy = x0 + w / 2, y0 + 0.25
            if put(_rect(cx - 0.2, y0, cx + 0.2, y0 + 0.18)):
                dr.plines.append(("furn", [(cx + 0.18 * math.cos(a), cy + 0.18 + 0.28 * math.sin(a))
                                           for a in [2 * math.pi * i / 24 for i in range(24)]], True))

    if cfg.get("wall_style") == "hatched":
        # exploded 45-degree hatch pattern clipped to the wall bodies (what many PDF exporters emit)
        bx0, by0, bx1, by1 = walls_body.bounds
        k = 0.10
        s = by0 - (bx1 - bx0)
        while s < by1:
            ln = LineString([(bx0, s), (bx1, s + (bx1 - bx0))]).intersection(walls_body)
            for g in getattr(ln, "geoms", [ln]):
                if g.geom_type == "LineString" and g.length > 0.02:
                    a, b = list(g.coords)[0], list(g.coords)[-1]
                    dr.lines.append(("hatch", a, b))
            s += k

    # sheet frame and dashed grid axes beyond the plan
    bx0, by0, bx1, by1 = walls_body.bounds
    dr.plines.append(("furn", _rect(bx0 - 3.0, by0 - 3.0, bx1 + 3.0, by1 + 3.0), True))
    for x in (bx0 + 0.15, bx1 - 0.15):
        y = by0 - 2.6
        while y < by1 + 2.6:
            dr.lines.append(("dims", (x, y), (x, min(y + 0.6, by1 + 2.6))))
            y += 0.9
        dr.plines.append(("dims", _circle((x, by1 + 2.85), 0.2), True))


def _node(x):
    return x if isinstance(x, str) else f"r{x}"


def _unit(w):
    L = _len(w)
    return ((w["q"][0] - w["p"][0]) / L, (w["q"][1] - w["p"][1]) / L)


def _centre(r):
    return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)


def _dim_draw(dr: RDrawing, d: dict) -> None:
    (x1, y1), (x2, y2) = d["p1"], d["p2"]
    yb = d["base"]
    dr.lines.append(("dims", (x1, y1 - 0.05), (x1, yb - 0.10)))
    dr.lines.append(("dims", (x2, y2 - 0.05), (x2, yb - 0.10)))
    dr.lines.append(("dims", (x1, yb), (x2, yb)))
    t = 0.10 / math.sqrt(2)
    for x in (x1, x2):
        dr.lines.append(("dims", (x - t, yb - t), (x + t, yb + t)))
    dr.texts.append(("dims", f"{d['measured']:.2f}".replace(".", ","), ((x1 + x2) / 2, yb + 0.14), 0.16, 0.0))


# ---------------------------------------------------------------------------
# Writers

def _write_dxf(dr: RDrawing, path: Path, cfg: dict, k: float) -> None:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4 if cfg["units"] == "mm" else 6
    L = LAYER_SCHEMES[cfg["scheme"]]
    for name in set(L.values()):
        if name not in doc.layers:
            doc.layers.add(name)
    msp = doc.modelspace()

    def P(p):
        return (p[0] * k, p[1] * k)

    for role, a, b in dr.lines:
        msp.add_line(P(a), P(b), dxfattribs={"layer": L[role]})
    for role, pts, closed in dr.plines:
        msp.add_lwpolyline([P(p) for p in pts], close=closed, dxfattribs={"layer": L[role]})
    for role, rings, _f in dr.polys:
        h = msp.add_hatch(color=8, dxfattribs={"layer": L[role]})
        for i, ring in enumerate(rings):
            h.paths.add_polyline_path([P(p) for p in ring[:-1]], is_closed=True, flags=1 if i == 0 else 0)
    for role, c, r, a0, a1, style in dr.arcs:
        if style == "bulge":
            s = (c[0] + r * math.cos(math.radians(a0)), c[1] + r * math.sin(math.radians(a0)))
            e = (c[0] + r * math.cos(math.radians(a1)), c[1] + r * math.sin(math.radians(a1)))
            bulge = math.tan(math.radians(((a1 - a0) % 360) / 4))
            msp.add_lwpolyline([(*P(s), 0, 0, bulge), (*P(e), 0, 0, 0)], format="xyseb",
                               dxfattribs={"layer": L[role]})
        elif style == "segments":
            n = 12
            pts = [(c[0] + r * math.cos(math.radians(a0 + 90 * i / n)), c[1] + r * math.sin(math.radians(a0 + 90 * i / n)))
                   for i in range(n + 1)]
            for a, b in zip(pts, pts[1:]):
                msp.add_line(P(a), P(b), dxfattribs={"layer": L[role]})
        else:
            msp.add_arc(P(c), r * k, a0, a1, dxfattribs={"layer": L[role]})
    if dr.blocks:
        # unit door: hinge at the origin, leaf open along local +x, closed position along local -y
        blk = doc.blocks.new("PORTE_STD")
        blk.add_line((0, 0), (1, 0), dxfattribs={"layer": "0"})
        blk.add_arc((0, 0), 1.0, 270.0, 360.0, dxfattribs={"layer": "0"})
        for hinge, ac, ao, r in dr.blocks:
            # closed = open - 90 deg as drawn; closed = open + 90 deg needs a mirrored insert
            mirror = abs((ao - ac) % 360 - 90) > 1e-6
            msp.add_blockref("PORTE_STD", P(hinge), dxfattribs={"rotation": ao, "xscale": r * k,
                                                                  "yscale": -r * k if mirror else r * k,
                                                                  "layer": L["door"]})
    for role, text, at, h, rot in dr.texts:
        t = msp.add_text(text, height=h * k, rotation=rot, dxfattribs={"layer": L[role]})
        t.set_placement(P(at), align=TextEntityAlignment.MIDDLE_CENTER)
    doc.saveas(path)


def _write_pdf(dr: RDrawing, path: Path, cfg: dict) -> dict:
    import pymupdf

    k = 1000.0 / cfg["denominator"]
    margin = 20.0
    pts = [p for _, a, b in dr.lines for p in (a, b)] + [t[2] for t in dr.texts]
    pts += [p for _, rings, _ in dr.polys for ring in rings for p in ring] + [p for _, ps, _ in dr.plines for p in ps]
    minx, miny = min(p[0] for p in pts) - 1.0, min(p[1] for p in pts) - 1.0
    maxx, maxy = max(p[0] for p in pts) + 1.0, max(p[1] for p in pts) + 1.0
    W, H = (maxx - minx) * k + 2 * margin, (maxy - miny) * k + 2 * margin
    PT = 72 / 25.4

    def P(p):
        return pymupdf.Point((margin + (p[0] - minx) * k) * PT, (H - margin - (p[1] - miny) * k) * PT)

    doc = pymupdf.open()
    page = doc.new_page(width=W * PT, height=H * PT)
    L = LAYER_SCHEMES[cfg["scheme"]]
    oc = {} if cfg["scheme"] == "none" else {n: doc.add_ocg(n, on=True) for n in set(L.values())}
    width = {"wall": 0.5, "door": 0.25, "glaz": 0.18, "text": 0.1, "dims": 0.13, "furn": 0.13, "hatch": 0.05}

    def st(role):
        d = dict(color=(0, 0, 0), width=width[role] * PT)
        if oc:
            d["oc"] = oc[L[role]]
        return d

    for role, a, b in dr.lines:
        page.draw_line(P(a), P(b), **st(role))
    for role, pts_, closed in dr.plines:
        page.draw_polyline([P(p) for p in pts_] + ([P(pts_[0])] if closed else []), **st(role))
    for role, rings, _f in dr.polys:
        shape = page.new_shape()
        for ring in rings:
            shape.draw_polyline([P(p) for p in ring])
        s = st(role)
        shape.finish(color=None if role == "wall" else s["color"], fill=(0.55, 0.55, 0.55), even_odd=True,
                     width=s["width"], oc=s.get("oc", 0))
        shape.commit()
    for role, c, r, a0, a1, style in dr.arcs:
        if style == "segments":
            n = 12
            ps = [(c[0] + r * math.cos(math.radians(a0 + 90 * i / n)), c[1] + r * math.sin(math.radians(a0 + 90 * i / n)))
                  for i in range(n + 1)]
            page.draw_polyline([P(p) for p in ps], **st(role))
            continue
        t0, t1 = math.radians(a0), math.radians(a0 + ((a1 - a0) % 360))
        kk = 4 / 3 * math.tan((t1 - t0) / 4)
        p0 = (c[0] + r * math.cos(t0), c[1] + r * math.sin(t0))
        p3 = (c[0] + r * math.cos(t1), c[1] + r * math.sin(t1))
        p1 = (p0[0] - kk * r * math.sin(t0), p0[1] + kk * r * math.cos(t0))
        p2 = (p3[0] + kk * r * math.sin(t1), p3[1] - kk * r * math.cos(t1))
        page.draw_bezier(P(p0), P(p1), P(p2), P(p3), **st(role))
    for hinge, ac, ao, r in dr.blocks:      # block doors are exploded in the PDF, as exporters do
        open_end = (hinge[0] + r * math.cos(math.radians(ao)), hinge[1] + r * math.sin(math.radians(ao)))
        page.draw_line(P(hinge), P(open_end), **st("door"))
        a0, a1 = (ac, ao) if abs((ao - ac) % 360 - 90) < 1e-6 else (ao, ac)
        t0, t1 = math.radians(a0), math.radians(a0) + math.pi / 2
        kk = 4 / 3 * math.tan(math.pi / 8)
        p0 = (hinge[0] + r * math.cos(t0), hinge[1] + r * math.sin(t0))
        p3 = (hinge[0] + r * math.cos(t1), hinge[1] + r * math.sin(t1))
        p1 = (p0[0] - kk * r * math.sin(t0), p0[1] + kk * r * math.cos(t0))
        p2 = (p3[0] + kk * r * math.sin(t1), p3[1] - kk * r * math.cos(t1))
        page.draw_bezier(P(p0), P(p1), P(p2), P(p3), **st("door"))
    for role, text, at, h, rot in dr.texts:
        size = h * k * PT * 1.25
        tl = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
        c = P(at)
        org = pymupdf.Point(c.x - tl / 2, c.y + size * 0.35)
        kw = dict(fontsize=size, fontname="helv")
        if oc:
            kw["oc"] = oc[L[role]]
        if rot:
            kw["morph"] = (c, pymupdf.Matrix(rot))      # Matrix(+deg) turns text counter-clockwise on the page
        page.insert_text(org, text, **kw)
    doc.save(path)
    return {"k": k, "ox": margin - minx * k, "oy": margin - miny * k}
