"""Alignment of two versions: sheets by number and title block (then by content), and per sheet a rigid transform (a turn by
quarter turns and a translation) from the old page frame to the new one, found by voting. No model, no learned parts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from .snapshot import BBox, PageSnap, Snapshot

MIN_CONTENT = 0.55            # content similarity needed to pair two sheets whose numbers do not agree
MIN_WITH_NUMBER = 0.12        # ... and when the sheet number agrees


@dataclass
class SheetMatch:
    old: PageSnap
    new: PageSnap
    score: float
    how: str                    # number, title, content
    renumbered: bool = False


@dataclass
class Transform:
    rot: int = 0                # quarter turns clockwise applied to the old page
    dx: float = 0.0
    dy: float = 0.0
    votes: int = 0
    method: str = "identity"
    ok: bool = True
    W: float = 0.0              # old page size
    H: float = 0.0

    def _rot(self, x, y):
        W, H = self.W, self.H
        for _ in range(self.rot % 4):
            x, y, W, H = H - y, x, H, W
        return x, y

    def point(self, x: float, y: float) -> tuple[float, float]:
        x, y = self._rot(x, y)
        return x + self.dx, y + self.dy

    def box(self, b: BBox) -> BBox:
        a, c = self.point(b[0], b[1]), self.point(b[2], b[3])
        return (min(a[0], c[0]), min(a[1], c[1]), max(a[0], c[0]), max(a[1], c[1]))

    def inv_box(self, b: BBox) -> BBox:
        """A box of the new page in the old page frame."""
        corners = []
        for _ in range(1):
            for x, y in ((b[0], b[1]), (b[2], b[3])):
                corners.append(self._inv_point(x, y))
        return (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))

    def _inv_point(self, x: float, y: float) -> tuple[float, float]:
        x, y = x - self.dx, y - self.dy
        dims = [(self.W, self.H)]
        for _ in range(self.rot % 4):
            dims.append((dims[-1][1], dims[-1][0]))
        for k in range(self.rot % 4):
            W, H = dims[self.rot % 4 - 1 - k]
            # forward step on a page of size (W, H): x' = H - y, y' = x  ->  x = y', y = H - x'
            x, y = y, H - x
        return x, y

    @property
    def is_identity(self) -> bool:
        return self.rot % 4 == 0 and abs(self.dx) < 0.5 and abs(self.dy) < 0.5

    def to_dict(self) -> dict:
        return {"rot": self.rot, "dx": round(self.dx, 2), "dy": round(self.dy, 2), "votes": self.votes, "method": self.method}


def _wjaccard(a: Counter, b: Counter) -> float:
    inter = sum((a & b).values())
    union = sum((a | b).values())
    return inter / union if union else 0.0


def align_sheets(old: Snapshot, new: Snapshot) -> tuple[list[SheetMatch], list[PageSnap], list[PageSnap]]:
    """Pair the pages of two versions. A pair needs the same sheet number (or title) and some shared content, or a high
    content similarity alone (a renumbered or reordered sheet). Returns the pairs, the old pages with no partner (removed)
    and the new pages with no partner (added)."""
    bags_o = {p.index: p.token_bag() for p in old.pages}
    bags_n = {p.index: p.token_bag() for p in new.pages}
    cands = []
    for o in old.pages:
        for n in new.pages:
            sim = _wjaccard(bags_o[o.index], bags_n[n.index])
            same_no = o.number is not None and n.number is not None and o.key == n.key
            same_title = bool(o.title) and o.title == n.title
            if same_no and sim >= MIN_WITH_NUMBER:
                how = "number"
            elif sim >= MIN_CONTENT:
                how = "content" if not same_title else "title"
            else:
                continue
            bonus = 0.5 * same_no + 0.1 * same_title
            cands.append((sim + bonus, sim, how, o, n))
    cands.sort(key=lambda c: (-c[0], c[3].index, c[4].index))
    used_o: set[int] = set()
    used_n: set[int] = set()
    pairs = []
    for _score, sim, how, o, n in cands:
        if o.index in used_o or n.index in used_n:
            continue
        used_o.add(o.index)
        used_n.add(n.index)
        renum = (o.number or None) != (n.number or None) and (o.number is not None or n.number is not None)
        pairs.append(SheetMatch(o, n, round(sim, 3), how, renumbered=renum and how != "number"))
    pairs.sort(key=lambda m: m.old.index)
    removed = [p for p in old.pages if p.index not in used_o]
    added = [p for p in new.pages if p.index not in used_n]
    return pairs, removed, added


def _rot_pts(pts: np.ndarray, rot: int, W: float, H: float) -> np.ndarray:
    for _ in range(rot % 4):
        pts = np.stack([H - pts[:, 1], pts[:, 0]], axis=1)
        W, H = H, W
    return pts


def _peak(diffs: np.ndarray, weights: np.ndarray | None = None) -> tuple[float, float, float]:
    """The most voted translation among the differences (1 point bins, a 3 x 3 neighbourhood) and its refined value."""
    if not len(diffs):
        return 0.0, 0.0, 0.0
    w = np.ones(len(diffs)) if weights is None else weights
    bins = np.round(diffs).astype(int)
    tally: dict[tuple[int, int], float] = {}
    for (bx, by), wi in zip(map(tuple, bins), w, strict=True):
        tally[(bx, by)] = tally.get((bx, by), 0.0) + wi
    best, score = (0, 0), -1.0
    for (bx, by) in tally:
        s = sum(tally.get((bx + i, by + j), 0.0) for i in (-1, 0, 1) for j in (-1, 0, 1))
        if s > score or (s == score and abs(bx) + abs(by) < abs(best[0]) + abs(best[1])):
            best, score = (bx, by), s
    near = diffs[(np.abs(diffs[:, 0] - best[0]) <= 1.5) & (np.abs(diffs[:, 1] - best[1]) <= 1.5)]
    med = np.median(near, axis=0) if len(near) else np.array(best, dtype=float)
    return float(med[0]), float(med[1]), float(score)


def _word_diffs(a: PageSnap, b: PageSnap, rot: int) -> np.ndarray:
    by_new: dict[str, list[int]] = {}
    for j, w in enumerate(b.words):
        by_new.setdefault(w.text.lower(), []).append(j)
    cn = np.array([[(w.bbox[0] + w.bbox[2]) / 2, (w.bbox[1] + w.bbox[3]) / 2] for w in b.words]) if b.words else np.zeros((0, 2))
    ca = np.array([[(w.bbox[0] + w.bbox[2]) / 2, (w.bbox[1] + w.bbox[3]) / 2] for w in a.words]) if a.words else np.zeros((0, 2))
    ca = _rot_pts(ca, rot, a.width, a.height) if len(ca) else ca
    out = []
    by_old: dict[str, list[int]] = {}
    for i, w in enumerate(a.words):
        by_old.setdefault(w.text.lower(), []).append(i)
    for text, ia in by_old.items():
        jb = by_new.get(text)
        if not jb or len(ia) * len(jb) > 300:
            continue
        for i in ia:
            for j in jb:
                out.append(cn[j] - ca[i])
    return np.array(out).reshape(-1, 2)


def _prim_diffs(a: PageSnap, b: PageSnap, rot: int) -> tuple[np.ndarray, np.ndarray]:
    ka, kb = np.array(a.keys), np.array(b.keys)
    ca = np.stack([(a.feats[:, 0] + a.feats[:, 2]) / 2, (a.feats[:, 1] + a.feats[:, 3]) / 2], axis=1) if len(ka) else np.zeros((0, 2))
    cb = np.stack([(b.feats[:, 0] + b.feats[:, 2]) / 2, (b.feats[:, 1] + b.feats[:, 3]) / 2], axis=1) if len(kb) else np.zeros((0, 2))
    ca = _rot_pts(ca, rot, a.width, a.height) if len(ca) else ca
    la, lb = (np.round(a.feats[:, 4]) if len(ka) else ka), (np.round(b.feats[:, 4]) if len(kb) else kb)
    ga: dict[tuple, list[int]] = {}
    gb: dict[tuple, list[int]] = {}
    for i in range(len(ka)):
        ga.setdefault((int(ka[i]), int(la[i] // 2)), []).append(i)
    for j in range(len(kb)):
        gb.setdefault((int(kb[j]), int(lb[j] // 2)), []).append(j)
    diffs, weights = [], []
    for key, ia in ga.items():
        jb = gb.get(key)
        if not jb or len(ia) * len(jb) > 36:
            continue
        for i in ia:
            for j in jb:
                diffs.append(cb[j] - ca[i])
                weights.append(1.0 / (len(ia) * len(jb)) ** 0.5)
    return np.array(diffs).reshape(-1, 2), np.array(weights)


def estimate_transform(a: PageSnap, b: PageSnap) -> Transform:
    """The turn and shift taking the old page onto the new one. Words vote first (same text, shift between the two places);
    drawn objects vote when the page has too few words. `ok` is False when no shift got enough votes."""
    best = Transform(W=a.width, H=a.height, ok=False, method="none")
    best_score = 0.0
    n_words = min(len(a.words), len(b.words))
    for rot in range(4):
        d = _word_diffs(a, b, rot)
        dx, dy, score = _peak(d)
        need = max(3, 0.04 * n_words)
        if score >= need:
            pref = score * (1.0 if rot == 0 else 0.97)
            if pref > best_score:
                best, best_score = Transform(rot, dx, dy, int(score), "words", True, a.width, a.height), pref
    if best.ok:
        return best
    for rot in range(4):
        d, w = _prim_diffs(a, b, rot)
        dx, dy, score = _peak(d, w)
        if score >= 6 and score * (1.0 if rot == 0 else 0.97) > best_score:
            best_score = score * (1.0 if rot == 0 else 0.97)
            best = Transform(rot, dx, dy, int(score), "drawn objects", True, a.width, a.height)
    if not best.ok and not len(a.words) and not len(b.words) and not len(a.keys) and not len(b.keys):
        return Transform(W=a.width, H=a.height, ok=False, method="empty")
    return best
