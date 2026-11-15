"""E1 - Matching: Hungarian assignment on 1 - IoU, and length-weighted line coverage."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree


@dataclass
class MatchResult:
    pairs: list[tuple[int, int, float]]    # (pred index, true index, IoU)
    n_pred: int
    n_true: int

    @property
    def tp(self) -> int:
        return len(self.pairs)

    @property
    def precision(self) -> float:
        return self.tp / self.n_pred if self.n_pred else (1.0 if not self.n_true else 0.0)

    @property
    def recall(self) -> float:
        return self.tp / self.n_true if self.n_true else (1.0 if not self.n_pred else 0.0)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def pred_to_true(self) -> dict[int, int]:
        return {p: t for p, t, _ in self.pairs}


def iou(a: Polygon, b: Polygon) -> float:
    if a.is_empty or b.is_empty:
        return 0.0
    inter = a.intersection(b).area
    if inter <= 0:
        return 0.0
    return inter / (a.area + b.area - inter)


def match_polygons(pred: list[Polygon], true: list[Polygon], thr: float = 0.5) -> MatchResult:
    if not pred or not true:
        return MatchResult([], len(pred), len(true))
    cost = np.ones((len(pred), len(true)))
    tree = STRtree(true)
    for i, p in enumerate(pred):
        for j in tree.query(p):
            cost[i, j] = 1.0 - iou(p, true[j])
    r, c = linear_sum_assignment(cost)
    pairs = [(int(i), int(j), 1.0 - cost[i, j]) for i, j in zip(r, c) if 1.0 - cost[i, j] >= thr]
    return MatchResult(pairs, len(pred), len(true))


def length_coverage(pred: list[tuple[LineString, float]], true: list[tuple[LineString, float]],
                    tol: float) -> tuple[float, float]:
    """Length-weighted (precision, recall) for centrelines: a predicted metre counts when it lies
    within the true wall body (half thickness + tol), and vice versa."""
    def covered(src, ref):
        if not src:
            return 1.0 if not ref else 0.0
        if not ref:
            return 0.0
        body = unary_union([ln.buffer(t / 2 + tol, cap_style="flat") for ln, t in ref])
        tot = sum(ln.length for ln, _ in src)
        inside = sum(ln.intersection(body).length for ln, _ in src)
        return inside / tot if tot else 0.0

    return covered(pred, true), covered(true, pred)


def prf(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if p + r else 0.0
