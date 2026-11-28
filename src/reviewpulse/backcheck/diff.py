"""Vector content diff of two aligned pages: words (text and place), drawn objects (shape bucket and place), blocks that moved
as a whole, and the changed places they add up to. Everything is compared after the page transform, so a shift or a turn of
the whole page is no change, and a block that moved with its content intact is a move, not an edit."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from .align import Transform
from .snapshot import BBox, PageSnap

WORD_TOL = 2.5          # points between the same word in two versions
PRIM_TOL = 1.0          # points on each of the four box edges and 2 on the path length
CLUSTER_MARGIN = 14.0   # changed things closer than this make one changed place
MOVE_MIN = 6            # a moved block holds at least this many objects


@dataclass
class Item:
    kind: str                       # word, shape
    bbox: BBox                      # old frame
    text: str = ""
    key: int = 0
    length: float = 0.0
    side: str = "removed"           # removed (only in the old), added (only in the new)


@dataclass
class Moved:
    bbox_old: BBox
    bbox_new: BBox
    dx: float
    dy: float
    n: int


@dataclass
class PageDiff:
    transform: Transform
    items: list[Item] = field(default_factory=list)
    moved: list[Moved] = field(default_factory=list)
    n_words_same: int = 0
    n_shapes_same: int = 0

    @property
    def n_changes(self) -> int:
        return len(self.items)


def _centers(b: BBox) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _match_words(a: PageSnap, b: PageSnap, T: Transform):
    by_new: dict[str, list[int]] = {}
    for j, w in enumerate(b.words):
        by_new.setdefault(w.text.lower(), []).append(j)
    nb = [T.inv_box(w.bbox) for w in b.words]            # new words in the old frame
    taken: set[int] = set()
    unmatched_old = []
    same = 0
    for i, w in enumerate(a.words):
        cx, cy = _centers(w.bbox)
        tol = max(WORD_TOL, 0.35 * min(w.bbox[3] - w.bbox[1], 12))
        best, bd = None, 1e9
        for j in by_new.get(w.text.lower(), ()):
            if j in taken:
                continue
            nx, ny = _centers(nb[j])
            d = max(abs(nx - cx), abs(ny - cy))
            if d <= tol and d < bd:
                best, bd = j, d
        if best is None:
            unmatched_old.append(i)
        else:
            taken.add(best)
            same += 1
    unmatched_new = [j for j in range(len(b.words)) if j not in taken]
    return unmatched_old, unmatched_new, nb, same


def _match_shapes(a: PageSnap, b: PageSnap, T: Transform):
    na, nb_ = len(a.keys), len(b.keys)
    if not na or not nb_:
        return list(range(na)), list(range(nb_)), 0
    fa = np.array([[*T.box(tuple(f[:4])), f[4]] for f in a.feats])
    fb = b.feats
    ka, kb = np.array(a.keys), np.array(b.keys)
    matched_a: set[int] = set()
    matched_b: set[int] = set()
    # identical shapes first, one for one: CAD exports often stack many copies of one line in one place
    exact: dict[tuple, list[int]] = {}
    for j in range(nb_):
        exact.setdefault((int(kb[j]), *np.round(fb[j], 2).tolist()), []).append(j)
    for i in range(na):
        left = exact.get((int(ka[i]), *np.round(fa[i], 2).tolist()))
        if left:
            matched_a.add(i)
            matched_b.add(left.pop())
    # then near ones, among every candidate within the tolerance (not only a few nearest), closest pairs first
    for key in set(ka.tolist()) & set(kb.tolist()):
        ia = np.array([i for i in np.where(ka == key)[0] if int(i) not in matched_a], dtype=int)
        jb = np.array([j for j in np.where(kb == key)[0] if int(j) not in matched_b], dtype=int)
        if not len(ia) or not len(jb):
            continue
        pa, pb = np.c_[fa[ia, :4], fa[ia, 4] / 2], np.c_[fb[jb, :4], fb[jb, 4] / 2]
        near = cKDTree(pb).query_ball_point(pa, r=PRIM_TOL, p=np.inf)
        pairs = sorted((float(np.abs(pa[r] - pb[c]).max()), int(ia[r]), int(jb[c])) for r, cs in enumerate(near) for c in cs)
        for _d, i, j in pairs:
            if i not in matched_a and j not in matched_b:
                matched_a.add(i)
                matched_b.add(j)
    return ([i for i in range(na) if i not in matched_a], [j for j in range(nb_) if j not in matched_b], len(matched_a))


def _find_moves(items_old: list[Item], items_new: list[Item]) -> tuple[list[Moved], set[int], set[int]]:
    """Leftover objects that agree on one shift between the versions are a block that moved (the old box and the new box of
    each object are the same shape in two places). Returns the blocks and the indices of the items they explain."""
    moved: list[Moved] = []
    used_o: set[int] = set()
    used_n: set[int] = set()
    for _round in range(4):
        by_new: dict[tuple, list[int]] = {}
        for j, it in enumerate(items_new):
            if j not in used_n:
                by_new.setdefault((it.kind, it.key, it.text.lower(), int(it.length // 2)), []).append(j)
        votes: dict[tuple[int, int], int] = {}
        for i, it in enumerate(items_old):
            if i in used_o:
                continue
            js = by_new.get((it.kind, it.key, it.text.lower(), int(it.length // 2)), ())
            if not js or len(js) > 12:
                continue
            for j in js:
                d = items_new[j].bbox
                votes[(round(d[0] - it.bbox[0]), round(d[1] - it.bbox[1]))] = votes.get((round(d[0] - it.bbox[0]), round(d[1] - it.bbox[1])), 0) + 1
        if not votes:
            break
        (sx, sy), n = max(votes.items(), key=lambda kv: kv[1])
        if n < MOVE_MIN or (abs(sx) <= 2 and abs(sy) <= 2):
            break
        pairs_o, pairs_n = [], []
        taken: set[int] = set()
        for i, it in enumerate(items_old):
            if i in used_o:
                continue
            for j in by_new.get((it.kind, it.key, it.text.lower(), int(it.length // 2)), ()):
                if j in taken or j in used_n:
                    continue
                d = items_new[j].bbox
                if abs(d[0] - it.bbox[0] - sx) <= 2.0 and abs(d[1] - it.bbox[1] - sy) <= 2.0:
                    pairs_o.append(i)
                    pairs_n.append(j)
                    taken.add(j)
                    break
        if len(pairs_o) < MOVE_MIN:
            break
        bo = _union([items_old[i].bbox for i in pairs_o])
        bn = _union([items_new[j].bbox for j in pairs_n])
        moved.append(Moved(bo, bn, float(sx), float(sy), len(pairs_o)))
        used_o.update(pairs_o)
        used_n.update(pairs_n)
    return moved, used_o, used_n


def _union(boxes) -> BBox:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def diff_pages(a: PageSnap, b: PageSnap, T: Transform) -> PageDiff:
    out = PageDiff(T)
    uo_w, un_w, nbw, same_w = _match_words(a, b, T)
    uo_s, un_s, same_s = _match_shapes(a, b, T)
    out.n_words_same, out.n_shapes_same = same_w, same_s
    old_items = [Item("word", a.words[i].bbox, a.words[i].text) for i in uo_w]       # boxes in the old frame
    new_items = [Item("word", nbw[j], b.words[j].text, side="added") for j in un_w]  # boxes in the old frame too
    new_frame = [b.words[j].bbox for j in un_w]                                      # the same boxes in the new frame
    for i in uo_s:
        f = a.feats[i]
        old_items.append(Item("shape", tuple(f[:4]), "", a.keys[i], float(f[4])))
    for j in un_s:
        f = b.feats[j]
        new_items.append(Item("shape", T.inv_box(tuple(f[:4])), "", b.keys[j], float(f[4]), side="added"))
        new_frame.append(tuple(f[:4]))
    # a moved block is looked for in the new frame: old boxes carried over by the page transform, new boxes as they are
    old_t = [Item(it.kind, T.box(it.bbox), it.text, it.key, it.length) for it in old_items]
    new_n = [Item(it.kind, nf, it.text, it.key, it.length, "added") for it, nf in zip(new_items, new_frame, strict=True)]
    moved, used_o, used_n = _find_moves(old_t, new_n)
    for m in moved:
        out.moved.append(Moved(T.inv_box(m.bbox_old), m.bbox_new, m.dx, m.dy, m.n))
    out.items = [it for i, it in enumerate(old_items) if i not in used_o] + [it for j, it in enumerate(new_items) if j not in used_n]
    return out


def clusters(items: list[Item], margin: float = CLUSTER_MARGIN) -> list[list[Item]]:
    """Changed objects that touch or lie within `margin` of each other, grouped (union-find over a grid)."""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    cell = max(margin * 2, 30.0)
    grid: dict[tuple[int, int], list[int]] = {}
    for i, it in enumerate(items):
        b = it.bbox
        for gx in range(int((b[0] - margin) // cell), int((b[2] + margin) // cell) + 1):
            for gy in range(int((b[1] - margin) // cell), int((b[3] + margin) // cell) + 1):
                grid.setdefault((gx, gy), []).append(i)
    for members in grid.values():
        for ai in range(len(members)):
            for bi in range(ai + 1, len(members)):
                i, j = members[ai], members[bi]
                if find(i) == find(j):
                    continue
                p, q = items[i].bbox, items[j].bbox
                if p[0] - margin <= q[2] and q[0] - margin <= p[2] and p[1] - margin <= q[3] and q[1] - margin <= p[3]:
                    parent[find(i)] = find(j)
    groups: dict[int, list[Item]] = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    return sorted(groups.values(), key=lambda g: (_union([x.bbox for x in g])[1], _union([x.bbox for x in g])[0]))
