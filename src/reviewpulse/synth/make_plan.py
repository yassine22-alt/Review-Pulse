"""T1 - Synthetic plan generator with exact ground truth and planted errors.

One in-memory drawing (metres, y up) is written to:
- a DXF (true LINE/ARC/TEXT/DIMENSION entities, $INSUNITS = metres),
- a vector PDF at 1:denominator with one optional-content layer per CAD layer
  (real text, dimension ticks, so R2 and R7 can be tested on it),
- a PNG rendered from the PDF,
- ``truth.json`` with walls, openings, rooms, room graph, dimensions, tags and
  the findings each planted error must produce.

Layout family (rows bottom to top), sizes drawn from the seed:

    row 2:  CHAMBRE 1 | CHAMBRE 3 | SDB
    row 1:  DEGAGEMENT (corridor spanning the three columns)
    row 0:  SEJOUR    | CUISINE   | CHAMBRE 2

The generator lives in the package (not only in tests/) because the rule
tester (I5) and ``rp synth`` use it too.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

T_INT = 0.20
T_EXT = 0.30
MAX_WINDOW_M = 2.9      # widest window R9 can recognise as a gap (3.0 m) minus margin; huge rooms then fail C-V1

ERRORS = {
    "topo_bedroom_via_bedroom": [("C-T2", "FAIL", "bed3"), ("C-T1", "FAIL", "bed3")],
    "topo_exit_via_bath": [("C-T1", "FAIL", "bed3")],
    "topo_garage_bedroom": [("C-T3", "FAIL", "kitchen")],
    "topo_dead_end_no_window": [("C-T4", "FAIL", "bed2"), ("C-V1", "FAIL", "bed2")],
    "metric_door_narrow": [("C-D1", "FAIL", "door:bed1-corridor")],
    "metric_corridor_pinch": [("C-D2", "FAIL", "corridor")],
    "metric_room_small": [("C-D3", "FAIL", "bed1")],
    "metric_window_small": [("C-V1", "FAIL", "bed1"), ("C-V2", "FAIL", "bed1")],
    "cons_chain_off": [("K-A1", "FAIL", "chain:bottom")],
    # a wrong written part also breaks the written chain sum
    "cons_written_vs_drawn": [("K-A2", "FAIL", "dim:bottom:1"), ("K-A1", "FAIL", "chain:bottom")],
    "cons_schedule_width": [("K-X1", "FAIL", "door:bed3-corridor")],
    "cons_area_text": [("K-A3", "FAIL", "living")],
    "comp_unlabelled_room": [("P-1", "FAIL", "bed3")],
    "comp_no_dimensions": [("P-2", "FAIL", "sheet")],
    "comp_tag_missing": [("P-3", "FAIL", "P9")],
    "coord_swing_overlap": [("Q-1", "WARNING", "door:bath-corridor")],
    # no exterior door: no exit at all, so every habitable room also fails reachability
    "topo_no_exit": [("C-C1", "FAIL", "sheet"), ("C-T1", "FAIL", "living"), ("C-T1", "FAIL", "kitchen"),
                     ("C-T1", "FAIL", "bed1"), ("C-T1", "FAIL", "bed2"), ("C-T1", "FAIL", "bed3"),
                     ("C-T2", "FAIL", "bed1"), ("C-T2", "FAIL", "bed2"), ("C-T2", "FAIL", "bed3")],
    "comp_title_incomplete": [("P-4", "FAIL", "sheet")],
    # a 2.0 m wide (but long enough) bedroom; the living room in the same column shrinks with it
    "metric_bedroom_narrow": [("C-D3W", "FAIL", "bed1"), ("C-D3L", "FAIL", "living")],
    "metric_living_small": [("C-D3L", "FAIL", "living")],
    # a 17 m wide dwelling; its 6 m rooms also exceed what a 2.9 m window can light
    "metric_travel_far": [("C-T5", "FAIL", "bed2"), ("C-V1", "FAIL", "kitchen")],
    # a 1.8 m wide kitchen column also makes the bedroom above it too small and too narrow
    "metric_kitchen_small": [("C-D5", "FAIL", "kitchen"), ("C-D3", "FAIL", "bed3"), ("C-D3W", "FAIL", "bed3")],
    # the bedroom window is scheduled 0.80 m high: no escape window, and less light
    "metric_escape_window": [("C-V2", "FAIL", "bed1"), ("C-V1", "FAIL", "bed1")],
    "comp_door_untagged": [("P-5", "FAIL", "door:kitchen-living")],
    "topo_isolated_room": [("P-6", "FAIL", "bath")],
}

LABELS = {"living": "SEJOUR", "kitchen": "CUISINE", "bed2": "CHAMBRE 2", "corridor": "DEGAGEMENT",
          "bed1": "CHAMBRE 1", "bed3": "CHAMBRE 3", "bath": "SDB", "garage": "GARAGE"}
TYPES = {"living": "living", "kitchen": "kitchen", "bed2": "bedroom", "corridor": "corridor",
         "bed1": "bedroom", "bed3": "bedroom", "bath": "bathroom", "garage": "garage"}

LAYERS = {  # name -> (ACI colour, PDF stroke width mm, rgb)
    "A-WALL": (7, 0.50, (0, 0, 0)),
    "A-DOOR": (3, 0.25, (0.0, 0.45, 0.0)),
    "A-GLAZ": (4, 0.18, (0.0, 0.4, 0.7)),
    "A-ANNO-TEXT": (7, 0.10, (0, 0, 0)),
    "A-ANNO-DIMS": (1, 0.13, (0.6, 0, 0)),
    "A-FURN": (8, 0.13, (0.5, 0.5, 0.5)),
    "A-HATCH": (8, 0.05, (0.75, 0.75, 0.75)),
    "A-TTLB": (7, 0.25, (0, 0, 0)),
    "A-ANNO-TABL": (7, 0.18, (0, 0, 0)),
}


@dataclass
class Opening:
    kind: str                 # door | window
    seg: tuple                # wall segment key
    a: str                    # room
    b: str                    # room, EXIT or EXTERIOR
    width: float
    swing_into: str | None = None
    tag: str = ""
    hinge_end: str = "start"  # which jamb carries the hinge
    frac: float = 0.5         # opening centre along the segment


@dataclass
class Drawing:
    lines: list = field(default_factory=list)     # (layer, (x,y), (x,y))
    arcs: list = field(default_factory=list)      # (layer, (cx,cy), r, a0, a1)
    polys: list = field(default_factory=list)     # (layer, pts, filled)
    texts: list = field(default_factory=list)     # (layer, text, (x,y) centre, height, rot)
    dims: list = field(default_factory=list)      # dict(p1, p2, base, angle, text, id, chain)


# --------------------------------------------------------------------------
# Layout

def _spec(seed: int, errors: tuple[str, ...]):
    rnd = random.Random(seed)
    # bounds keep the clean flat within the example regulation's 15 m travel distance, measured from
    # the farthest corner of the far bedroom (worst case, every bound at its maximum: 14.9 m)
    cols = [rnd.uniform(4.2, 4.8), rnd.uniform(3.2, 3.8), rnd.uniform(3.3, 3.8)]
    rows = [rnd.uniform(4.1, 4.4), rnd.uniform(1.20, 1.40), rnd.uniform(3.5, 4.2)]
    cols = [round(c, 2) for c in cols]
    rows = [round(r, 2) for r in rows]
    if "metric_room_small" in errors:          # bed1 net area 7.5 m2
        cols[0] = round(7.5 / (rows[2] - (T_EXT + T_INT) / 2) + (T_EXT + T_INT) / 2, 3)
    half = (T_EXT + T_INT) / 2
    if "metric_bedroom_narrow" in errors:      # bed1 2.00 m wide, still >= 9 m2
        cols[0] = round(2.0 + half, 3)
        rows[2] = round(9.4 / 2.0 + half, 3)
    if "metric_living_small" in errors:        # living net area 12.5 m2, bed1 still >= 9 m2
        cols[0] = round(12.5 / (rows[0] - half) + half, 3)
    if "metric_travel_far" in errors:          # a 17 m wide dwelling
        cols[1] = cols[2] = 6.5
    if "metric_kitchen_small" in errors:       # kitchen 1.8 m wide, under 7 m2
        cols[1] = 1.75
    grid = {(0, 0): "living", (1, 0): "kitchen", (2, 0): "bed2",
            (0, 1): "corridor", (1, 1): "corridor", (2, 1): "corridor",
            (0, 2): "bed1", (1, 2): "bed3", (2, 2): "bath"}
    if "topo_garage_bedroom" in errors:
        grid[(1, 0)] = "garage"
    kitchen = grid[(1, 0)]
    ops = [
        Opening("door", ("v", 0, 1), "corridor", "EXIT", 0.90, "corridor", "P1"),     # entrance into the hall
        Opening("door", ("h", 0, 1), "living", "corridor", 0.90, "living", "P2"),
        Opening("door", ("v", 1, 0), kitchen, "living", 0.80, kitchen, "P3", frac=0.7),
        Opening("door", ("h", 2, 1), "bed2", "corridor", 0.85, "bed2", "P4"),
        Opening("door", ("h", 0, 2), "bed1", "corridor", 0.85, "bed1", "P5"),
        Opening("door", ("h", 1, 2), "bed3", "corridor", 0.85, "bed3", "P6"),
        Opening("door", ("h", 2, 2), "bath", "corridor", 0.80, "bath", "P7"),
        Opening("window", ("v", 0, 0), "living", "EXTERIOR", 1.40, tag="F1"),
        Opening("window", ("h", 1, 0), kitchen, "EXTERIOR", 1.20, tag="F2"),
        Opening("window", ("h", 2, 0), "bed2", "EXTERIOR", 1.20, tag="F3"),
        Opening("window", ("h", 0, 3), "bed1", "EXTERIOR", 1.20, tag="F4"),
        Opening("window", ("h", 1, 3), "bed3", "EXTERIOR", 1.20, tag="F5"),
        Opening("window", ("h", 2, 3), "bath", "EXTERIOR", 0.60, tag="F6"),
    ]
    by_tag = {o.tag: o for o in ops}
    if "topo_bedroom_via_bedroom" in errors:
        ops.remove(by_tag["P6"])
        ops.append(Opening("door", ("v", 1, 2), "bed3", "bed1", 0.85, "bed3", "P6"))
    if "topo_exit_via_bath" in errors:
        ops.remove(by_tag["P6"])
        ops.append(Opening("door", ("v", 2, 2), "bed3", "bath", 0.85, "bed3", "P6"))
    if "topo_garage_bedroom" in errors:
        ops.append(Opening("door", ("v", 2, 0), "garage", "bed2", 0.80, "garage", "P8", frac=0.75))
    if "topo_no_exit" in errors:
        ops.remove(by_tag["P1"])
    if "topo_isolated_room" in errors:
        ops.remove(by_tag["P7"])
    if "comp_door_untagged" in errors:
        by_tag["P3"].tag = ""
    if "topo_dead_end_no_window" in errors:
        ops.remove(by_tag["F3"])
    if "metric_door_narrow" in errors:
        by_tag["P5"].width = 0.70
    if "coord_swing_overlap" in errors:
        by_tag["P4"].swing_into = "corridor"
        by_tag["P7"].swing_into = "corridor"
    return cols, rows, grid, ops


def _walls(cols, rows, grid):
    xs = [0.0]
    for c in cols:
        xs.append(round(xs[-1] + c, 6))
    ys = [0.0]
    for r in rows:
        ys.append(round(ys[-1] + r, 6))
    nc, nr = len(cols), len(rows)
    segs = {}
    for j in range(nr + 1):                     # horizontal grid lines
        for i in range(nc):
            below, above = grid.get((i, j - 1)), grid.get((i, j))
            if below != above:
                ext = below is None or above is None
                segs[("h", i, j)] = dict(p=(xs[i], ys[j]), q=(xs[i + 1], ys[j]), t=T_EXT if ext else T_INT,
                                         rooms=(below or "OUT", above or "OUT"), ext=ext)
    for i in range(nc + 1):                     # vertical grid lines
        for j in range(nr):
            left, right = grid.get((i - 1, j)), grid.get((i, j))
            if left != right:
                ext = left is None or right is None
                segs[("v", i, j)] = dict(p=(xs[i], ys[j]), q=(xs[i], ys[j + 1]), t=T_EXT if ext else T_INT,
                                         rooms=(left or "OUT", right or "OUT"), ext=ext)
    # half thickness of perpendicular walls at each node, used to extend segments into junctions
    node_perp: dict[tuple, dict[str, float]] = {}
    for k, s in segs.items():
        for pt in (s["p"], s["q"]):
            d = node_perp.setdefault(pt, {"h": 0.0, "v": 0.0})
            d[k[0]] = max(d[k[0]], s["t"])
    for k, s in segs.items():
        other = "v" if k[0] == "h" else "h"
        s["ext_p"] = node_perp[s["p"]][other] / 2
        s["ext_q"] = node_perp[s["q"]][other] / 2
    return xs, ys, segs


def _axis(s):
    (px, py), (qx, qy) = s["p"], s["q"]
    L = math.hypot(qx - px, qy - py)
    u = ((qx - px) / L, (qy - py) / L)
    n = (-u[1], u[0])
    return L, u, n


def _at(s, along, across=0.0):
    L, u, n = _axis(s)
    return (round(s["p"][0] + u[0] * along + n[0] * across, 6), round(s["p"][1] + u[1] * along + n[1] * across, 6))


def _room_poly(grid, xs, ys, room):
    return unary_union([box(xs[i], ys[j], xs[i + 1], ys[j + 1]) for (i, j), r in grid.items() if r == room])


# --------------------------------------------------------------------------
# Main entry

def make_plan(out_dir: str | Path, seed: int = 0, denominator: int = 100, rotate: int = 0,
              errors: tuple[str, ...] = (), strip_layers: bool = False, noise: float = 0.0,
              name: str | None = None, png: bool = True) -> dict:
    unknown = set(errors) - set(ERRORS)
    if unknown:
        raise ValueError(f"unknown planted errors: {sorted(unknown)}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = name or f"synth_{seed:04d}" + ("_" + "_".join(errors) if errors else "")
    rnd = random.Random(seed + 7919)

    cols, rows, grid, ops = _spec(seed, tuple(errors))
    xs, ys, segs = _walls(cols, rows, grid)
    dr = Drawing()

    # ---- wall body: union of rectangles minus openings ---------------------
    rects = []
    for _k, s in segs.items():
        L, u, n = _axis(s)
        a = (s["p"][0] - u[0] * s["ext_p"], s["p"][1] - u[1] * s["ext_p"])
        b = (s["q"][0] + u[0] * s["ext_q"], s["q"][1] + u[1] * s["ext_q"])
        rects.append(LineString([a, b]).buffer(s["t"] / 2, cap_style="flat", join_style="mitre"))
    walls_solid = unary_union(rects)

    # clean plans size habitable-room windows to >= 1/6 of the net floor area (height 1.25 m)
    for o in ops:
        if o.kind != "window" or o.a not in ("living", "kitchen", "bed1", "bed2", "bed3"):
            continue
        net = _room_poly(grid, xs, ys, o.a).difference(walls_solid).area
        L = _axis(segs[o.seg])[0]
        need = net / 6 / 1.25 + 0.10
        o.width = round(min(max(o.width, math.ceil(need * 10) / 10), L - 0.9, MAX_WINDOW_M), 2)
        if "metric_window_small" in errors and o.tag == "F4":
            o.width = 0.80

    cuts, open_truth = [], []
    for o in ops:
        s = segs[o.seg]
        L, u, n = _axis(s)
        c = o.frac * L
        s0, s1 = c - o.width / 2, c + o.width / 2
        cut = Polygon([_at(s, s0, -s["t"] / 2 - 0.01), _at(s, s1, -s["t"] / 2 - 0.01),
                       _at(s, s1, s["t"] / 2 + 0.01), _at(s, s0, s["t"] / 2 + 0.01)])
        cuts.append(cut)
        rec = dict(id=f"{o.kind}:{o.a}-{o.b}" if o.b not in ("EXIT", "EXTERIOR") else f"{o.kind}:{o.a}-{o.b.lower()}",
                   cls=o.kind, tag=o.tag, rooms=[o.a, o.b], width_m=o.width, wall=list(o.seg),
                   polygon=[_at(s, s0, -s["t"] / 2), _at(s, s1, -s["t"] / 2), _at(s, s1, s["t"] / 2),
                            _at(s, s0, s["t"] / 2)],
                   midpoint=_at(s, c))
        if o.kind == "door":
            # side of the swing room
            rp = _room_poly(grid, xs, ys, o.swing_into)
            mid = _at(s, c)
            sgn = 1 if (rp.centroid.x - mid[0]) * n[0] + (rp.centroid.y - mid[1]) * n[1] > 0 else -1
            hinge_s = s0 if o.hinge_end == "start" else s1
            other_s = s1 if o.hinge_end == "start" else s0
            hinge = _at(s, hinge_s, sgn * s["t"] / 2)
            closed = _at(s, other_s, sgn * s["t"] / 2)
            open_end = (round(hinge[0] + sgn * n[0] * o.width, 6), round(hinge[1] + sgn * n[1] * o.width, 6))
            ac = math.degrees(math.atan2(closed[1] - hinge[1], closed[0] - hinge[0])) % 360
            ao = math.degrees(math.atan2(open_end[1] - hinge[1], open_end[0] - hinge[0])) % 360
            a0, a1 = (ac, ao) if (ao - ac) % 360 == 90 or abs((ao - ac) % 360 - 90) < 1e-6 else (ao, ac)
            dr.arcs.append(("A-DOOR", hinge, o.width, round(a0, 6), round(a1, 6)))
            dr.lines.append(("A-DOOR", hinge, open_end))
            sector = [hinge] + [(hinge[0] + o.width * math.cos(math.radians(a0 + 90 * i / 16)),
                                 hinge[1] + o.width * math.sin(math.radians(a0 + 90 * i / 16))) for i in range(17)]
            rec.update(hinge=hinge, swing_into=o.swing_into, swing_polygon=[(round(x, 6), round(y, 6)) for x, y in sector])
        else:
            for off in (-s["t"] / 2, 0.0, s["t"] / 2):
                dr.lines.append(("A-GLAZ", _at(s, s0, off), _at(s, s1, off)))
        open_truth.append(rec)
        # tag text, outside the swing, beside the opening
        if o.tag:
            side = -1 if o.kind == "door" and sgn == 1 else 1
            tpos = _at(s, c, side * (s["t"] / 2 + 0.30))
            dr.texts.append(("A-ANNO-TEXT", o.tag, tpos, 0.18, 0.0))

    walls_cut = walls_solid.difference(unary_union(cuts))
    for g in getattr(walls_cut, "geoms", [walls_cut]):
        for ring in [g.exterior, *g.interiors]:
            cs = list(ring.coords)
            for a, b in zip(cs, cs[1:]):
                dr.lines.append(("A-WALL", (round(a[0], 6), round(a[1], 6)), (round(b[0], 6), round(b[1], 6))))

    # ---- corridor pinch (pilaster, a filled column on the wall layer) ----------
    columns = []
    corridor_net = rows[1] - T_INT
    if "metric_corridor_pinch" in errors:
        depth = round(corridor_net - 0.90, 6)
        cx = xs[1] + cols[1] * 0.5
        y0 = ys[1] + T_INT / 2
        col = [(cx - 0.2, y0), (cx + 0.2, y0), (cx + 0.2, y0 + depth), (cx - 0.2, y0 + depth)]
        dr.polys.append(("A-WALL", col, True))
        columns.append(col)

    # ---- rooms truth ----------------------------------------------------------
    barrier = walls_solid.union(unary_union([Polygon(c) for c in columns])) if columns else walls_solid
    rooms_truth = {}
    for room in sorted(set(grid.values())):
        net = _room_poly(grid, xs, ys, room).difference(barrier)
        if net.geom_type == "MultiPolygon":
            net = max(net.geoms, key=lambda g: g.area)
        rooms_truth[room] = dict(id=room, label=LABELS[room], type=TYPES[room], area_m2=round(net.area, 4),
                                 polygon=[(round(x, 6), round(y, 6)) for x, y in net.exterior.coords[:-1]])

    # ---- texts ------------------------------------------------------------------
    for room, r in rooms_truth.items():
        if room == "bed3" and "comp_unlabelled_room" in errors:
            r["label"] = None
            continue
        c = Polygon(r["polygon"]).representative_point() if room == "corridor" else Polygon(r["polygon"]).centroid
        cxy = (round(c.x, 3), round(c.y, 3))
        dr.texts.append(("A-ANNO-TEXT", r["label"], cxy, 0.25, 0.0))
        stated = r["area_m2"] + (2.0 if room == "living" and "cons_area_text" in errors else 0.0)
        r["stated_area_m2"] = round(stated, 2)
        area_txt = f"{stated:.2f}".replace(".", ",") + " m²"
        dr.texts.append(("A-ANNO-TEXT", area_txt, (cxy[0], round(cxy[1] - 0.40, 3)), 0.18, 0.0))

    # ---- dimensions: one chain under the plan, one on the left -----------------
    dims_truth = []
    if "comp_no_dimensions" not in errors:
        yb = -T_EXT / 2
        for i in range(len(cols)):
            text = None
            if "cons_written_vs_drawn" in errors and i == 1:
                text = f"{cols[i] - 0.30:.2f}".replace(".", ",")
            dr.dims.append(dict(id=f"dim:bottom:{i}", chain="chain:bottom", p1=(xs[i], yb), p2=(xs[i + 1], yb),
                                base=(xs[i], -1.0), angle=0, text=text, measured=cols[i]))
        total = xs[-1]
        tot_text = None
        if "cons_chain_off" in errors:
            tot_text = f"{total + 0.10:.2f}".replace(".", ",")
        dr.dims.append(dict(id="dim:bottom:total", chain="chain:bottom", p1=(0.0, yb), p2=(total, yb),
                            base=(0.0, -1.8), angle=0, text=tot_text, measured=total, overall=True))
        xl = -T_EXT / 2
        for j in range(len(rows)):
            dr.dims.append(dict(id=f"dim:left:{j}", chain="chain:left", p1=(xl, ys[j]), p2=(xl, ys[j + 1]),
                                base=(-1.0, ys[j]), angle=90, text=None, measured=rows[j]))
        dr.dims.append(dict(id="dim:left:total", chain="chain:left", p1=(xl, 0.0), p2=(xl, ys[-1]),
                            base=(-1.8, 0.0), angle=90, text=None, measured=ys[-1], overall=True))
        for d in dr.dims:
            stated = d["measured"] if d["text"] is None else float(d["text"].replace(",", "."))
            dims_truth.append(dict(id=d["id"], chain=d["chain"], p1=d["p1"], p2=d["p2"],
                                   measured_m=round(d["measured"], 6), stated_m=round(stated, 6),
                                   overall=d.get("overall", False)))

    # ---- furniture noise ---------------------------------------------------------
    for room in ("bed1", "bed2", "bed3"):
        if room not in rooms_truth:
            continue
        c = Polygon(rooms_truth[room]["polygon"]).centroid
        bx, by = c.x + rnd.uniform(-0.3, 0.3), c.y + 0.5
        bed = [(bx - 0.7, by), (bx + 0.7, by), (bx + 0.7, by + 1.0), (bx - 0.7, by + 1.0)]
        for a, b in zip(bed, bed[1:] + bed[:1]):
            dr.lines.append(("A-FURN", a, b))

    # ---- title block -------------------------------------------------------------
    tx, ty = xs[-1] + 1.5, -1.8
    tb_lines = ["PLAN DU REZ-DE-CHAUSSEE", "PROJET ReviewPulse synth", f"ECHELLE 1:{denominator}",
                "DATE 24/10/2026", "INDICE A"]
    if "comp_title_incomplete" in errors:
        tb_lines.remove("DATE 24/10/2026")
    for k, line in enumerate(tb_lines):
        dr.texts.append(("A-TTLB", line, (tx + 1.6, ty + 0.35 * (len(tb_lines) - 1 - k) + 0.2), 0.15, 0.0))

    # ---- schedule: truth and a drawn table (ruled, text in cells) ------------------
    schedule = [dict(tag=o.tag, kind=o.kind, width_m=o.width,
                     height_m=2.10 if o.kind == "door" else (0.60 if o.width < 1.0 else 1.25))
                for o in sorted((o for o in ops if o.tag), key=lambda o: (o.tag[0] != "P", int(o.tag[1:])))]
    if "cons_schedule_width" in errors:
        for row in schedule:
            if row["tag"] == "P6":
                row["width_m"] = round(row["width_m"] + 0.10, 2)
    if "metric_escape_window" in errors:
        for row in schedule:
            if row["tag"] == "F4":
                row["height_m"] = 0.80
    if "comp_tag_missing" in errors:
        dr.texts.append(("A-ANNO-TEXT", "P9", (xs[1] + 0.6, ys[1] + rows[1] / 2), 0.18, 0.0))
    _draw_schedule(dr, schedule, x0=xs[-1] + 1.5, y_top=ys[-1])

    if strip_layers:
        dr.lines = [("0", a, b) for _, a, b in dr.lines]
        dr.arcs = [("0", *rest) for _, *rest in dr.arcs]
        dr.polys = [("0", *rest) for _, *rest in dr.polys]
        dr.texts = [("0", *rest) for _, *rest in dr.texts]

    # ---- truth ------------------------------------------------------------------
    walls_truth = []
    for k, s in segs.items():
        L = _axis(s)[0]
        cuts = sorted((o.frac * L - o.width / 2, o.frac * L + o.width / 2) for o in ops if o.seg == k)
        pos, pieces = 0.0, []
        for a, b in cuts:
            if a > pos:
                pieces.append((pos, a))
            pos = max(pos, b)
        if pos < L:
            pieces.append((pos, L))
        for i, (a, b) in enumerate(pieces):
            walls_truth.append(dict(id=f"wall:{k[0]}{k[1]}{k[2]}:{i}", centreline=[_at(s, a), _at(s, b)],
                                    thickness=s["t"], exterior=s["ext"], rooms=list(s["rooms"])))
    edges = []
    for o in ops:
        kind = "door" if o.kind == "door" else "window"
        edges.append(dict(a=o.a, b=o.b, kind=kind, width_m=o.width, tag=o.tag))
    expected = []
    for e in errors:
        for rule, verdict, subject in ERRORS[e]:
            expected.append(dict(error=e, rule=rule, verdict=verdict, subject=subject))
    truth = dict(name=name, seed=seed, denominator=denominator, rotate=rotate, errors=list(errors),
                 units="m", cols=cols, rows=rows, walls=walls_truth, columns=columns, openings=open_truth,
                 rooms=list(rooms_truth.values()), edges=edges, dimensions=dims_truth, schedule=schedule,
                 expected_findings=expected)

    paths = dict(truth=out_dir / f"{name}.truth.json", dxf=out_dir / f"{name}.dxf", pdf=out_dir / f"{name}.pdf")
    _write_dxf(dr, paths["dxf"])
    # metres -> PDF sheet space (paper mm, y up, before page rotation): x_mm = ox + k x, y_mm = oy + k y
    truth["pdf_transform"] = _write_pdf(dr, paths["pdf"], denominator, rotate)
    paths["truth"].write_text(json.dumps(truth, indent=1), encoding="utf-8")
    if png:
        paths["png"] = out_dir / f"{name}.png"
        _write_png(paths["pdf"], paths["png"], noise=noise, seed=seed)
    return {k: str(v) for k, v in paths.items()}


def _draw_schedule(dr: Drawing, schedule: list[dict], x0: float, y_top: float) -> None:
    """Door and window schedule: title, header row, one ruled row per tag."""
    widths = [1.0, 1.3, 1.1, 1.1]
    header = ["REPERE", "TYPE", "LARGEUR", "HAUTEUR"]
    rh = 0.40
    xs_ = [x0]
    for w in widths:
        xs_.append(xs_[-1] + w)
    n = len(schedule) + 1
    dr.texts.append(("A-ANNO-TABL", "TABLEAU DES MENUISERIES", (x0 + sum(widths) / 2, y_top + 0.30), 0.15, 0.0))
    for r in range(n + 1):
        y = y_top - r * rh
        dr.lines.append(("A-ANNO-TABL", (xs_[0], y), (xs_[-1], y)))
    for x in xs_:
        dr.lines.append(("A-ANNO-TABL", (x, y_top), (x, y_top - n * rh)))
    rows_ = [header] + [[row["tag"], "porte" if row["kind"] == "door" else "fenetre",
                         f"{row['width_m']:.2f}".replace(".", ","), f"{row['height_m']:.2f}".replace(".", ",")]
                        for row in schedule]
    for r, cells in enumerate(rows_):
        yc = y_top - (r + 0.5) * rh
        for c, txt in enumerate(cells):
            dr.texts.append(("A-ANNO-TABL", txt, ((xs_[c] + xs_[c + 1]) / 2, yc), 0.15, 0.0))


# --------------------------------------------------------------------------
# Writers

def _write_dxf(dr: Drawing, path: Path) -> None:
    import ezdxf
    from ezdxf import units

    doc = ezdxf.new("R2018", setup=True)
    doc.units = units.M
    doc.header["$INSUNITS"] = 6
    for name, (aci, _w, _rgb) in LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name, color=aci)
    msp = doc.modelspace()
    for layer, a, b in dr.lines:
        msp.add_line(a, b, dxfattribs={"layer": layer})
    for layer, c, r, a0, a1 in dr.arcs:
        msp.add_arc(c, r, a0, a1, dxfattribs={"layer": layer})
    for layer, pts, filled in dr.polys:
        if filled:
            h = msp.add_hatch(color=7, dxfattribs={"layer": layer})
            h.paths.add_polyline_path(pts, is_closed=True)
        else:
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
    for layer, text, at, h, rot in dr.texts:
        t = msp.add_text(text, height=h, rotation=rot, dxfattribs={"layer": layer})
        t.set_placement(at, align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    for d in dr.dims:
        override = {"dimtxt": 0.18, "dimasz": 0.10, "dimtsz": 0.10, "dimexo": 0.05, "dimexe": 0.10,
                    "dimdec": 2, "dimdsep": ord(","), "dimgap": 0.05, "dimtad": 1}
        dim = msp.add_linear_dim(base=d["base"], p1=d["p1"], p2=d["p2"], angle=d["angle"], dimstyle="EZDXF",
                                 text=d["text"] if d["text"] else "<>", override=override,
                                 dxfattribs={"layer": "A-ANNO-DIMS"})
        dim.render()
    doc.saveas(path)


def _write_pdf(dr: Drawing, path: Path, denominator: int, rotate: int) -> dict:
    import pymupdf

    k = 1000.0 / denominator            # mm on paper per metre
    margin = 25.0
    pts = [p for _, a, b in dr.lines for p in (a, b)] + [t[2] for t in dr.texts]
    pts += [(t[2][0] + 1.2, t[2][1]) for t in dr.texts]   # room for text width
    pts += [d["base"] for d in dr.dims]
    minx, miny = min(p[0] for p in pts) - 0.5, min(p[1] for p in pts) - 0.5
    maxx, maxy = max(p[0] for p in pts) + 0.5, max(p[1] for p in pts) + 0.5
    W = (maxx - minx) * k + 2 * margin
    H = (maxy - miny) * k + 2 * margin
    PT = 72 / 25.4

    def P(x, y):                       # metres -> PDF points (y down)
        return pymupdf.Point((margin + (x - minx) * k) * PT, (H - margin - (y - miny) * k) * PT)

    doc = pymupdf.open()
    page = doc.new_page(width=W * PT, height=H * PT)
    ocg = {name: doc.add_ocg(name, on=True) for name in LAYERS}
    ocg["0"] = doc.add_ocg("0", on=True)

    def style(layer):
        _aci, w, rgb = LAYERS.get(layer, (7, 0.25, (0, 0, 0)))
        return dict(color=rgb, width=w * PT, oc=ocg.get(layer, ocg["0"]))

    for layer, a, b in dr.lines:
        page.draw_line(P(*a), P(*b), **style(layer))
    for layer, c, r, a0, a1 in dr.arcs:
        sweep = (a1 - a0) % 360 or 360
        n = max(1, math.ceil(sweep / 90 - 1e-9))
        step = sweep / n
        for i in range(n):
            t0, t1 = math.radians(a0 + i * step), math.radians(a0 + (i + 1) * step)
            kk = 4 / 3 * math.tan((t1 - t0) / 4)
            p0 = (c[0] + r * math.cos(t0), c[1] + r * math.sin(t0))
            p3 = (c[0] + r * math.cos(t1), c[1] + r * math.sin(t1))
            p1 = (p0[0] - kk * r * math.sin(t0), p0[1] + kk * r * math.cos(t0))
            p2 = (p3[0] + kk * r * math.sin(t1), p3[1] - kk * r * math.cos(t1))
            page.draw_bezier(P(*p0), P(*p1), P(*p2), P(*p3), **style(layer))
    for layer, pts_, filled in dr.polys:
        st = style(layer)
        page.draw_polyline([P(*p) for p in pts_] + [P(*pts_[0])], fill=st["color"] if filled else None,
                           closePath=True, **st)

    def text(layer, s, at, h, rot):
        size = h * k * PT * 1.25          # cap height ~ 0.8 of the font size
        tl = pymupdf.get_text_length(s, fontname="helv", fontsize=size)
        c = P(*at)
        if rot % 180 == 0:
            org = pymupdf.Point(c.x - tl / 2, c.y + size * 0.35)
            page.insert_text(org, s, fontsize=size, fontname="helv", color=(0, 0, 0), oc=ocg.get(layer, ocg["0"]))
        else:
            org = pymupdf.Point(c.x + size * 0.35, c.y + tl / 2)
            page.insert_text(org, s, fontsize=size, fontname="helv", rotate=90, color=(0, 0, 0),
                             oc=ocg.get(layer, ocg["0"]))

    for t in dr.texts:
        text(*t)

    # dimensions: line, extension lines, oblique ticks, text
    for d in dr.dims:
        (x1, y1), (x2, y2) = d["p1"], d["p2"]
        st = style("A-ANNO-DIMS")
        if d["angle"] == 0:
            yb = d["base"][1]
            a, b = (x1, yb), (x2, yb)
            for x, y in ((x1, y1), (x2, y2)):
                page.draw_line(P(x, y - 0.05), P(x, yb - 0.10), **st)
            ux, uy = 1.0, 0.0
        else:
            xb = d["base"][0]
            a, b = (xb, y1), (xb, y2)
            for x, y in ((x1, y1), (x2, y2)):
                page.draw_line(P(x - 0.05, y), P(xb - 0.10, y), **st)
            ux, uy = 0.0, 1.0
        page.draw_line(P(*a), P(*b), **st)
        tick = 0.10                       # metres, half length -> 2 mm at 1:100
        for e in (a, b):
            dx, dy = (ux - uy) / math.sqrt(2), (uy + ux) / math.sqrt(2)
            page.draw_line(P(e[0] - dx * tick, e[1] - dy * tick), P(e[0] + dx * tick, e[1] + dy * tick),
                           color=st["color"], width=0.25 * PT, oc=st["oc"])
        label = d["text"] if d["text"] else f"{d['measured']:.2f}".replace(".", ",")
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if d["angle"] == 0:
            text("A-ANNO-DIMS", label, (mid[0], mid[1] + 0.14), 0.18, 0)
        else:
            text("A-ANNO-DIMS", label, (mid[0] - 0.14, mid[1]), 0.18, 90)
    if rotate:
        page.set_rotation(rotate)
    doc.save(path)
    return {"k": k, "ox": margin - minx * k, "oy": margin - miny * k}


def _write_png(pdf: Path, png: Path, dpi: int = 200, noise: float = 0.0, seed: int = 0) -> None:
    import pymupdf

    pix = pymupdf.open(pdf)[0].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    if noise <= 0:
        pix.save(png)
        return
    import numpy as np
    from PIL import Image, ImageFilter

    rng = np.random.default_rng(seed)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).astype(np.float32)
    arr += rng.normal(0, 255 * noise, arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    img = img.rotate(rng.uniform(1, 3), expand=True, fillcolor=255)
    img.save(png, dpi=(dpi, dpi))


def make_suite(out_dir: str | Path, n: int = 120) -> list[dict]:
    """Fixed seeds; every error switch appears on its own plan, plus clean plans."""
    out = []
    keys = list(ERRORS)
    for i in range(n):
        errs = (keys[(i // 2) % len(keys)],) if i % 2 else ()   # every switch in turn
        out.append(make_plan(out_dir, seed=i, errors=errs, png=False))
    return out
