"""A shape descriptor of a set of strokes that does not change with translation, scale, rotation or mirroring.

The strokes are resampled at equal steps of arc length (so how a curve was cut into pieces does not matter, nor how long the
pieces are). From the samples, relative to their centroid and the root mean square radius, four blocks are built:

  pairs     a soft histogram over (distance between two samples, angle between their tangents): a multi scale shape
            context in which orientation is only ever relative, so a turned symbol gives the same histogram
  radial    the distribution of the distance from the centroid
  angular   the magnitudes of the first Fourier harmonics of the ink around the centroid (a turn only shifts the phase)
  type      from the turning function of the simplified strokes: the share of the turning that is in corners and in smooth
            curves, the total turning; then the filled and closed share, the aspect and the ink amount per radius

`signature_hash` is the simple baseline: the exact quantised path signature, which only equal drawings share.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .primitives import Stroke

N_SAMPLES = 64
PAIR_D_BINS, PAIR_A_BINS, RAD_BINS, ANG_BINS, HARM = 8, 4, 10, 16, 5
D_MAX, R_MAX = 3.2, 2.5
SIMPLIFY = 0.008                  # Douglas-Peucker tolerance, share of the box diagonal
SMOOTH_LO, CORNER = np.radians(3.0), np.radians(50.0)
WEIGHTS = {"pairs": 0.35, "radial": 0.20, "angular": 0.15, "type": 0.30}
MIN_LENGTH = 1e-6


@dataclass
class Descriptor:
    pairs: np.ndarray
    radial: np.ndarray
    angular: np.ndarray
    type: np.ndarray           # corner share, smooth share, total turning, filled, closed, aspect, ink
    diag: float                # box diagonal of the strokes, page points
    box: tuple[float, float, float, float]

    def vector(self) -> np.ndarray:
        """The deterministic embedding: the four blocks joined, each scaled by the square root of its weight."""
        return np.concatenate([np.sqrt(WEIGHTS["pairs"]) * self.pairs.ravel(), np.sqrt(WEIGHTS["radial"]) * self.radial,
                               np.sqrt(WEIGHTS["angular"]) * self.angular, np.sqrt(WEIGHTS["type"]) * self.type])


def _soft_bin(x: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Linear soft assignment of x in [0, 1] to n bins: (low bin, high bin, weight of the high bin)."""
    f = np.clip(x, 0, 1) * n - 0.5
    lo = np.clip(np.floor(f).astype(int), 0, n - 1)
    hi = np.clip(lo + 1, 0, n - 1)
    w = np.clip(f - np.floor(f), 0, 1)
    w = np.where(f < 0, 0.0, w)
    return lo, hi, w


def _simplify(p: np.ndarray, eps: float) -> np.ndarray:
    """Douglas-Peucker: drop vertices closer than eps to the line through their neighbours (noise and extra cut points)."""
    n = len(p)
    if n <= 2:
        return p
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        seg = p[j] - p[i]
        ln = float(np.hypot(*seg))
        q = p[i + 1:j] - p[i]
        d = np.hypot(*q.T) if ln < 1e-12 else np.abs(seg[0] * q[:, 1] - seg[1] * q[:, 0]) / ln
        k = int(np.argmax(d))
        if d[k] > eps:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return p[keep]


def _resample(strokes: list[Stroke]):
    a, b, flag_f = [], [], []
    closed_len = 0.0
    corner = smooth = 0.0
    for s in strokes:
        p = s.pts
        seg = np.diff(p, axis=0)
        ln = np.hypot(seg[:, 0], seg[:, 1])
        keep = ln > MIN_LENGTH
        if not keep.any():
            continue
        a.append(p[:-1][keep])
        b.append(p[1:][keep])
        flag_f.append(np.full(int(keep.sum()), s.filled))
        if s.closed:
            closed_len += float(ln.sum())
        # turning function of the simplified stroke: where the direction changes and by how much
        q = p
        if s.closed and len(q) > 3:
            q = q[:-1]
            sg = np.roll(q, -1, axis=0) - q
        else:
            sg = np.diff(q, axis=0)
        sg = sg[np.hypot(sg[:, 0], sg[:, 1]) > MIN_LENGTH]
        if len(sg) >= 2:
            ang = np.arctan2(sg[:, 1], sg[:, 0])
            nxt = np.roll(ang, -1)
            turn = np.abs((nxt - ang + np.pi) % (2 * np.pi) - np.pi)
            if not (s.closed and len(q) > 3):
                turn = turn[:-1]
            corner += float(turn[turn >= CORNER].sum())
            smooth += float(turn[(turn >= SMOOTH_LO) & (turn < CORNER)].sum())
    if not a:
        return None
    return np.vstack(a), np.vstack(b), np.concatenate(flag_f), (corner, smooth), closed_len


