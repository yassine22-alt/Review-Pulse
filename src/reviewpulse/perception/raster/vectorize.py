"""Masks -> Elements in sheet space (R13 step 3).

Walls: the wall mask is kept as a polygon barrier (rooms are built from it directly) and
skeletonised into centrelines (Douglas-Peucker at a quarter thickness) with thickness = 2 x the
median distance-transform value along the path, confidence = mean class probability.
Doors and windows: connected components -> minimum rotated rectangles, oriented across the wall.
"""

from __future__ import annotations

import numpy as np
from shapely.affinity import affine_transform
from shapely.geometry import LineString, MultiPolygon, Polygon, shape
from shapely.ops import unary_union

from ...core.ids import IdFactory
from ...schema import Element, Prov


def mask_polygons(mask: np.ndarray, min_area_px: float = 20.0):
    """Union of the mask's pixel polygons (rasterio-free: via skimage contours)."""
    from skimage import measure

    polys = []
    padded = np.pad(mask.astype(np.uint8), 1)
    for c in measure.find_contours(padded, 0.5):
        if len(c) < 4:
            continue
        p = Polygon([(x - 1, y - 1) for y, x in c]).buffer(0)
        if p.area >= min_area_px:
            polys.append(p)
    if not polys:
        return Polygon()
    # contours of holes come back as separate rings: even-odd combine by area order
    polys.sort(key=lambda p: -p.area)
    out = Polygon()
    for p in polys:
        out = out.symmetric_difference(p) if out.contains(p.representative_point()) else out.union(p)
    return out.buffer(0)


def _to_sheet(geom, affine):
    a, b, c, d, e, f = affine
    return affine_transform(geom, [a, b, d, e, c, f])


