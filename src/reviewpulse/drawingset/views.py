"""Cut a sheet into views.

Method (the general one, `xycut`):
  1. Find the title block from its labels (sheet number, date, drawn by ...) and set it apart.
  2. Find view titles: a line holding a view kind word (plan, section, detail, schedule ...) that is a title and not a note:
     it has a scale line next to it, or a number bubble, or it is set larger than the body text.
  3. Rasterise everything that is drawn or written on a coarse grid and cut the sheet at its widest whitespace bands, but
     only where each side keeps at least one title (recursive X-Y cut). A leaf with one title is one view.
  4. Each view takes the scale line of its title (or on its own title line), else the one scale found inside it, else the
     sheet default marked as such.

Baselines kept for comparison: `voronoi` (every cell goes to the nearest title) and `sheet` (the sheet is one view).
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter

import numpy as np

from .model import BBox, Sheet, View
from .pagedata import Line, PageData
from .scale import Scale, parse_scale
from .vocab import Vocab, fold, norm_id, plain

_BUBBLE = re.compile(r"^(?:[A-Za-z]?\d{1,2}|[A-Za-z])$")
_LEAD = re.compile(r"^(?P<lab>[A-Za-z]?\d{1,2}|[A-Za-z])\s*[.):\-]?\s+(?P<rest>.*\S.*)$")
NONPLAN = ("index", "legend", "schedule", "notes")


def box_of(ln: Line) -> BBox:
    return (ln.x0, ln.y0, ln.x1, ln.y1)


def gap(a: BBox, b: BBox) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def union(boxes: list[BBox]) -> BBox:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def median_h(pg: PageData) -> float:
    hs = [ln.h for ln in pg.lines if ln.horizontal and ln.src == "text"] or [ln.h for ln in pg.lines]
    return statistics.median(hs) if hs else 10.0


def median_size(pg: PageData) -> float:
    ss = [ln.size for ln in pg.lines if ln.horizontal]
    return statistics.median(ss) if ss else 10.0


# ---- title block ----------------------------------------------------------------------------------------------------

def find_title_block(pg: PageData, vocab: Vocab) -> tuple[BBox | None, dict[str, list[Line]]]:
    hits: dict[str, list[Line]] = {}
    for ln in pg.lines:
        t = fold(ln.text).rstrip(" :.")
        if len(t) > 40 or len(t.split()) > 6:
            continue
        for kind, rx in vocab.label_regex.items():
            m = rx.search(t)
            if m and m.start() <= 1:
                hits.setdefault(kind, []).append(ln)
    if len(hits) < 2:
        return None, hits
    lines = [ln for ls in hits.values() for ln in ls]
    hl = statistics.median(ln.h for ln in lines)
    W, H = pg.width, pg.height
    # labels of one title block sit together: grow a group from the sheet number label (else the first label) by single
    # linkage, so a "project / address" block elsewhere on the sheet is not pulled in
    seeds = hits.get("sheet_number") or lines[:1]
    group = [seeds[0]]
    grew = True
    while grew:
        grew = False
        for ln in lines:
            if ln not in group and min(gap(box_of(ln), box_of(g)) for g in group) <= 40 * hl:
                group.append(ln)
                grew = True
    kinds_in = {k for k, ls in hits.items() for ln in ls if ln in group}
    if len(kinds_in) < 2:
        return None, hits
    hits = {k: [ln for ln in ls if ln in group] for k, ls in hits.items() if any(ln in group for ln in ls)}
    lines = group
    box = union([box_of(ln) for ln in lines])
    pad = 6 * hl
    R = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    inside = [ln for ln in pg.lines if R[0] <= ln.cx <= R[2] and R[1] <= ln.cy <= R[3]]
    R = union([R] + [box_of(ln) for ln in inside if gap(box_of(ln), R) == 0])
    R = (max(0, R[0]), max(0, R[1]), min(W, R[2]), min(H, R[3]))
    edge = 0.05
    near = {"l": R[0] < edge * W, "r": R[2] > (1 - edge) * W, "t": R[1] < edge * H, "b": R[3] > (1 - edge) * H}
    x0, y0, x1, y1 = R
    if near["r"]:
        x1 = W
    if near["l"]:
        x0 = 0
    if near["b"]:
        y1 = H
    if near["t"]:
        y0 = 0
    if (near["l"] or near["r"]) and (x1 - x0) < 0.15 * W:
        y0, y1 = 0, H
    elif (near["t"] or near["b"]) and (y1 - y0) < 0.15 * H:
        x0, x1 = 0, W
    # a "title block" that covers most of the page is a form, not a title block
    if (x1 - x0) * (y1 - y0) > 0.5 * W * H:
        return None, hits
    return (x0, y0, x1, y1), hits


def in_box(ln: Line, b: BBox | None) -> bool:
    return b is not None and b[0] <= ln.cx <= b[2] and b[1] <= ln.cy <= b[3]


def read_title_block(pg: PageData, tb: BBox, hits: dict[str, list[Line]], vocab: Vocab, constants: frozenset[str] = frozenset()):
    """Sheet number, sheet title and default scale from the lines inside the title block."""
    all_lines = [ln for ln in pg.lines if in_box(ln, tb)]
    lines = [ln for ln in all_lines if fold(ln.text) not in constants]
    label_lines = {id(ln) for ls in hits.values() for ln in ls}

    def idlike(txt: str, allow_num: bool) -> bool:
        t = plain(txt).upper().strip(" .:")
        return bool(vocab.letter_id.match(t) or (allow_num and vocab.number_id.match(t)))

    number, num_line = None, None
    # "SHEET NO: A101" on one line
    for ln in hits.get("sheet_number", []):
        rest = re.split(r"[:#]", plain(ln.text), maxsplit=1)
        if len(rest) == 2 and idlike(rest[1], True):
            number, num_line = rest[1].strip(" ."), ln
    if number is None:
        cands = [ln for ln in lines if id(ln) not in label_lines and idlike(ln.text, True)]
        if cands:
            labs = hits.get("sheet_number", [])
            if labs:
                lab = labs[0]
                near = [c for c in cands if gap(box_of(c), box_of(lab)) <= 30 * lab.h]
                pool = near or cands
                top = max(c.size for c in pool)
                big = [c for c in pool if c.size >= 0.6 * top]
                num_line = min(big, key=lambda c: gap(box_of(c), box_of(lab)))
            else:
                num_line = max(cands, key=lambda c: c.size)
            number = plain(num_line.text).strip(" .:")
    # sheet title: the largest text of the block that is not the number or a label
    rest = [ln for ln in lines if id(ln) not in label_lines and ln is not num_line and len(ln.text.strip()) > 2
            and re.search(r"[A-Za-z]{3}", ln.text)]
    title = None
    if rest:
        top = max(ln.size for ln in rest)
        big = [ln for ln in rest if ln.size >= 0.85 * top]
        big.sort(key=lambda ln: (ln.cy if ln.horizontal else ln.cx, ln.cx if ln.horizontal else ln.cy))
        title = " ".join(plain(ln.text) for ln in big)
    default = None
    for ln in all_lines:
        s = parse_scale(ln.text, vocab, labelled=True)
        if s is not None and not s.nts:
            default = s
            break
    return number, title, default


# ---- titles ---------------------------------------------------------------------------------------------------------

def classify_kind(text: str, vocab: Vocab) -> str | None:
    ft = fold(text)
    for kind in vocab.kind_priority:
        if vocab.kind_regex[kind].search(ft):
            return kind
    # a storey name alone ("Erdgeschoss", "1. OG") titles a floor plan
    if read_level(text, vocab) is not None:
        return "plan"
    return None


class TitleCand:
    __slots__ = ("line", "kind", "title", "labels", "bubble", "scale_line", "scale", "scale_source", "anchor", "evidence")

    def __init__(self, line: Line, kind: str, title: str):
        self.line, self.kind, self.title = line, kind, title
        self.labels: list[str] = []
        self.bubble: Line | None = None
        self.scale_line: Line | None = None
        self.scale: Scale | None = None
        self.scale_source = "none"
        self.anchor: BBox = box_of(line)
        self.evidence: list[str] = []


def trailing_label(title: str, kind_words_rx: re.Pattern | None, vocab: Vocab) -> str | None:
    """"SECTION A-A" -> "A-A", "WINDOW ELEVATION B" -> "B", "DETAIL 4" -> "4" (the label after the last kind word)."""
    m = re.search(r"\b(?:[A-Za-z]{3,})\s+(?P<lab>[A-Z]{1,2}(?:\s*-\s*[A-Z]{1,2})?|\d{1,2})\s*$", title)
    if m:
        return m.group("lab").replace(" ", "")
    return None


def find_titles(pg: PageData, tb: BBox | None, vocab: Vocab, own_number: str | None = None) -> list[TitleCand]:
    mh = median_h(pg)
    ms = median_size(pg)
    cands: list[TitleCand] = []
    short = [ln for ln in pg.lines if not in_box(ln, tb) and ln.horizontal]
    scales: list[tuple[Line, Scale]] = []
    for ln in short:
        if len(ln.text) <= 48:
            s = parse_scale(ln.text, vocab)
            if s is not None:
                scales.append((ln, s))
    own = norm_id(own_number) if own_number else None
    bubbles = [ln for ln in short if _BUBBLE.match(ln.text.strip()) and (own is None or norm_id(ln.text) != own)]
    for ln in short:
        txt = plain(ln.text)
        if len(txt) > 70 or len(txt.split()) > 10:
            continue
        ft = fold(txt)
        if vocab.ref_regex.search(ft) and not vocab.scale_label.match(ft):
            continue            # "SOLAR PANELS, SEE DETAIL" is a note that points, not a title
        kind = classify_kind(txt, vocab)
        if kind is None:
            # a title bar needs no kind word when it is set in large type with both a number and a scale beside it
            if ln.size >= 1.25 * ms and len(txt.split()) <= 8 and sum(ch.isalpha() for ch in txt) >= 5:
                kind = "other"
            else:
                continue
        # numbers, dimension strings and sentences are not titles
        letters = sum(ch.isalpha() for ch in txt)
        if letters < 4 or letters < 0.5 * len(txt.replace(" ", "")):
            continue
        if txt.endswith(".") and len(txt.split()) > 3:
            continue
        tc = TitleCand(ln, kind, txt)
        lead = _LEAD.match(txt)
        if lead and kind_after(lead.group("rest"), vocab):
            tc.labels.append(lead.group("lab").upper())
            tc.title = lead.group("rest")
            tc.evidence.append("number in text")
        cands.append(tc)
    # numbers beside the title, scale lines beside the title
    used_b: set[int] = set()
    for tc in cands:
        if tc.labels:
            continue
        near = []
        for b in bubbles:
            if id(b) in used_b or b is tc.line:
                continue
            d = gap(box_of(b), box_of(tc.line))
            if d <= 3.0 * max(b.h, tc.line.h) and (b.cx <= tc.line.cx + tc.line.h or b.cy <= tc.line.cy):
                near.append((not b.text.strip().isdigit(), d, b))     # a plain number before a letter code, then the nearest
        if near:
            near.sort(key=lambda t: (t[0], t[1]))
            b = near[0][2]
            used_b.add(id(b))
            tc.bubble = b
            tc.labels.append(b.text.strip().upper())
            tc.anchor = union([tc.anchor, box_of(b)])
            tc.evidence.append("bubble")
    pairs = []
    for i, tc in enumerate(cands):
        own = parse_scale(tc.line.text, vocab) if len(tc.line.text) <= 70 else None
        if own is not None:
            tc.scale, tc.scale_source = own, "own line"
            tc.evidence.append("scale on title line")
            continue
        for j, (sl, _s) in enumerate(scales):
            if sl is tc.line:
                continue
            d = gap(tc.anchor, box_of(sl))
            # the scale sits just under or beside its title, not far across the sheet
            if d <= 3.0 * max(sl.h, tc.line.h) and abs(sl.cx - tc.line.cx) <= 40 * mh:
                pairs.append((d, i, j))
    taken_s: set[int] = set()
    for _d, i, j in sorted(pairs):
        tc = cands[i]
        if tc.scale is not None or j in taken_s:
            continue
        tc.scale_line, tc.scale = scales[j][0], scales[j][1]
        tc.scale_source = "title"
        tc.anchor = union([tc.anchor, box_of(scales[j][0])])
        tc.evidence.append("scale line")
        taken_s.add(j)
    out = []
    for tc in cands:
        big = tc.line.size >= 1.25 * ms and len(tc.title.split()) <= 8
        upper = tc.title.rstrip().endswith(":")
        ok = bool(tc.scale) or bool(tc.labels) or big
        if tc.kind == "other":
            ok = bool(tc.scale) and bool(tc.labels)
        if not ok and tc.kind in NONPLAN and (upper or tc.line.size >= 1.15 * ms) and len(tc.title.split()) <= 5:
            ok = True
            tc.evidence.append("heading")
        if big:
            tc.evidence.append("large type")
        if not ok:
            continue
        tl = trailing_label(tc.title, None, vocab)
        if tl and tl not in tc.labels:
            tc.labels.append(tl)
        out.append(tc)
    # one title per place: overprinted duplicates collapse
    out.sort(key=lambda t: (t.line.cy, t.line.cx))
    dedup: list[TitleCand] = []
    for tc in out:
        if any(fold(tc.title) == fold(d.title) and gap(box_of(tc.line), box_of(d.line)) < 2 * tc.line.h for d in dedup):
            continue
        dedup.append(tc)
    # an index with a heading owns the rows under it: they are not titles of other views
    for tc in [t for t in dedup if t.kind == "index"]:
        region = grow_list(pg, tb, tc.anchor)
        tc.anchor = region
        dedup = [t for t in dedup if t is tc or not (region[0] <= t.line.cx <= region[2] and region[1] <= t.line.cy <= region[3])]
    # an index with no heading in the text layer: a column of sheet numbers each beside its title
    for box in untitled_index(pg, tb, vocab):
        if any(t.kind == "index" and gap(t.anchor, box) <= 12 * mh for t in dedup):
            continue
        # the rows of an index are not titles of other views
        dedup = [t for t in dedup if gap(box_of(t.line), box) > 0]
        first = min((ln for ln in pg.lines if box[0] <= ln.cx <= box[2] and box[1] <= ln.cy <= box[3]), key=lambda ln: ln.cy)
        tc = TitleCand(first, "index", "(sheet index, no heading)")
        tc.anchor = box
        tc.evidence.append("rows of sheet numbers and titles")
        dedup.append(tc)
    return dedup


def grow_list(pg: PageData, tb: BBox | None, seed: BBox, max_rows: int = 400) -> BBox:
    """The list under a heading: grow from the heading while the next line is within a line or two and set in the same type
    size as the first row, so the notes and drawings around an index are not swallowed."""
    below = sorted((ln for ln in pg.lines if ln.horizontal and not in_box(ln, tb) and ln.y0 >= seed[1] and box_of(ln) != seed),
                   key=lambda ln: ln.y0)
    # the first rows sit just under the heading and may stick out on either side of it (a centred heading over a wide list)
    first = [ln for ln in below if -ln.h <= ln.y0 - seed[3] <= 3.0 * ln.h and max(seed[0] - ln.x1, ln.x0 - seed[2], 0) <= 10 * ln.h]
    if not first:
        return seed
    near = [ln for ln in below if 0 <= ln.y0 - seed[3] <= 8.0 * ln.h and max(seed[0] - ln.x1, ln.x0 - seed[2], 0) <= 10 * ln.h]
    sizes = Counter(round(ln.size) for ln in near)
    ref = float(sizes.most_common(1)[0][0])         # the type size most lines under the heading share
    rows0 = [ln for ln in first if abs(ln.size - ref) <= 0.1 * ref]
    region = union([seed] + [box_of(ln) for ln in rows0])
    # the list stays in the columns of its first rows: text in other columns belongs to something else
    lo, hi = min(ln.x0 for ln in rows0) - 2 * rows0[0].h, max(ln.x1 for ln in rows0) + 20 * rows0[0].h
    pool = [ln for ln in below if abs(ln.size - ref) <= 0.1 * ref and ln.x0 >= lo and ln.x1 <= hi]
    grew = True
    while grew and pool and max_rows > 0:
        grew = False
        for ln in list(pool):
            if gap(box_of(ln), region) <= 1.3 * ln.h:
                region = union([region, box_of(ln)])
                pool.remove(ln)
                max_rows -= 1
                grew = True
    return region


def untitled_index(pg: PageData, tb: BBox | None, vocab: Vocab, min_rows: int = 5) -> list[BBox]:
    """Boxes of lists whose rows are a sheet number and a title: ids aligned in a column at an even pitch."""
    ls = [ln for ln in pg.lines if ln.horizontal and not in_box(ln, tb)]
    ids = [ln for ln in ls if vocab.number_id.match(plain(ln.text).strip(" .:"))
           or vocab.letter_id.match(plain(ln.text).upper().strip(" .:"))]
    texts = [ln for ln in ls if ln not in ids and len(re.findall(r"[A-Za-z]", ln.text)) >= 3]
    out: list[BBox] = []
    used: set[int] = set()
    for a in sorted(ids, key=lambda ln: ln.cy):
        if id(a) in used:
            continue
        col = [a]
        used.add(id(a))
        while True:
            last = col[-1]
            nxt = [b for b in ids if id(b) not in used and 0 < b.cy - last.cy <= 2.6 * last.h
                   and (abs(b.x1 - last.x1) <= 1.5 * last.h or abs(b.x0 - last.x0) <= 1.5 * last.h)]
            if not nxt:
                break
            b = min(nxt, key=lambda b: b.cy - last.cy)
            col.append(b)
            used.add(id(b))
        if len(col) < min_rows:
            continue
        rows = [[t for t in texts if abs(t.cy - c.cy) <= 0.6 * max(t.h, c.h) and abs(t.cx - c.cx) <= 60 * c.h] for c in col]
        if sum(1 for r in rows if r) < 0.8 * len(col):
            continue
        boxes = [box_of(c) for c in col] + [box_of(t) for r in rows for t in r]
        u = union(boxes)
        pitch = [b.cy - a.cy for a, b in zip(col, col[1:])]
        mp = statistics.median(pitch)
        regular = sum(1 for p in pitch if abs(p - mp) <= 0.4 * mp) >= 0.8 * len(pitch)
        # an index is a compact list with an even pitch, not rows scattered over the sheet
        if regular and (u[2] - u[0]) <= 0.45 * pg.width and (u[3] - u[1]) <= 0.6 * pg.height:
            out.append(u)
    return out


def kind_after(rest: str, vocab: Vocab) -> bool:
    return classify_kind(rest, vocab) is not None


# ---- grid and cuts --------------------------------------------------------------------------------------------------

def _fill(shape: tuple[int, int], boxes: np.ndarray, cell: float) -> np.ndarray:
    """Cells touched by any of the boxes (n x 4, page points), by a 2-d difference array: no loop over boxes."""
    ny, nx = shape
    if not len(boxes):
        return np.zeros(shape, dtype=bool)
    j0 = np.clip((boxes[:, 0] // cell).astype(int), 0, nx - 1)
    j1 = np.clip((boxes[:, 2] // cell).astype(int), 0, nx - 1)
    i0 = np.clip((boxes[:, 1] // cell).astype(int), 0, ny - 1)
    i1 = np.clip((boxes[:, 3] // cell).astype(int), 0, ny - 1)
    diff = np.zeros((ny + 1, nx + 1), dtype=np.int32)
    np.add.at(diff, (i0, j0), 1)
    np.add.at(diff, (i0, j1 + 1), -1)
    np.add.at(diff, (i1 + 1, j0), -1)
    np.add.at(diff, (i1 + 1, j1 + 1), 1)
    return np.cumsum(np.cumsum(diff, axis=0), axis=1)[:ny, :nx] > 0


def occupancy(pg: PageData, tb: BBox | None, cell: float) -> tuple[np.ndarray, np.ndarray]:
    """Cells holding anything drawn or written (all) and cells holding drawn paths (paths). The title block, the sheet border,
    a content frame and rules across the sheet are left out: they would stop any whitespace cut."""
    nx, ny = int(math.ceil(pg.width / cell)), int(math.ceil(pg.height / cell))
    W, H = pg.width, pg.height
    r = pg.rects
    if len(r):
        w, h = r[:, 2] - r[:, 0], r[:, 3] - r[:, 1]
        keep = ~(((w > 0.45 * W) & (h > 0.45 * H)) | ((np.maximum(w, h) > 0.5 * max(W, H)) & (np.minimum(w, h) < 0.01 * max(W, H))))
        if tb is not None:
            cx, cy = (r[:, 0] + r[:, 2]) / 2, (r[:, 1] + r[:, 3]) / 2
            keep &= ~((cx >= tb[0]) & (cx <= tb[2]) & (cy >= tb[1]) & (cy <= tb[3]))
        r = r[keep]
    paths = _fill((ny, nx), r, cell)
    tl = np.array([box_of(ln) for ln in pg.lines if not in_box(ln, tb)], dtype=float).reshape(-1, 4)
    occ = paths | _fill((ny, nx), tl, cell)
    return occ, paths


def _runs(empty: np.ndarray):
    """Runs of True in a 1-d bool array as (start, end exclusive), ignoring runs at either end."""
    n = len(empty)
    i = 0
    while i < n:
        if empty[i]:
            j = i
            while j < n and empty[j]:
                j += 1
            if i > 0 and j < n:
                yield i, j
            i = j
        else:
            i += 1


def xy_cut(occ: np.ndarray, anchors: list[tuple[float, float]], cell: float, min_band: int):
    """Leaves as (rect in cells, [anchor indexes]). A cut needs a whitespace band of `min_band` cells and a title each side."""
    leaves = []

    def rec(r0, r1, c0, c1, idx):
        if len(idx) <= 1:
            leaves.append(((r0, r1, c0, c1), idx))
            return
        sub = occ[r0:r1, c0:c1]
        best = None
        for axis in (0, 1):
            counts = sub.sum(axis=1) if axis == 0 else sub.sum(axis=0)
            # a row or column is empty when only a stray mark (a border line, a leader) crosses it: at most 1% of its cells
            proj = counts > max(1, 0.01 * (c1 - c0 if axis == 0 else r1 - r0))
            for a, b in _runs(~proj):
                if b - a < min_band:
                    continue
                mid = ((r0 if axis == 0 else c0) + (a + b) / 2) * cell
                lo = [k for k in idx if anchors[k][1 - axis] < mid]
                hi = [k for k in idx if anchors[k][1 - axis] >= mid]
                if lo and hi and (best is None or b - a > best[0]):
                    best = (b - a, axis, a, b, lo, hi)
        if best is None:
            leaves.append(((r0, r1, c0, c1), idx))
            return
        _, axis, a, b, lo, hi = best
        if axis == 0:
            rec(r0, r0 + a, c0, c1, lo)
            rec(r0 + b, r1, c0, c1, hi)
        else:
            rec(r0, r1, c0, c0 + a, lo)
            rec(r0, r1, c0 + b, c1, hi)

    rec(0, occ.shape[0], 0, occ.shape[1], list(range(len(anchors))))
    return leaves


def nearest_owner(occ: np.ndarray, paths: np.ndarray, rect, idx: list[int], anchors: list[BBox], cell: float):
    """A leaf holding several titles that no whitespace band separates (views that overlap in x and in y). The drawn paths
    are cut into connected pieces (no dilation: two views are two pieces unless a line joins them); a piece goes whole to the
    title it touches, else to the nearest one, and shared cell by cell only if it touches several. Written text goes to the
    view of the nearest drawn cell. Without paths (a text only page) every cell goes to the nearest title."""
    from scipy import ndimage

    r0, r1, c0, c1 = rect
    sub = occ[r0:r1, c0:c1]
    psub = paths[r0:r1, c0:c1]
    ys, xs = np.nonzero(sub)
    px = (xs + c0 + 0.5) * cell
    py = (ys + r0 + 0.5) * cell
    d = np.stack([np.hypot(np.maximum(np.maximum(anchors[k][0] - px, px - anchors[k][2]), 0),
                           np.maximum(np.maximum(anchors[k][1] - py, py - anchors[k][3]), 0)) for k in idx])
    if not psub.any():
        return px, py, np.array(idx)[d.argmin(axis=0)], np.ones(len(px), dtype=bool)
    lab, nl = ndimage.label(psub, structure=np.ones((3, 3)))
    # text only cells take the label of the nearest drawn cell
    near = ndimage.distance_transform_edt(lab == 0, return_distances=False, return_indices=True)
    comp = lab[near[0][ys, xs], near[1][ys, xs]]
    ids = np.arange(1, nl + 1)
    pm = psub[ys, xs]
    # distance of each piece to each title, measured on its drawn cells only
    mind = np.stack([ndimage.minimum(np.where(pm, d[t], 1e9), comp, ids) for t in range(len(idx))])   # titles x pieces
    touch = mind <= 1.5 * cell
    none = ~touch.any(axis=0)
    touch[mind.argmin(axis=0)[none], np.nonzero(none)[0]] = True
    allowed = touch[:, comp - 1]                                                    # titles x cells
    own = np.where(allowed, d, 1e18).argmin(axis=0)
    # a small piece far from the main drawing of its view (a ruler, a stray frame) does not stretch the view
    size = np.bincount(comp[pm], minlength=nl + 1).astype(float)
    first_owner = np.full(nl + 1, -1)
    first_owner[comp[pm]] = own[pm]
    core = np.zeros(len(px), dtype=bool)
    for t in range(len(idx)):
        mine = first_owner == t
        if mine.any():
            big = size[mine].max()
            keep = mine & (size >= 0.15 * big)
            core |= (own == t) & keep[comp]
    return px, py, np.array(idx)[own], core


def segment(pg: PageData, tb: BBox | None, titles: list[TitleCand], method: str, vocab: Vocab):
    """Boxes of the views: list of (title index or None, bbox) and an owner function for lines."""
    mh = median_h(pg)
    cell = max(pg.width, pg.height) / 300.0
    occ, paths = occupancy(pg, tb, cell)
    anchors = [t.anchor for t in titles]
    centres = [((a[0] + a[2]) / 2, (a[1] + a[3]) / 2) for a in anchors]   # (x, y)
    min_band = max(2, int(math.ceil(1.5 * mh / cell)))
    owners: list[tuple[BBox, int | None, np.ndarray | None]] = []
    if method == "sheet" or not titles:
        ys, xs = np.nonzero(occ)
        if len(xs):
            b = (xs.min() * cell, ys.min() * cell, (xs.max() + 1) * cell, (ys.max() + 1) * cell)
            owners.append((b, None, None))
        return owners, cell
    if method == "voronoi":
        leaves = [((0, occ.shape[0], 0, occ.shape[1]), list(range(len(titles))))]
    else:
        leaves = xy_cut(occ, centres, cell, min_band)
    for rect, idx in leaves:
        r0, r1, c0, c1 = rect
        if len(idx) == 1:
            ys, xs = np.nonzero(occ[r0:r1, c0:c1])
            boxes = [anchors[idx[0]]]
            if len(xs):
                boxes.append(((xs.min() + c0) * cell, (ys.min() + r0) * cell, (xs.max() + c0 + 1) * cell, (ys.max() + r0 + 1) * cell))
            owners.append((union(boxes), idx[0], np.array([r0 * cell, r1 * cell, c0 * cell, c1 * cell])))
        else:
            xs, ys, own, core = nearest_owner(occ, paths, rect, idx, anchors, cell)
            for k in idx:
                sel = (own == k) & (core if (own == k)[core].any() else True)
                boxes = [anchors[k]]
                if sel.any():
                    boxes.append((xs[sel].min() - cell / 2, ys[sel].min() - cell / 2, xs[sel].max() + cell / 2, ys[sel].max() + cell / 2))
                owners.append((union(boxes), k, None))
    return owners, cell


# ---- levels ---------------------------------------------------------------------------------------------------------

def read_level(text: str, vocab: Vocab) -> tuple[str, int] | None:
    ft = fold(text)
    for rx in vocab.level_ordinals:
        m = rx.search(ft)
        if m:
            g = m.group(1)
            n = int(g) if g.isdigit() else vocab.ordinal_words.get(g)
            if n is not None:
                return (f"level {n}", n)
    for label, rank, rx in vocab.level_words:
        if rx.search(ft):
            return (label, rank)
    return None


# ---- one sheet ------------------------------------------------------------------------------------------------------

def title_block_texts(pg: PageData, vocab: Vocab) -> set[str]:
    tb, _ = find_title_block(pg, vocab)
    return {fold(ln.text) for ln in pg.lines if in_box(ln, tb) and len(ln.text.strip()) > 2}


def build_sheet(pg: PageData, vocab: Vocab, method: str = "xycut", constants: frozenset[str] = frozenset()) -> tuple[Sheet, list[Line]]:
    tb, hits = find_title_block(pg, vocab)
    number, title, default = (None, None, None)
    if tb is not None:
        number, title, default = read_title_block(pg, tb, hits, vocab, constants)
    sheet = Sheet(index=pg.index, number=number, number_source="title block" if number else "none", title=title,
                  width=pg.width, height=pg.height, title_block=tb, default_scale=default,
                  has_text_layer=pg.has_text_layer, n_lines=len(pg.lines))
    titles = find_titles(pg, tb, vocab, number)
    owners, cell = segment(pg, tb, titles, method, vocab)
    views: list[View] = []
    for n, (bbox, k, _) in enumerate(owners, 1):
        tc = titles[k] if k is not None else None
        v = View(id=f"{pg.index}.{n}", sheet=pg.index, kind=tc.kind if tc else "unknown", title=tc.title if tc else "",
                 labels=list(tc.labels) if tc else [], bbox=tuple(round(x, 1) for x in bbox),
                 title_bbox=tuple(round(x, 1) for x in tc.anchor) if tc else None)
        if tc and tc.scale:
            v.scale, v.scale_source = tc.scale, tc.scale_source
        views.append(v)
    # lines and paths to views, by box (smallest box wins when boxes overlap)
    unassigned = []
    for ln in pg.lines:
        if in_box(ln, tb):
            continue
        v = owner_of(ln.cx, ln.cy, views)
        if v is None:
            unassigned.append(ln)
        else:
            v.n_lines += 1
    if len(pg.rects) and views:
        c = (pg.rects[:, :2] + pg.rects[:, 2:]) / 2
        for v in views:
            b = v.bbox
            v.n_paths = int(((c[:, 0] >= b[0]) & (c[:, 0] <= b[2]) & (c[:, 1] >= b[1]) & (c[:, 1] <= b[3])).sum())
    sheet.unassigned_lines = len(unassigned)
    # scale for views without their own: one scale line inside the view, else the sheet default
    for v in views:
        if v.scale is None:
            inside = []
            for ln in pg.lines:
                if len(ln.text) <= 48 and not in_box(ln, tb) and in_view(ln, v):
                    s = parse_scale(ln.text, vocab)
                    if s is not None and not s.nts:
                        inside.append(s)
            ratios = {round(s.ratio, 2) for s in inside if s.ratio}
            if len(ratios) == 1:
                v.scale, v.scale_source = inside[0], "region"
            elif default is not None and v.kind in ("plan", "section", "elevation", "detail", "site", "unknown"):
                v.scale, v.scale_source = default, "sheet"
        if v.kind == "unknown" and sheet.title and len(views) == 1:
            k = classify_kind(sheet.title, vocab)
            if k is not None:
                v.kind, v.title = k, sheet.title
        if v.kind == "plan" or (v.kind == "unknown" and sheet.title):
            lv = read_level(v.title, vocab) or (read_level(sheet.title or "", vocab) if v.kind == "plan" else None)
            if lv:
                v.level, v.level_rank = lv
    sheet.views = views
    return sheet, unassigned


def in_view(ln: Line, v: View) -> bool:
    b = v.bbox
    return b[0] <= ln.cx <= b[2] and b[1] <= ln.cy <= b[3]


def owner_of(x: float, y: float, views: list[View]) -> View | None:
    best, area = None, None
    for v in views:
        b = v.bbox
        if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
            a = (b[2] - b[0]) * (b[3] - b[1])
            if area is None or a < area:
                best, area = v, a
    return best
