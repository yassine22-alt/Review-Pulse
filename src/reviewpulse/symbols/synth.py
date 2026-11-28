"""Generated drawings with the truth known by construction: a legend of 6 to 12 symbols and a plan with rooms, symbols planted
at known places, turns, sizes and line weights, and distractors (door swings, fixtures, columns, text boxes, plain circles).

Drawn with pymupdf shapes, so the PDF has real vector paths and a text layer, and goes through the same readers as a real set.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pymupdf

WORDS = ["SMOKE ALARM", "CARBON MONOXIDE ALARM", "EXHAUST FAN", "JUNCTION BOX", "DUPLEX OUTLET", "GFCI OUTLET",
         "DATA JACK", "THERMOSTAT", "SUPPLY REGISTER", "RETURN GRILLE", "CEILING FAN", "WALL SCONCE"]
ROOM_NAMES = ["BEDROOM 1", "BEDROOM 2", "KITCHEN", "LIVING ROOM", "BATH", "HALL", "DINING ROOM", "OFFICE", "LAUNDRY", "GARAGE",
              "STUDY", "PANTRY"]
BASE_R = 7.0                        # symbol radius in the legend, page points


def _ngon(n, r=1.0, a0=0.0):
    return [(r * math.cos(a0 + 2 * math.pi * k / n), r * math.sin(a0 + 2 * math.pi * k / n)) for k in range(n)]


def _arc(r, a0, a1, n=12):
    return [(r * math.cos(a0 + (a1 - a0) * k / n), r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


# a glyph is a list of ops in unit coordinates: ("circle", cx, cy, r, filled), ("line", p, q), ("poly", pts, closed, filled)
GLYPHS: list[list[tuple]] = [
    [("circle", 0, 0, 1, False), ("line", (-.6, 0), (.6, 0)), ("line", (0, -.6), (0, .6))],                       # 0 circle, plus
    [("circle", 0, 0, 1, False), ("circle", 0, 0, .3, True)],                                                       # 1 circle, dot
    [("poly", [(-1, -1), (1, -1), (1, 1), (-1, 1)], True, False), ("line", (-1, -1), (1, 1))],                      # 2 square, diagonal
    [("poly", _ngon(3, 1.2, math.pi / 2), True, False)],                                                            # 3 triangle
    [("circle", 0, 0, 1, False), ("circle", 0, 0, .55, False)],                                                     # 4 double circle
    [("poly", [(-1, -1), (1, -1), (1, 1), (-1, 1)], True, False), ("circle", 0, 0, .5, False)],                     # 5 square, circle
    [("poly", _ngon(6, 1.05), True, False)],                                                                        # 6 hexagon
    [("poly", [(-1, -1), (1, -1), (1, 1), (-1, 1)], True, False), ("line", (-1, -1), (1, 1)), ("line", (-1, 1), (1, -1))],
    [("circle", 0, 0, .8, False), ("line", (-1.3, 0), (1.3, 0))],                                                   # 8 circle, bar
    [("poly", [(0, -1.2), (1.2, 0), (0, 1.2), (-1.2, 0)], True, False)],                                            # 9 diamond
    [("line", (-1, 0), (1, 0)), ("line", (-.5, -.87), (.5, .87)), ("line", (-.5, .87), (.5, -.87))],               # 10 asterisk
    [("poly", _arc(1, -math.pi / 2, math.pi / 2), True, False)],                                                    # 11 half disc
]


def distractors(kind: int) -> list[tuple]:
    """Things that are drawn on plans and are not in the legend, in unit coordinates of their own size."""
    if kind == 0:                      # door swing: leaf and quarter arc
        return [("line", (0, 0), (0, -1)), ("poly", _arc(1, -math.pi / 2, 0, 10), False, False)]
    if kind == 1:                      # toilet: tank and bowl
        return [("poly", [(-.5, -1), (.5, -1), (.5, -.5), (-.5, -.5)], True, False),
                ("poly", [(0.5 * math.cos(a), 0.2 + 0.7 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 17)[:-1]], True, False)]
    if kind == 2:                      # sink: basin with drain
        return [("poly", [(-1, -.7), (1, -.7), (1, .7), (-1, .7)], True, False), ("circle", 0, 0, .15, False)]
    if kind == 3:                      # column
        return [("poly", [(-.6, -.6), (.6, -.6), (.6, .6), (-.6, .6)], True, True)]
    if kind == 4:                      # plain circle (a column or a tree)
        return [("circle", 0, 0, 1, False)]
    if kind == 5:                      # long thin box (counter) with a line
        return [("poly", [(-2.5, -.6), (2.5, -.6), (2.5, .6), (-2.5, .6)], True, False), ("line", (-2.5, 0), (2.5, 0))]
    if kind == 6:                      # dimension end ticks
        return [("line", (-1, 0), (1, 0)), ("line", (-1, -.4), (-1, .4)), ("line", (1, -.4), (1, .4))]
    # near misses: close to a legend symbol but not in the legend, so the finder must say "not in the legend"
    if kind == 7:                      # circle with four spokes
        return GLYPHS[0] + [("line", (-.42, -.42), (.42, .42)), ("line", (-.42, .42), (.42, -.42))]
    if kind == 8:                      # square with a plus
        return [("poly", [(-1, -1), (1, -1), (1, 1), (-1, 1)], True, False), ("line", (-.6, 0), (.6, 0)), ("line", (0, -.6), (0, .6))]
    return [("poly", _ngon(3, 1.2, math.pi / 2), True, False), ("circle", 0, .1, .25, True)]   # triangle with a dot


def _xf(p, th, s, c):
    x, y = p[0] * s, p[1] * s
    return (c[0] + x * math.cos(th) - y * math.sin(th), c[1] + x * math.sin(th) + y * math.cos(th))


def draw_glyph(page, ops, centre, size, theta=0.0, width=1.0, circles_as_polygons=False, color=(0, 0, 0)) -> tuple:
    """Draw ops as one path; returns the box of the drawn geometry (the strokes' own extent)."""
    sh = page.new_shape()
    pts_all = []
    fill_any = None
    for op in ops:
        if op[0] == "circle":
            _, cx, cy, r, filled = op
            c = _xf((cx, cy), theta, size, centre)
            if circles_as_polygons:
                poly = [(c[0] + r * size * math.cos(a), c[1] + r * size * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 25)]
                sh.draw_polyline([pymupdf.Point(*p) for p in poly])
            else:
                sh.draw_circle(pymupdf.Point(*c), r * size)
            pts_all += [(c[0] - r * size, c[1] - r * size), (c[0] + r * size, c[1] + r * size)]
            if filled:
                fill_any = color
        elif op[0] == "line":
            p, q = _xf(op[1], theta, size, centre), _xf(op[2], theta, size, centre)
            sh.draw_line(pymupdf.Point(*p), pymupdf.Point(*q))
            pts_all += [p, q]
        else:
            _, pts, closed, filled = op
            tp = [_xf(p, theta, size, centre) for p in pts]
            if closed:
                tp = tp + [tp[0]]
            sh.draw_polyline([pymupdf.Point(*p) for p in tp])
            pts_all += tp
            if filled:
                fill_any = color
    sh.finish(width=width, color=color, fill=fill_any, closePath=False)
    sh.commit()
    a = np.array(pts_all)
    return (float(a[:, 0].min()), float(a[:, 1].min()), float(a[:, 0].max()), float(a[:, 1].max()))


@dataclass
class Truth:
    legend: list[dict] = field(default_factory=list)        # row, glyph, words, box
    instances: list[dict] = field(default_factory=list)     # glyph, label, box, centre, room, theta, size, width
    rooms: list[dict] = field(default_factory=list)         # id, polygon, label
    distractors: list[dict] = field(default_factory=list)
    unlisted: list[dict] = field(default_factory=list)      # planted symbols whose glyph is not in the legend
    plan_box: tuple = (0, 0, 0, 0)
    page: tuple = (0, 0)


def make_pdf(path, seed: int = 0, n_symbols: int = 8, per_symbol: tuple[int, int] = (3, 6), instance_scale: float = 1.0,
             legend_perm: tuple | None = None, circles_as_polygons: bool = False, page_scale: float = 1.0,
             shift: tuple[float, float] = (0.0, 0.0), page_rotation: int = 0, line_weights=(0.5, 1.6),
             n_distractors: int = 3, cols: int = 3, rows: int = 3, angles: str = "free", near_miss: bool = True,
             wall_touch: float = 0.0, legend_n: int | None = None) -> Truth:
    """One sheet: legend on the left, floor plan on the right. All lengths are in page points at page_scale 1."""
    rng = np.random.default_rng(seed)
    k = page_scale
    W, H = 1224 * k, 792 * k
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    tr = Truth(page=(W, H))
    ox, oy = shift

    def P(x, y):
        return (x * k + ox, y * k + oy)

    # glyph for each legend row; legend_perm changes which glyph a row shows (the words stay)
    legend_n = n_symbols if legend_n is None else legend_n
    glyph_of_row = list(range(legend_n)) if legend_perm is None else list(legend_perm)
    page.insert_text(pymupdf.Point(*P(40, 60)), "LEGEND", fontsize=16 * k, fontname="helv")
    for i in range(legend_n):
        y = 100 + i * 42
        g = glyph_of_row[i]
        c = P(70, y)
        box = draw_glyph(page, GLYPHS[g], c, BASE_R * k, 0.0, 1.0)
        page.insert_text(pymupdf.Point(*P(105, y + 4)), WORDS[i], fontsize=10 * k, fontname="helv")
        tr.legend.append({"row": i, "glyph": g, "words": WORDS[i], "box": box})
    label_of_glyph = {g: WORDS[i] for i, g in enumerate(glyph_of_row)}

    # plan: a grid of rooms
    px0, py0, px1, py1 = 330, 90, 1170, 720
    page.insert_text(pymupdf.Point(*P(px0, 60)), "FIRST FLOOR PLAN", fontsize=16 * k, fontname="helv")
    page.insert_text(pymupdf.Point(*P(px0 + 250, 60)), "SCALE: 1/4\" = 1'-0\"", fontsize=10 * k, fontname="helv")
    tr.plan_box = (*P(px0 - 10, 40), *P(px1 + 10, py1 + 10))
    cw, ch = (px1 - px0) / cols, (py1 - py0) / rows
    sh = page.new_shape()
    for r in range(rows + 1):
        sh.draw_line(pymupdf.Point(*P(px0, py0 + r * ch)), pymupdf.Point(*P(px1, py0 + r * ch)))
    for c in range(cols + 1):
        sh.draw_line(pymupdf.Point(*P(px0 + c * cw, py0)), pymupdf.Point(*P(px0 + c * cw, py1)))
    sh.finish(width=3 * k, color=(0, 0, 0))
    sh.commit()
    rooms = []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = px0 + c * cw, py0 + r * ch
            poly = [P(x0 + 2, y0 + 2), P(x0 + cw - 2, y0 + 2), P(x0 + cw - 2, y0 + ch - 2), P(x0 + 2, y0 + ch - 2)]
            rid = f"R{r * cols + c + 1}"
            name = ROOM_NAMES[(r * cols + c) % len(ROOM_NAMES)]
            page.insert_text(pymupdf.Point(*P(x0 + 8, y0 + 18)), name, fontsize=8 * k, fontname="helv")
            rooms.append((rid, (x0, y0, x0 + cw, y0 + ch)))
            tr.rooms.append({"id": rid, "polygon": poly, "label": name})

    placed: list[tuple] = []        # centres and radii already used

    def free(cx, cy, rad):
        return all(math.hypot(cx - a, cy - b) > rad + rr + 6 for a, b, rr in placed)

    def spot(room, rad):
        x0, y0, x1, y1 = room
        for _ in range(200):
            cx = rng.uniform(x0 + rad + 8, x1 - rad - 8)
            cy = rng.uniform(y0 + rad + 26, y1 - rad - 8)
            if wall_touch and rng.random() < wall_touch:
                cx = x0 + rad / 1.6 + 1.6          # the symbol rests against the wall line
            if free(cx, cy, rad):
                return cx, cy
        return None

    for rid, room in rooms:
        for _ in range(n_distractors):
            kind = int(rng.integers(0, 10 if near_miss else 7))
            size = float(rng.uniform(7, 14))
            pos = spot(room, size * 2.6)
            if pos is None:
                continue
            placed.append((*pos, size * 2.6))
            th = float(rng.choice([0, math.pi / 2, math.pi, 3 * math.pi / 2]))
            c = P(*pos)
            box = draw_glyph(page, distractors(kind), c, size * k, th, float(rng.uniform(*line_weights)))
            if kind == 5:
                page.insert_text(pymupdf.Point(c[0] - 6, c[1] + 3 * k), "BOX", fontsize=6 * k, fontname="helv")
            tr.distractors.append({"kind": kind, "box": box, "room": rid})
    for g in range(n_symbols):
        for _ in range(int(rng.integers(per_symbol[0], per_symbol[1] + 1))):
            rid, room = rooms[int(rng.integers(0, len(rooms)))]
            size = BASE_R * instance_scale * float(rng.uniform(0.85, 1.25))
            pos = spot(room, size * 1.6)
            if pos is None:
                continue
            placed.append((*pos, size * 1.6))
            if angles == "free":
                th = float(rng.uniform(0, 2 * math.pi)) if rng.random() < 0.5 else float(rng.choice([0, 1, 2, 3])) * math.pi / 2
            else:
                th = 0.0
            wd = float(rng.uniform(*line_weights))
            c = P(*pos)
            box = draw_glyph(page, GLYPHS[g], c, size * k, th, wd, circles_as_polygons)
            rec = {"glyph": g, "label": label_of_glyph.get(g), "box": box, "centre": c, "room": rid, "theta": th,
                   "size": size * k, "width": wd}
            (tr.instances if g in label_of_glyph else tr.unlisted).append(rec)
    if page_rotation:
        page.set_rotation(page_rotation)
    doc.save(str(path))
    doc.close()
    return tr