def skeleton_branches(skel: np.ndarray) -> list[np.ndarray]:
    """Split a 1-px skeleton into branches between junctions / endpoints; each branch is an ordered
    (N, 2) array of (x, y) pixel coordinates."""
    from scipy import ndimage

    sk = skel.astype(bool)
    nb = ndimage.convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - 1
    nodes = sk & (nb != 2)                       # endpoints (1) and junctions (>=3)
    body = sk & ~nodes
    lab, n = ndimage.label(body, structure=np.ones((3, 3)))
    out = []
    H, W = sk.shape
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        pix = set(zip(ys.tolist(), xs.tolist()))
        # start from a pixel with a single neighbour inside the branch (or any pixel for loops)
        def nbrs(p, pix=pix):
            y, x = p
            return [(y + dy, x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if (dy or dx) and (y + dy, x + dx) in pix]
        start = next((p for p in pix if len(nbrs(p)) <= 1), next(iter(pix)))
        order, seen, cur = [start], {start}, start
        while True:
            nxt = [q for q in nbrs(cur) if q not in seen]
            if not nxt:
                break
            cur = nxt[0]
            seen.add(cur)
            order.append(cur)
        # attach the adjacent node pixels so branches meet at junctions
        ends = []
        for p in (order[0], order[-1]):
            y, x = p
            js = [(y + dy, x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                  if 0 <= y + dy < H and 0 <= x + dx < W and nodes[y + dy, x + dx]]
            ends.append(js[0] if js else None)
        pts = ([ends[0]] if ends[0] else []) + order + ([ends[1]] if ends[1] else [])
        out.append(np.array([(x, y) for y, x in pts], float))
    return out


def wall_elements(wall_mask: np.ndarray, prob: np.ndarray | None, affine, sheet_id: str,
                  source: str, stage: str) -> list[Element]:
    from scipy import ndimage
    from skimage.morphology import skeletonize

    ids = IdFactory(sheet_id)
    if wall_mask.sum() == 0:
        return []
    dt = ndimage.distance_transform_edt(wall_mask)
    out = []
    mm_per_px = abs(affine[0])
    for br in skeleton_branches(skeletonize(wall_mask)):
        if len(br) < 3:
            continue
        xs, ys = br[:, 0].astype(int), br[:, 1].astype(int)
        t_px = float(2 * np.median(dt[ys, xs]))
        if len(br) * 1.0 < max(2.0, t_px):              # spur shorter than the wall is thick
            continue
        line = LineString(br).simplify(max(1.0, t_px / 4))
        coords = list(line.coords)
        conf = float(prob[ys, xs].mean()) if prob is not None else 0.8
        for a_, b_ in zip(coords, coords[1:]):
            seg = _to_sheet(LineString([a_, b_]), affine)
            if seg.length <= 0:
                continue
            g = [tuple(round(v, 4) for v in seg.coords[0]), tuple(round(v, 4) for v in seg.coords[1])]
            out.append(Element(id=ids("wall", g), cls="wall", geom=g, thickness=round(t_px * mm_per_px, 4),
                               attrs={"source": source, "thickness_px": round(t_px, 2)},
                               prov=Prov(source="raster", stage=stage, confidence=round(conf, 3))))
    return out


FILL_MIN = 0.6         # pixels / rotated-rectangle area of a clean door or window blob


def _rect(ys, xs):
    mp = MultiPolygon([Polygon([(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]) for x, y in zip(xs, ys)])
    return unary_union(mp.geoms).minimum_rotated_rectangle


def opening_parts(mask: np.ndarray, min_px: int = 12) -> list[tuple[np.ndarray, np.ndarray, Polygon]]:
    """Connected opening blobs as (ys, xs, rotated rectangle) in pixels.

    A door or window is a compact bar across a wall. A blob that also took in thin strokes (stair
    treads, terrace lines, a hatch) fills its rectangle poorly and its rectangle balloons; such a blob
    is opened with a disk sized from its own core thickness, which removes strokes thinner than the
    bar, and each surviving part becomes its own rectangle."""
    from scipy import ndimage

    lab, n = ndimage.label(mask)
    out = []
    for k in range(1, n + 1):
        comp = lab == k
        ys, xs = np.nonzero(comp)
        if len(xs) < min_px:
            continue
        rect = _rect(ys, xs)
        if len(xs) >= FILL_MIN * rect.area:
            out.append((ys, xs, rect))
            continue
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        sub = np.pad(comp[y0:y1, x0:x1], 1)
        core = 2.0 * float(ndimage.distance_transform_edt(sub).max())
        r = max(1, int(round(0.3 * core)))
        disk = np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r
        kept = ndimage.binary_opening(sub, structure=disk)
        plab, pn = ndimage.label(kept)
        for j in range(1, pn + 1):
            py, px = np.nonzero(plab == j)
            if len(px) < min_px:
                continue
            py, px = py + y0 - 1, px + x0 - 1
            out.append((py, px, _rect(py, px)))
    return out


def opening_elements(mask: np.ndarray, cls: str, prob: np.ndarray | None, affine, sheet_id: str,
                     mpu: float | None, stage: str, min_px: int = 12) -> list[Element]:

    ids = IdFactory(sheet_id + ":" + cls)
    out = []
    for ys, xs, rect in opening_parts(mask, min_px):
        poly = _to_sheet(rect, affine)
        if poly.geom_type != "Polygon" or poly.area <= 0:
            continue
        cs = list(poly.exterior.coords)[:4]
        e0 = np.subtract(cs[1], cs[0])
        e1 = np.subtract(cs[2], cs[1])
        long_, short = (e0, e1) if np.linalg.norm(e0) >= np.linalg.norm(e1) else (e1, e0)
        t = float(np.linalg.norm(short))
        nrm = short / (t or 1.0)
        mid = (poly.centroid.x, poly.centroid.y)
        width = float(np.linalg.norm(long_))
        conf = float(prob[ys, xs].mean()) if prob is not None else 0.7
        attrs = {"mid": mid, "normal": (float(nrm[0]), float(nrm[1])), "thickness": t,
                 "width_m": round(width * mpu, 4) if mpu else None, "source": "raster"}
        if conf < 0.9:
            attrs["needs_confirmation"] = True
        g = [tuple(round(v, 4) for v in q) for q in cs]
        out.append(Element(id=ids(cls, g), cls=cls, geom=g, attrs=attrs,
                           prov=Prov(source="raster", stage=stage, confidence=round(conf, 3))))
    return out


def barrier_from_masks(wall_mask: np.ndarray, door_mask: np.ndarray, window_mask: np.ndarray, affine):
    """Barrier polygon in sheet space: walls plus closed openings (connectivity comes from probes)."""
    geom = mask_polygons(wall_mask | door_mask | window_mask)
    return _to_sheet(geom, affine) if not geom.is_empty else geom


__all__ = ["wall_elements", "opening_elements", "barrier_from_masks", "mask_polygons", "shape"]
