"""Vector strokes of a page: the drawing primitives the symbol finder works on.

A PDF "path" can hold a whole layer. It is cut here into strokes: chains of items that follow each other end to end
(rectangles and quads are closed chains of their own). A curve is flattened to a short polyline. Everything is in the
displayed frame of the page, the frame the drawing set model uses, so view boxes and legend boxes apply directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CURVE_STEPS = 8
JOIN_TOL = 0.05


@dataclass
class Stroke:
    pts: np.ndarray            # (n, 2) polyline
    filled: bool = False
    closed: bool = False
    width: float = 0.0

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (float(self.pts[:, 0].min()), float(self.pts[:, 1].min()), float(self.pts[:, 0].max()), float(self.pts[:, 1].max()))

    @property
    def length(self) -> float:
        return float(np.hypot(*np.diff(self.pts, axis=0).T).sum())


def _bezier(p0, p1, p2, p3, n: int = CURVE_STEPS) -> np.ndarray:
    t = np.linspace(0, 1, n + 1)[:, None]
    a, b, c, d = (np.array([p.x, p.y]) for p in (p0, p1, p2, p3))
    return (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d


def _item_chains(items) -> list[list[np.ndarray]]:
    """Items of one path as chains of point arrays that join end to end."""
    chains: list[list[np.ndarray]] = []
    cur: list[np.ndarray] = []
    last = None
    for it in items:
        kind = it[0]
        if kind in ("re", "qu"):
            if cur:
                chains.append(cur)
                cur, last = [], None
            if kind == "re":
                r = it[1]
                ring = np.array([[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1], [r.x0, r.y0]])
            else:
                q = it[1]
                ring = np.array([[p.x, p.y] for p in (q.ul, q.ur, q.lr, q.ll, q.ul)])
            chains.append([ring])
            continue
        if kind == "l":
            pts = np.array([[it[1].x, it[1].y], [it[2].x, it[2].y]])
        elif kind == "c":
            pts = _bezier(it[1], it[2], it[3], it[4])
        else:
            continue
        if last is not None and np.hypot(*(pts[0] - last)) <= JOIN_TOL:
            cur.append(pts)
        else:
            if cur:
                chains.append(cur)
            cur = [pts]
        last = pts[-1]
    if cur:
        chains.append(cur)
    return chains


def _is_invisible(d: dict) -> bool:
    fill, color = d.get("fill"), d.get("color")
    if d.get("type") == "clip":
        return True
    return color is None and fill is not None and all(c >= 0.98 for c in fill)   # a white fill hides, it does not draw


def strokes_of_page(page, turns: int = 0) -> list[Stroke]:
    """All strokes of a pymupdf page in the displayed frame (rotation applied), turned `turns` quarter turns clockwise."""
    m = page.rotation_matrix
    H = page.rect.height
    out: list[Stroke] = []
    for d in page.get_drawings():
        if _is_invisible(d) or not d.get("items"):
            continue
        filled = d.get("fill") is not None
        width = float(d.get("width") or 0.0)
        for chain in _item_chains(d["items"]):
            pts = np.vstack([chain[0]] + [c[1:] for c in chain[1:]])
            if len(pts) < 2:
                continue
            pts = np.stack([pts[:, 0] * m.a + pts[:, 1] * m.c + m.e, pts[:, 0] * m.b + pts[:, 1] * m.d + m.f], axis=1)
            closed = bool(np.hypot(*(pts[0] - pts[-1])) <= JOIN_TOL and len(pts) > 3)
            out.append(Stroke(pts, filled and closed, closed, width))
    return rotate_strokes(out, turns, H, page.rect.width) if turns else out


def rotate_strokes(strokes: list[Stroke], turns: int, height: float, width: float) -> list[Stroke]:
    """Quarter turns clockwise, the same map as the drawing set model uses (x' = H - y, y' = x)."""
    for _ in range(turns % 4):
        strokes = [Stroke(np.stack([height - s.pts[:, 1], s.pts[:, 0]], axis=1), s.filled, s.closed, s.width) for s in strokes]
        height, width = width, height
    return strokes


def frame_turns(page, pagedata, strokes: list[Stroke]) -> int:
    """How many quarter turns the drawing set model applied to this page (it puts text upright), found by comparing the extent
    of all path boxes of the page data with the extent of the strokes after each candidate turn."""
    r = pagedata.rects
    if not len(r) or not strokes:
        return 0
    want = np.array([r[:, 0].min(), r[:, 1].min(), r[:, 2].max(), r[:, 3].max()])
    best, best_err = 0, None
    for k in range(4):
        t = rotate_strokes(strokes, k, page.rect.height, page.rect.width) if k else strokes
        allp = np.vstack([s.pts for s in t])
        got = np.array([allp[:, 0].min(), allp[:, 1].min(), allp[:, 0].max(), allp[:, 1].max()])
        err = float(np.abs(got - want).max())
        if best_err is None or err < best_err - 1e-6:
            best, best_err = k, err
    return best


def inside(box, region, tol: float = 0.0) -> bool:
    return box[0] >= region[0] - tol and box[1] >= region[1] - tol and box[2] <= region[2] + tol and box[3] <= region[3] + tol


def union_box(boxes) -> tuple[float, float, float, float]:
    a = np.asarray(list(boxes), dtype=float)
    return (float(a[:, 0].min()), float(a[:, 1].min()), float(a[:, 2].max()), float(a[:, 3].max()))
