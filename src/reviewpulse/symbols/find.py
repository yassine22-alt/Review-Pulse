"""Find the instances of legend symbols in a plan view from their vector shape alone.

1. An exemplar is the group of strokes inside the symbol box of a legend entry (the box comes from the drawing set model).
2. Candidates are connected groups of small strokes in the view: strokes whose boxes lie within a gap of each other,
   at three gaps, kept when the group's box has the size of the exemplar (a band around it, moved by the view scale when
   both scales are known). Long strokes (walls) are left out before grouping, so a symbol drawn against a wall is still
   a group of its own.
3. Each candidate is described (descriptor.py) and compared with every exemplar. The nearest exemplar is its label, if the
   distance is within the exemplar's threshold. The threshold is calibrated on the legend itself: distances between the
   exemplar and copies of it that are turned, rescaled, re-cut and jittered, capped by half the distance to the nearest
   other exemplar. A candidate further than its threshold is "not in the legend" and is dropped. A candidate whose second
   nearest exemplar is almost as near is kept apart as ambiguous, not counted.
4. Overlapping accepted candidates are thinned, nearest first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.strtree import STRtree

from .descriptor import Descriptor, describe, distance, signature_hash
from .primitives import Stroke, union_box

GAPS = (0.0, 0.06, 0.15)          # as a share of the exemplar's box diagonal
BAND = (0.5, 2.0)
MAX_STROKES = 60
EXEMPLAR_DIAG = (3.0, 90.0)       # page points: smaller is a dot or a speck, larger is a detail
EXEMPLAR_ASPECT = 5.0             # longer than this is a line swatch, a hatch or a leader, not a point symbol
AMBIGUITY_MARGIN = 0.02
TAU_FLOOR, TAU_CEIL = 0.04, 0.30
JITTER = 0.003                    # vertex noise of the calibration copies, as a share of the box diagonal


@dataclass
class Exemplar:
    id: int
    words: list[str]
    sheet: int
    view: str
    box: tuple[float, float, float, float]
    strokes: list[Stroke]
    desc: Descriptor
    hash: str | None
    legend_rows: list[int] = field(default_factory=list)
    tau: float = 0.1
    nearest_other: float | None = None
    scale_mpp: float | None = None       # metres per point of the legend's view, when known

    @property
    def label(self) -> str:
        return " / ".join(dict.fromkeys(self.words))

    @property
    def size(self) -> float:
        return self.desc.diag


@dataclass
class Detection:
    exemplar: int
    box: tuple[float, float, float, float]
    dist: float
    tau: float
    runner_up: tuple[int, float] | None = None
    ambiguous: bool = False

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)

    @property
    def score(self) -> float:
        """Higher for a nearer match. A ranking, not a calibrated probability."""
        return float(np.clip(0.95 - 0.45 * self.dist / max(self.tau, 1e-9), 0.05, 0.95))


@dataclass
class FindResult:
    detections: list[Detection] = field(default_factory=list)
    ambiguous: list[Detection] = field(default_factory=list)
    n_candidates: int = 0
    n_not_in_legend: int = 0


# ---- exemplars -----------------------------------------------------------------------------------------------------

def strokes_in(strokes: list[Stroke], box, grow: float = 0.15) -> list[Stroke]:
    """The strokes of a symbol box: those whose box centre lies in the legend box grown by a share of its size, and that are
    not much larger than the box (a leader line or a frame passing through is not part of the symbol)."""
    w, h = box[2] - box[0], box[3] - box[1]
    gx, gy = grow * max(w, h) + 0.5, grow * max(w, h) + 0.5
    cap = 2.5 * float(np.hypot(w, h)) + 1.0
    out = []
    for s in strokes:
        b = s.bbox
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if box[0] - gx <= cx <= box[2] + gx and box[1] - gy <= cy <= box[3] + gy and float(np.hypot(b[2] - b[0], b[3] - b[1])) <= cap:
            out.append(s)
    return out


def _add_exemplar(ex, rejected, i, words, ss, e, mpp):
    if len(ss) > MAX_STROKES:
        rejected.append((i, f"{len(ss)} strokes, a pattern"))
        return
    d = describe(ss)
    if d is None:
        rejected.append((i, "no shape"))
        return
    w, h = d.box[2] - d.box[0], d.box[3] - d.box[1]
    if not EXEMPLAR_DIAG[0] <= d.diag <= EXEMPLAR_DIAG[1]:
        rejected.append((i, f"size {d.diag:.0f} pt outside the symbol band"))
        return
    if max(w, h) / max(min(w, h), 1e-6) > EXEMPLAR_ASPECT:
        rejected.append((i, "line swatch or hatch (aspect), not a point symbol"))
        return
    for g in ex:
        if g.sheet == e.sheet and distance(g.desc, d) < 0.01 and 0.8 < g.size / d.diag < 1.25:
            if words not in g.words:
                g.words.append(words)
            g.legend_rows.append(i)
            return
    ex.append(Exemplar(len(ex), [words], e.sheet, e.view, d.box, ss, d, signature_hash(ss), [i], scale_mpp=mpp))


def _split_row(ss: list[Stroke], words: str, box) -> list[tuple[str, list[Stroke]]] | None:
    """A legend row that shows several symbols for words like "SMOKE DETECTOR / THERMOSTAT / GAS": when the strokes fall into as
    many separate groups as the words have parts, the groups in reading order take the parts in order. None when the row
    is not of that kind (one symbol, or the counts disagree)."""
    parts = [p.strip() for p in words.split("/") if p.strip()]
    h = box[3] - box[1]
    w = box[2] - box[0]
    if len(parts) < 2 or w < 2.2 * max(h, 1.0):
        return None
    small = [s for s in ss if np.hypot(s.bbox[2] - s.bbox[0], s.bbox[3] - s.bbox[1]) <= max(3.0 * h, 30.0)]
    if len(small) < 2:
        return None
    boxes = np.array([s.bbox for s in small])
    lab = _components(boxes, 0.35 * max(h, 6.0))
    groups = [[small[k] for k in np.flatnonzero(lab == g)] for g in np.unique(lab)]
    groups.sort(key=lambda g: min(s.bbox[0] for s in g))
    if len(groups) != len(parts):
        return None
    return list(zip(parts, groups, strict=True))


def build_exemplars(entries, strokes_by_sheet: dict[int, list[Stroke]], scale_by_view: dict[str, float | None] | None = None):
    """Exemplars from the legend entries of a drawing set. Returns (exemplars, rejected) where rejected lists
    (entry index, reason): no symbol box, not a point symbol (a line swatch or a hatch), too small or too large, too busy."""
    ex: list[Exemplar] = []
    rejected: list[tuple[int, str]] = []
    for i, e in enumerate(entries):
        if e.symbol_bbox is None:
            rejected.append((i, "no symbol box"))
            continue
        ss = strokes_in(strokes_by_sheet.get(e.sheet, []), e.symbol_bbox)
        if not ss:
            rejected.append((i, "no strokes in the box"))
            continue
        parts = _split_row(ss, e.words, e.symbol_bbox)
        if parts is not None:
            for words, sub in parts:
                _add_exemplar(ex, rejected, i, words, sub, e, (scale_by_view or {}).get(e.view))
            continue
        _add_exemplar(ex, rejected, i, e.words, ss, e, (scale_by_view or {}).get(e.view))
    calibrate(ex)
    return ex, rejected


def _augment(strokes: list[Stroke], rng: np.random.Generator, diag: float) -> list[Stroke]:
    th = rng.uniform(0, 2 * np.pi)
    sc = rng.uniform(0.7, 1.4)
    rot = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    flip = rng.random() < 0.5
    out = []
    for s in strokes:
        p = s.pts
        if rng.random() < 0.5 and len(p) >= 2:                     # cut the strokes differently: add midpoints
            mid = (p[:-1] + p[1:]) / 2
            q = np.empty((len(p) + len(mid), 2))
            q[0::2], q[1::2] = p, mid
            p = q
        p = p @ rot.T * sc
        if flip:
            p = p * np.array([1.0, -1.0])
        p = p + rng.normal(0, JITTER * diag * sc, p.shape)
        out.append(Stroke(p, s.filled, s.closed, s.width))
    return out


def calibrate(ex: list[Exemplar], n: int = 24, seed: int = 0) -> None:
    """Set each exemplar's threshold from the legend alone (see the module note)."""
    rng = np.random.default_rng(seed)
    for e in ex:
        ds = []
        for _ in range(n):
            d = describe(_augment(e.strokes, rng, e.size))
            if d is not None:
                ds.append(distance(e.desc, d))
        pos = float(np.quantile(ds, 0.95)) if ds else 0.1
        others = [distance(e.desc, o.desc) for o in ex if o is not e]
        e.nearest_other = min(others) if others else None
        tau = 1.25 * pos + 0.01
        if e.nearest_other is not None:
            tau = min(tau, 0.5 * e.nearest_other)
        e.tau = float(np.clip(tau, TAU_FLOOR, TAU_CEIL))


