"""Callouts and cross references: parse them from the text lines, resolve them to a view or a sheet.

Grammars come from vocab.yaml. Two things guard against false callouts without any label: a sheet token must have the shape
of the sheet numbers the set itself uses (or be one of them), and callouts inside a legend or an index are examples or lists,
not references, so they are set apart.
"""

from __future__ import annotations

import re

from .model import BBox, Callout, Sheet
from .pagedata import Line, PageData
from .views import box_of, gap, in_box, union
from .vocab import Vocab, fold, norm_id, plain, shape


def paragraphs(pg: PageData) -> list[list[Line]]:
    """Lines that follow each other in the same text block (stacked, overlapping in x) read as one paragraph."""
    out: list[list[Line]] = []
    for ln in pg.lines:
        if out:
            prev = out[-1][-1]
            if (ln.horizontal and prev.horizontal and -0.3 * ln.h <= ln.y0 - prev.y1 < 0.9 * ln.h
                    and ln.x0 < prev.x1 and prev.x0 < ln.x1):
                out[-1].append(ln)
                continue
        out.append([ln])
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", plain(text))


def parse_text_callouts(pg: PageData, vocab: Vocab, tb: BBox | None) -> list[Callout]:
    found: list[Callout] = []
    for para in paragraphs(pg):
        para = [ln for ln in para if not in_box(ln, tb)]
        if not para:
            continue
        text = " ".join(_clean(ln.text) for ln in para)
        # char offset to line, to place the callout
        starts, pos = [], 0
        for ln in para:
            starts.append(pos)
            pos += len(_clean(ln.text)) + 1
        claimed: list[tuple[int, int]] = []
        for name, rx in vocab.grammars:
            for m in rx.finditer(text):
                if any(m.start() < e and s < m.end() for s, e in claimed):
                    continue
                claimed.append((m.start(), m.end()))
                i = max(k for k, s in enumerate(starts) if s <= m.start())
                gd = m.groupdict()
                kind = None
                if gd.get("kind"):
                    fk = fold(gd["kind"])
                    kind = next((k for k, rxk in vocab.callout_kinds.items() if rxk.search(fk)), None)
                found.append(Callout(
                    sheet=pg.index, text=m.group(0), grammar=name,
                    view_label=gd["view"].replace(" ", "").upper() if gd.get("view") else None,
                    target_sheet=gd["sheet"].strip() if gd.get("sheet") else None, kind=kind, where=box_of(para[i])))
    return found


def _exact(token: str) -> str:
    """A sheet number as printed (upper case, no spaces). Not normalised: keynote tag E10 is not sheet E1.0."""
    return plain(token).upper().replace(" ", "")


def parse_bubbles(pg: PageData, vocab: Vocab, tb: BBox | None, known: set[str] | None = None) -> list[Callout]:
    """A callout bubble drawn as two short stacked lines: a view label and a sheet number. Offices differ on which one is on
    top, so both readings are kept (`alt`) and the set decides: the reading that names a sheet of the set and a view on it wins.
    To keep stacked dimension figures and symbol letters out, one of the two must carry a letter (A3.01, S6) and the other
    must be a plain number or the number of a sheet of the set (`known`, exactly as printed). A lettered view stacked over a lettered
    sheet number that is not a known sheet is a known loss."""
    known = known or set()
    out = []
    ls = [ln for ln in pg.lines if ln.horizontal and not in_box(ln, tb)]
    toks = [ln for ln in ls if re.match(r"^\d{1,3}$", ln.text.strip())
            or vocab.letter_id.match(plain(ln.text).upper().strip())]
    seen: set[frozenset] = set()
    for s in toks:
        if not vocab.letter_id.match(plain(s.text).upper().strip()):
            continue
        best = None
        for n in toks:
            if n is s:
                continue
            plain_num = bool(re.match(r"^\d{1,3}$", n.text.strip()))
            if not plain_num and _exact(n.text) not in known and _exact(s.text) not in known:
                continue
            dy = abs(n.cy - s.cy)
            if dy <= 2.6 * max(n.h, s.h) and abs(n.cx - s.cx) <= 1.2 * max(n.x1 - n.x0, s.x1 - s.x0) and dy > 0.3 * s.h:
                d = gap(box_of(n), box_of(s))
                if best is None or d < best[0]:
                    best = (d, n)
        if best:
            n = best[1]
            pair = frozenset((id(n), id(s)))
            if pair in seen:
                continue
            seen.add(pair)
            nt, st = n.text.strip(), plain(s.text).strip()
            top, bottom = (nt, st) if n.cy < s.cy else (st, nt)
            out.append(Callout(sheet=pg.index, text=f"{top} / {bottom}", grammar="bubble", view_label=nt.upper(),
                               target_sheet=st, kind=None, where=union([box_of(n), box_of(s)]), alt=(st.upper(), nt)))
    return out


