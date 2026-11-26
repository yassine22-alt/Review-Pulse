"""One version of a submission as the back check sees it: per page the words with boxes, the drawn objects with a shape
bucket, the revision clouds, and the sheet number and title the drawing set model reads.

Everything is in the page frame of PyMuPDF (points, y down, unrotated page), so a page whose /Rotate flag changed gives the
same snapshot.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from ..annotate.passages import Passage, sheet_passages

BBox = tuple[float, float, float, float]


@dataclass
class Word:
    text: str
    bbox: BBox


@dataclass
class PageSnap:
    index: int
    width: float
    height: float
    words: list[Word] = field(default_factory=list)
    lines: list[Word] = field(default_factory=list)          # text lines, for numbers with units and notes
    heights: list[float] = field(default_factory=list)       # font height of each line
    keys: list[int] = field(default_factory=list)            # drawn objects: bucket key
    feats: np.ndarray = field(default_factory=lambda: np.zeros((0, 5)))   # x0, y0, x1, y1, path length
    clouds: list[BBox] = field(default_factory=list)
    number: str | None = None
    number_source: str = "none"
    title: str | None = None
    title_block: BBox | None = None
    views: list[tuple[str, str, BBox]] = field(default_factory=list)      # id, title, box
    _passages: list[Passage] | None = None

    @property
    def key(self) -> str:
        from ..drawingset.vocab import norm_id
        return norm_id(self.number) if self.number else f"P{self.index + 1}"

    @property
    def readable(self) -> bool:
        """A page the vector diff can speak for: it has a text layer or enough drawn objects."""
        return len(self.words) >= 3 or len(self.keys) >= 30

    def view_at(self, box: BBox) -> str:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        best = ""
        for _id, title, b in self.views:
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                best = title or _id
        return best

    def passages(self) -> list[Passage]:
        if self._passages is None:
            H = self.height
            texts = [SimpleNamespace(text=w.text, bbox=(w.bbox[0], H - w.bbox[3], w.bbox[2], H - w.bbox[1]),
                                     height=h, kind="unknown") for w, h in zip(self.lines, self.heights, strict=True)]
            self._passages = sheet_passages(self.key, texts)
        return self._passages

    def token_bag(self) -> Counter:
        bag: Counter = Counter(f"w:{w.text.lower()}" for w in self.words)
        for k, f in zip(self.keys, self.feats, strict=True):
            bag[f"p:{k}:{int(round(f[2] - f[0]) // 3)}:{int(round(f[3] - f[1]) // 3)}"] += 1
        return bag


@dataclass
class Snapshot:
    path: str
    pages: list[PageSnap]
    name: str = ""

    def by_key(self) -> dict[str, PageSnap]:
        out: dict[str, PageSnap] = {}
        for p in self.pages:
            out.setdefault(p.key, p)
        return out


def _color(c) -> tuple:
    return tuple(round(v, 1) for v in c) if c else ()


def _length(items) -> float:
    total = 0.0
    for it in items:
        k = it[0]
        if k == "l":
            total += math.dist(it[1], it[2])
        elif k == "c":
            total += math.dist(it[1], it[4])
        elif k == "re":
            r = it[1]
            total += 2 * (abs(r.x1 - r.x0) + abs(r.y1 - r.y0))
        elif k == "qu":
            q = it[1]
            total += math.dist(q.ul, q.ur) + math.dist(q.ur, q.lr) + math.dist(q.lr, q.ll) + math.dist(q.ll, q.ul)
    return total


def _is_own(r, c: BBox) -> bool:
    """A drawn object that is the outline of the cloud with box `c` (inside it, and most of its size)."""
    inside = r.x0 >= c[0] - 1 and r.y0 >= c[1] - 1 and r.x1 <= c[2] + 1 and r.y1 <= c[3] + 1
    return inside and r.width * r.height >= 0.5 * (c[2] - c[0]) * (c[3] - c[1])


def _is_cloud(annot) -> bool:
    doc = annot.parent.parent
    kind = annot.type[1]
    if kind not in ("Polygon", "PolyLine", "Ink", "Square", "Circle", "FreeText", "Highlight"):
        return False
    be = doc.xref_get_key(annot.xref, "BE")
    if be[0] != "null" and "/S/C" in be[1].replace(" ", ""):
        return True
    info = annot.info
    text = f"{info.get('subject', '')} {info.get('content', '')} {info.get('title', '')}".lower()
    return "cloud" in text


def snapshot_pdf(path: str | Path, with_sheets: bool = True) -> Snapshot:
    import pymupdf

    path = Path(path)
    doc = pymupdf.open(str(path))
    pages: list[PageSnap] = []
    for pno in range(len(doc)):
        page = doc[pno]
        W, H = page.rect.width, page.rect.height
        if page.rotation % 180:
            W, H = H, W
        ps = PageSnap(pno, W, H)
        for w in page.get_text("words"):
            ps.words.append(Word(w[4], (w[0], w[1], w[2], w[3])))
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if txt:
                    ps.lines.append(Word(txt, tuple(ln["bbox"])))
                    ps.heights.append(max(s["size"] for s in ln["spans"]))
        try:
            for a in page.annots() or []:
                if _is_cloud(a):
                    r = a.rect
                    ps.clouds.append((r.x0, r.y0, r.x1, r.y1))
        except Exception:                                    # a damaged annotation must not stop the check
            pass
        keys, feats = [], []
        for d in page.get_drawings():
            r = d.get("rect")
            items = d.get("items") or []
            if r is None or not items:
                continue
            if any(_is_own(r, c) for c in ps.clouds):     # the outline of a revision cloud is a markup, not drawing content
                continue
            kinds = "".join("r" if it[0] in ("re", "qu") else it[0] for it in items)   # a turned rectangle may be written as a quad or four lines
            kinds = kinds.replace("llll", "r")
            w = d.get("width") or 0.0
            keys.append(hash((kinds, _color(d.get("color")), _color(d.get("fill")), round(w, 1))) & 0xFFFFFFF)
            feats.append((r.x0, r.y0, r.x1, r.y1, _length(items)))
        ps.keys = keys
        ps.feats = np.array(feats, dtype=float).reshape(-1, 5)
        pages.append(ps)
    n = len(doc)
    doc.close()
    snap = Snapshot(str(path), pages, path.stem)
    if with_sheets and n:
        _read_sheets(snap)
    return snap


def _read_sheets(snap: Snapshot) -> None:
    """Sheet number, title and views from the drawing set model. A failure leaves the page keyed by its position."""
    import pymupdf

    from ..drawingset import build_from_pdf

    try:
        ds = build_from_pdf(snap.path)
    except Exception:
        return
    with pymupdf.open(snap.path) as doc:
        rot = [p.rotation % 360 for p in doc]
    for sh in ds.sheets:
        if sh.index >= len(snap.pages):
            continue
        ps = snap.pages[sh.index]
        ps.number, ps.number_source, ps.title = sh.number, sh.number_source, sh.title
        if sh.number is not None and sh.number_source == "page index":
            ps.number = None
        if rot[sh.index] == 0:                              # the model works in the displayed frame
            ps.title_block = tuple(float(v) for v in sh.title_block) if sh.title_block else None
            ps.views = [(v.id, v.title, tuple(float(x) for x in v.bbox)) for v in sh.views]