# ---- candidates ----------------------------------------------------------------------------------------------------

def _components(boxes: np.ndarray, gap: float) -> np.ndarray:
    g = gap / 2 + 1e-6
    geoms = shapely.box(boxes[:, 0] - g, boxes[:, 1] - g, boxes[:, 2] + g, boxes[:, 3] + g)
    tree = STRtree(geoms)
    a, b = tree.query(geoms, predicate="intersects")
    m = len(boxes)
    graph = coo_matrix((np.ones(len(a)), (a, b)), shape=(m, m))
    return connected_components(graph, directed=False)[1]


def _candidates(strokes: list[Stroke], boxes: np.ndarray, size: float, lo: float, hi: float):
    """Groups of small strokes whose box diagonal is in [lo, hi]: tuples of stroke indices."""
    diag = np.hypot(boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1])
    small = np.flatnonzero(diag <= hi)
    if len(small) == 0:
        return
    seen = set()
    for g in GAPS:
        lab = _components(boxes[small], g * size)
        order = np.argsort(lab, kind="stable")
        cut = np.flatnonzero(np.diff(lab[order])) + 1
        for grp in np.split(order, cut):
            idx = tuple(sorted(int(small[k]) for k in grp))
            if idx in seen or len(idx) > MAX_STROKES:
                continue
            seen.add(idx)
            bx = boxes[list(idx)]
            dg = float(np.hypot(bx[:, 2].max() - bx[:, 0].min(), bx[:, 3].max() - bx[:, 1].min()))
            if lo <= dg <= hi:
                yield idx