def sheet_shapes(sheets: list[Sheet]) -> set[str]:
    return {shape(s.number) for s in sheets if s.number}


_RANK = {"view": 5, "sheet": 5, "partial": 4, "unresolved_sheet": 3, "ambiguous": 2, "unresolved_view": 2, "rejected_shape": 1}


def resolve(callouts: list[Callout], sheets: list[Sheet], shapes: set[str], legend_view_ids: set[str]) -> None:
    """Fill status and target of every callout in place."""
    by_key: dict[str, list[Sheet]] = {}
    for s in sheets:
        by_key.setdefault(s.key, []).append(s)
    by_index = {s.index: s for s in sheets}
    for c in callouts:
        src = by_index[c.sheet]
        sv = None
        for v in src.views:
            b = v.bbox
            cx, cy = (c.where[0] + c.where[2]) / 2, (c.where[1] + c.where[3]) / 2
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3] and (sv is None or _area(v.bbox) < _area(sv.bbox)):
                sv = v
        c.source_view = sv.id if sv else None
        if sv is not None and sv.id in legend_view_ids:
            c.status, c.reason = "in_legend", "drawn inside a legend or index: an example or a list, not a reference"
            continue
        res = _attempt(c, c.view_label, c.target_sheet, src, sheets, by_key, shapes)
        if c.alt is not None and res[0] not in ("view", "sheet"):
            alt = _attempt(c, c.alt[0], c.alt[1], src, sheets, by_key, shapes)
            if _RANK[alt[0]] > _RANK[res[0]]:
                res = alt[:3] + ((alt[3] + "; " if alt[3] else "") + "read the other way round (sheet number on top)",)
                c.view_label, c.target_sheet = c.alt
        c.status, c.target_view, c.target_sheet_index, c.reason = res[0], res[1], res[2], res[3]


def _attempt(c: Callout, view_label: str | None, sheet_token: str | None, src: Sheet, sheets: list[Sheet],
             by_key: dict[str, list[Sheet]], shapes: set[str]):
    """(status, target view id, target sheet index, reason) for one reading of a callout."""
    label = norm_id(view_label) if view_label else None
    if sheet_token:
        key = norm_id(sheet_token)
        if key not in by_key and shape(sheet_token) not in shapes:
            return ("rejected_shape", None, None,
                    f"'{sheet_token}' is not shaped like the set's sheet numbers {sorted(shapes)} (likely a code, a product number or a sheet outside the set)")
        cands = sorted(by_key.get(key, []), key=lambda t: abs(t.index - src.index))
        if not cands:
            return ("unresolved_sheet", None, None, f"sheet {sheet_token} is not in the set")
        # a file holding several designs repeats sheet numbers: the nearest sheet that holds the view is meant
        tgt = cands[0]
        if label is None:
            return ("sheet", None, tgt.index, "")
        for t in cands:
            hit = _find_view(t, label, c.kind)
            if hit is not None:
                return ("view", hit.id, t.index, "" if len(cands) == 1 else f"{len(cands)} sheets share the number, nearest holding the view taken")
        return ("partial", None, tgt.index, f"sheet {tgt.number} exists, no view {view_label} found on it ({len(tgt.views)} views found)")
    if label is None:
        return ("unresolved_view", None, None, "no label")
    hit = _find_view(src, label, c.kind)
    if hit is not None:
        return ("view", hit.id, src.index, "")
    others = [(s, h) for s in sheets if s is not src for h in [_find_view(s, label, c.kind)] if h is not None]
    if len(others) == 1:
        return ("view", others[0][1].id, others[0][0].index, "found on another sheet (unique)")
    if len(others) > 1:
        return ("ambiguous", None, None, f"view {view_label} exists on {len(others)} other sheets, none on this one")
    return ("unresolved_view", None, None, f"no view {view_label} on this sheet or any other")


def _area(b: BBox) -> float:
    return (b[2] - b[0]) * (b[3] - b[1])


def _find_view(sheet: Sheet, label: str, kind: str | None):
    ms = [v for v in sheet.views if any(norm_id(lb) == label for lb in v.labels)]
    if kind:
        same = [v for v in ms if v.kind == kind]
        if same:
            return same[0]
    return ms[0] if ms else None
