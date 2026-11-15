"""Label-seeded room separation.

Free space left by the wall barrier is sometimes one region that holds several rooms: a wall drawn as two thin lines was
missed, a doorway has no recognised symbol, a facade has a gap. A person still sees the rooms, because each carries its
own name (and often its area). This module uses those names as seeds, the way seeded watershed segmentation is used for
cell images and for floor plans: flood outward from every seed over the distance-to-barrier map, so that two seeds meet
where the free space is narrowest (a doorway, a missing wall piece) and not in the middle of a room.

Nothing here knows a room type or a language. A seed is any text the classifier took for a room label or a stated area;
text lines that stack on top of each other ("BEDROOM" over "SUITE" over "288 SQ FT") are one seed.
The boundaries it draws are inferred, never measured, so the rooms it makes are marked and the edges between them are
recorded with low confidence (see rooms.py).
"""

from __future__ import annotations

import re

import cv2
import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from ..schema import TextItem

STACK_GAP = 2.2          # two text lines belong to one seed when their centres are within this many text heights
SEED_RADIUS_M = 0.25     # the marker drawn at a seed
MAX_PIXELS = 1_800_000   # raster budget for one region
MIN_PIXEL_M = 0.04


def _centre(t: TextItem) -> tuple[float, float]:
    return (t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2


def _height(t: TextItem) -> float:
    # the character height; a rotated run has a tall box, so the short side of the box is the fallback, never the long one
    return max(t.height or min(t.bbox[2] - t.bbox[0], t.bbox[3] - t.bbox[1]), 1e-6)


def seeds_from_texts(texts: list[TextItem]) -> list[dict]:
    """One seed per room: label lines and area lines that sit one above the other are merged. A tag such as "K1" is not a
    seed: a seed needs a name of at least three letters or a stated area."""
    cand = []
    for t in texts:
        if t.kind == "room_label":
            # a short abbreviation with a number attached ("S6" over "13") is a callout or a tag, not a room name
            if sum(ch.isalpha() for ch in t.text) >= 3:
                cand.append(t)
        elif t.kind == "area":
            # an area is written with its unit ("288 SQ FT", "14,5 m2"); a bare number near a tag is not one
            if re.search(r"[A-Za-z²㎡]", t.text):
                cand.append(t)
    # identical duplicates (the same run drawn twice) count once
    uniq, seen = [], set()
    for t in cand:
        key = (t.text, round(t.bbox[0], 1), round(t.bbox[1], 1))
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    parent = list(range(len(uniq)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(uniq):
        ax, ay = _centre(a)
        th = np.radians(a.rotation_deg or 0.0)
        u, v = (np.cos(th), np.sin(th)), (-np.sin(th), np.cos(th))        # along the baseline, and across it
        for j in range(i + 1, len(uniq)):
            b = uniq[j]
            bx, by = _centre(b)
            h = max(_height(a), _height(b))
            length = max(max(a.bbox[2] - a.bbox[0], a.bbox[3] - a.bbox[1]), max(b.bbox[2] - b.bbox[0], b.bbox[3] - b.bbox[1]))
            along = (bx - ax) * u[0] + (by - ay) * u[1]
            across = (bx - ax) * v[0] + (by - ay) * v[1]
            # stacked lines, in the text's own frame: close across the baseline, and the middle of one lies over the other
            if abs(across) <= STACK_GAP * h and abs(along) <= 0.6 * length + h and abs(across) > 0.3 * h:
                parent[find(i)] = find(j)
    groups: dict[int, list[TextItem]] = {}
    for i, t in enumerate(uniq):
        groups.setdefault(find(i), []).append(t)
    seeds = []
    for g in groups.values():
        xs = [_centre(t) for t in g]
        named = [t for t in g if t.kind == "room_label"]
        stated = next((t.value for t in g if t.kind == "area" and t.value is not None), None)
        if stated is None:
            stated = next((t.value for t in g if t.value is not None), None)
        seeds.append({"x": float(np.mean([p[0] for p in xs])), "y": float(np.mean([p[1] for p in xs])),
                      "label": " ".join(t.text for t in sorted(named, key=lambda t: -_centre(t)[1])) or None,
                      "norm": next((t.norm for t in named if t.norm), None), "area_m2": stated,
                      "text_ids": [t.id for t in g]})
    return seeds


MIN_PIECE_M2 = 1.5       # a piece smaller than this is not a room: its seed was a stray text, the piece is given back


def split_region(g: Polygon, seeds: list[dict], mpu: float) -> list[tuple[Polygon, dict | None]]:
    """Split one free-space region among the seeds that lie in it. Returns (polygon, seed) pairs; a region with fewer than
    two seeds comes back whole with its seed (or None). Seeds whose piece comes out too small are dropped and the region is
    split again among the rest."""
    inside = [s for s in seeds if g.contains(Point(s["x"], s["y"]))]
    while True:
        parts = _flood(g, inside, mpu)
        small = [s for q, s in parts if s is not None and q.area * mpu * mpu < MIN_PIECE_M2]
        if not small or len(inside) - len(small) < 1 or len(parts) < 2:
            return parts
        inside = [s for s in inside if all(s is not x for x in small)]


def _flood(g: Polygon, inside: list[dict], mpu: float) -> list[tuple[Polygon, dict | None]]:
    if len(inside) < 2:
        return [(g, inside[0] if inside else None)]
    x0, y0, x1, y1 = g.bounds
    step = max(MIN_PIXEL_M / mpu, np.sqrt((x1 - x0) * (y1 - y0) / MAX_PIXELS))
    w, h = int((x1 - x0) / step) + 3, int((y1 - y0) / step) + 3

    def to_px(x, y):
        return int(round((x - x0) / step)) + 1, int(round((y1 - y) / step)) + 1

    mask = np.zeros((h, w), np.uint8)
    for poly in getattr(g, "geoms", [g]):
        ext = np.array([to_px(x, y) for x, y in poly.exterior.coords], np.int32)
        cv2.fillPoly(mask, [ext], 1)
        for ring in poly.interiors:
            cv2.fillPoly(mask, [np.array([to_px(x, y) for x, y in ring.coords], np.int32)], 0)
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    markers = np.zeros((h, w), np.int32)
    r = max(1, int(SEED_RADIUS_M / mpu / step))
    placed = []
    for k, s in enumerate(inside, 1):
        px, py = to_px(s["x"], s["y"])
        if not (0 <= py < h and 0 <= px < w) or not mask[py, px]:      # a label drawn over a wall: nearest free pixel
            ys, xs = np.nonzero(mask)
            if len(xs) == 0:
                continue
            i = int(np.argmin((xs - px) ** 2 + (ys - py) ** 2))
            px, py = int(xs[i]), int(ys[i])
        cv2.circle(markers, (px, py), r, k, -1)
        placed.append((k, s))
    markers[mask == 0] = 0
    from skimage.segmentation import watershed

    lab = watershed(-dist, markers, mask=mask.astype(bool))
    out = []
    for k, s in placed:
        region = (lab == k).astype(np.uint8)
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        polys = []
        for c in contours:
            if len(c) < 3:
                continue
            pts = [(x0 + (px - 1) * step, y1 - (py - 1) * step) for px, py in c[:, 0, :]]
            q = Polygon(pts).buffer(0)
            if not q.is_empty:
                polys.append(q)
        if not polys:
            continue
        piece = unary_union(polys).buffer(step * 0.6, join_style="mitre").intersection(g)
        parts = [q for q in getattr(piece, "geoms", [piece]) if q.geom_type == "Polygon" and not q.is_empty]
        if parts:
            out.append((max(parts, key=lambda q: q.area).simplify(step * 0.5), s))
    return out or [(g, None)]