def _overlap(a, b) -> bool:
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return False
    inter = iw * ih
    aa, ab = (a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])
    return inter / (aa + ab - inter + 1e-12) > 0.25 or inter / (min(aa, ab) + 1e-12) > 0.5


def find_instances(strokes: list[Stroke], region, exemplars: list[Exemplar], expected_ratio: float | dict[int, float] = 1.0,
                   band: tuple[float, float] = BAND, method: str = "descriptor",
                   margin: float = AMBIGUITY_MARGIN) -> FindResult:
    """Instances of the exemplars among the strokes whose box lies in `region` (a view box). `expected_ratio` is the size of
    a symbol here over its size in the legend (1.0 when symbols are plotted at one paper size; the legend scale over the
    view scale when they are drawn at model size). `method` "hash" is the baseline: exact path signature only."""
    res = FindResult()
    if not exemplars:
        return res
    sel = [s for s in strokes if region[0] <= (s.bbox[0] + s.bbox[2]) / 2 <= region[2] and region[1] <= (s.bbox[1] + s.bbox[3]) / 2 <= region[3]]
    if not sel:
        return res
    boxes = np.array([s.bbox for s in sel])
    cache: dict[tuple, tuple | None] = {}
    for e in exemplars:
        ratio = expected_ratio[e.id] if isinstance(expected_ratio, dict) else expected_ratio
        size = e.size * ratio
        for idx in _candidates(sel, boxes, size, band[0] * size, band[1] * size):
            if idx not in cache:
                ss = [sel[k] for k in idx]
                if method == "hash":
                    cache[idx] = (signature_hash(ss), union_box(boxes[list(idx)]))
                else:
                    d = describe(ss)
                    cache[idx] = (d, d.box) if d is not None else None
    for val in cache.values():
        if val is None:
            continue
        res.n_candidates += 1
        item, box = val
        diag = float(np.hypot(box[2] - box[0], box[3] - box[1]))
        scored = []
        for e in exemplars:
            ratio = expected_ratio[e.id] if isinstance(expected_ratio, dict) else expected_ratio
            size = e.size * ratio
            if not band[0] * size <= diag <= band[1] * size:
                continue
            if method == "hash":
                if item is not None and item == e.hash:
                    scored.append((0.0, e))
            else:
                scored.append((distance(e.desc, item), e))
        if not scored:
            continue
        scored.sort(key=lambda t: t[0])
        d1, e1 = scored[0]
        if method != "hash" and d1 > e1.tau:
            res.n_not_in_legend += 1
            continue
        runner = None
        amb = False
        if len(scored) > 1 and method != "hash":
            d2, e2 = scored[1]
            runner = (e2.id, d2)
            amb = d2 <= e2.tau and d2 - d1 < margin
        det = Detection(e1.id, box, d1, e1.tau, runner, amb)
        (res.ambiguous if amb else res.detections).append(det)
    res.detections = _thin(res.detections, res.ambiguous)
    return res


def _thin(dets: list[Detection], amb: list[Detection]) -> list[Detection]:
    """Keep the nearest of overlapping detections; an ambiguous candidate that overlaps a kept one is dropped, and a
    kept one overlapped by a nearer ambiguous candidate is dropped too (the place is contested)."""
    allc = sorted([(d.dist, 0, d) for d in dets] + [(d.dist, 1, d) for d in amb], key=lambda t: (t[0], t[1], t[2].box))
    kept: list[Detection] = []
    for _, _, d in allc:
        if any(_overlap(d.box, k.box) for k in kept):
            continue
        kept.append(d)
    keep_amb = [d for d in kept if d.ambiguous]
    amb[:] = keep_amb
    return [d for d in kept if not d.ambiguous]