def describe(strokes: list[Stroke], n: int = N_SAMPLES) -> Descriptor | None:
    strokes = [s for s in strokes if len(s.pts) >= 2]
    if not strokes:
        return None
    allpts = np.vstack([s.pts for s in strokes])
    eps = SIMPLIFY * float(np.hypot(*(allpts.max(axis=0) - allpts.min(axis=0))))
    # noise and extra cut points are removed first, so everything below depends on the shape and not on how it was cut
    strokes = [Stroke(_simplify(s.pts, eps), s.filled, s.closed, s.width) for s in strokes]
    r = _resample(strokes)
    if r is None:
        return None
    a, b, fl, (corner, smooth), closed_len = r
    d = b - a
    ln = np.hypot(d[:, 0], d[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(ln)])
    L = cum[-1]
    t = (np.arange(n) + 0.5) * L / n
    i = np.clip(np.searchsorted(cum, t, side="right") - 1, 0, len(ln) - 1)
    u = (t - cum[i]) / ln[i]
    P = a[i] + u[:, None] * d[i]
    tang = np.arctan2(d[i, 1], d[i, 0]) % np.pi
    fill_share = float(ln[fl].sum() / L)
    c = P.mean(axis=0)
    q = P - c
    rad = np.hypot(q[:, 0], q[:, 1])
    s = float(np.sqrt((rad ** 2).mean()))
    allp = np.vstack([a, b])
    box = (float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max()))
    diag = float(np.hypot(box[2] - box[0], box[3] - box[1]))
    if s < 1e-9:
        return None
    iu, ju = np.triu_indices(n, 1)
    dq = q[iu] - q[ju]
    dist = np.hypot(dq[:, 0], dq[:, 1]) / s
    da = np.abs(tang[iu] - tang[ju])
    da = np.minimum(da, np.pi - da) / (np.pi / 2)
    dl, dh, dw = _soft_bin(dist / D_MAX, PAIR_D_BINS)
    al, ah, aw = _soft_bin(da, PAIR_A_BINS)
    H = np.zeros((PAIR_D_BINS, PAIR_A_BINS))
    for di, dwt in ((dl, 1 - dw), (dh, dw)):
        for ai, awt in ((al, 1 - aw), (ah, aw)):
            np.add.at(H, (di, ai), dwt * awt)
    H /= H.sum()
    rl, rh, rw = _soft_bin(rad / s / R_MAX, RAD_BINS)
    R = np.zeros(RAD_BINS)
    np.add.at(R, rl, 1 - rw)
    np.add.at(R, rh, rw)
    R /= R.sum()
    th = np.arctan2(q[:, 1], q[:, 0])
    mass = np.zeros(ANG_BINS)
    bi = ((th + np.pi) / (2 * np.pi) * ANG_BINS).astype(int) % ANG_BINS
    np.add.at(mass, bi, rad / s)
    spec = np.abs(np.fft.rfft(mass))
    ang = spec[1:HARM + 1] / max(spec[0], 1e-9)
    tot = corner + smooth
    ev = np.linalg.eigvalsh(np.cov(q.T) + 1e-12 * np.eye(2))
    aspect = float(np.sqrt(max(ev[0], 0) / max(ev[1], 1e-12)))
    ink = float(np.log2(max(L / s, 1e-3)) / 4.0)
    typ = np.array([corner / tot if tot > 1e-9 else 0.0, smooth / tot if tot > 1e-9 else 0.0,
                    min(tot / (2 * np.pi), 3.0) / 3.0, fill_share, closed_len / L, aspect, ink])
    return Descriptor(H, R, ang, typ, diag, box)


def distance(x: Descriptor, y: Descriptor) -> float:
    """0 for the same shape; a weighted mix of block distances, each between 0 and about 1."""
    d_pairs = 0.5 * float(np.abs(x.pairs - y.pairs).sum())
    d_rad = 0.5 * float(np.abs(x.radial - y.radial).sum())
    d_ang = float(np.abs(x.angular - y.angular).mean()) * 2.0
    dt = np.abs(x.type - y.type)
    d_type = float(min(1.0, dt[:5].sum() / 2.0 + 0.5 * dt[5] + 0.5 * dt[6]))
    return (WEIGHTS["pairs"] * d_pairs + WEIGHTS["radial"] * d_rad + WEIGHTS["angular"] * min(d_ang, 1.0)
            + WEIGHTS["type"] * d_type)


def signature_hash(strokes: list[Stroke], grid: int = 16) -> str | None:
    """Baseline: the exact path signature. Strokes are moved to the corner of their box, divided by its larger side,
    and every vertex is rounded to 1/grid of that side. Only drawings that agree vertex by vertex share the hash."""
    strokes = [s for s in strokes if len(s.pts) >= 2]
    if not strokes:
        return None
    allp = np.vstack([s.pts for s in strokes])
    lo = allp.min(axis=0)
    side = float((allp.max(axis=0) - lo).max())
    if side < 1e-9:
        return None
    parts = []
    for s in strokes:
        q = np.rint((s.pts - lo) / side * grid).astype(int)
        parts.append((len(q), bool(s.filled), tuple(map(tuple, q))))
    parts.sort()
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:16]
