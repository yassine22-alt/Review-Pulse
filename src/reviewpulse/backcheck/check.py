"""The back check: previous comments against two versions of a submission.

Steps (all general methods, no model):
  1. sheets are paired by sheet number and title block, then by content; per sheet a turn and shift is found by voting;
  2. per pair a vector diff (words with places, drawn objects by shape bucket and place, blocks that moved as a whole),
     grouped into changed places; schedule cells are compared by row tag;
  3. per previous comment its place is found (box, else sheet), and the demand it carries is tested with the same evidence
     tools where it can be: a numeric limit against schedule values, fact graph values or figures printed in the region; a
     requested note against the sheet's passages (BM25). What cannot be settled is said so, with what a person must check;
  4. changes no comment asked for are NEW ISSUES; when the new PDF carries revision clouds, changes outside every cloud are
     CHANGES NOT CLOUDED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..drawingset.vocab import norm_id
from .align import SheetMatch, Transform, align_sheets, estimate_transform
from .demand import Demand, numbers_with_units, parse_demand, present, satisfies
from .diff import PageDiff, clusters, diff_pages
from .model import (
    CANNOT_TELL,
    CHANGED_NOT_SETTLED,
    MOVED,
    NOT_ADDRESSED,
    RESOLVED,
    BBox,
    Comment,
    Evidence,
    Place,
    Region,
    Verdict,
)
from .snapshot import PageSnap, Snapshot, snapshot_pdf
from .tables import CellChange, Table, all_tags, diff_tables, read_tables, row_values

PAD = 12.0                     # points around a comment box that still count as its place
TAG_RE = re.compile(r"^[A-Za-z]{1,3}[-.]?\d{1,3}[A-Za-z]?$")


def _inter(a: BBox, b: BBox, pad: float = 0.0) -> bool:
    return a[0] - pad <= b[2] and b[0] - pad <= a[2] and a[1] - pad <= b[3] and b[1] - pad <= a[3]


def _area(b: BBox) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _overlap(a: BBox, b: BBox) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _pad(b: BBox, p: float) -> BBox:
    return (b[0] - p, b[1] - p, b[2] + p, b[3] + p)


@dataclass
class PageCheck:
    match: SheetMatch
    T: Transform
    diff: PageDiff | None
    regions: list[Region] = field(default_factory=list)
    cells: list[CellChange] = field(default_factory=list)
    tables_old: list[Table] | None = None
    tables_new: list[Table] | None = None

    @property
    def old(self) -> PageSnap:
        return self.match.old

    @property
    def new(self) -> PageSnap:
        return self.match.new


@dataclass
class BackCheckResult:
    old_pdf: str
    new_pdf: str
    verdicts: list[Verdict]
    regions: list[Region]
    new_issues: list[Region]
    not_clouded: list[Region]
    clouds_without_change: list[dict]
    sheets: list[dict]
    sheets_removed: list[dict]
    sheets_added: list[dict]
    moved: list[dict]
    cells: list[dict]
    clouds_present: bool

    def by_id(self) -> dict[str, Verdict]:
        return {v.comment.id: v for v in self.verdicts}

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.verdicts:
            out[v.status] = out.get(v.status, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {"old_pdf": self.old_pdf, "new_pdf": self.new_pdf, "counts": self.counts(),
                "verdicts": [v.to_dict() for v in self.verdicts], "regions": [r.to_dict() for r in self.regions],
                "new_issues": [r.to_dict() for r in self.new_issues], "changes_not_clouded": [r.to_dict() for r in self.not_clouded],
                "clouds_without_change": self.clouds_without_change, "clouds_present": self.clouds_present,
                "sheets": self.sheets, "sheets_removed": self.sheets_removed, "sheets_added": self.sheets_added,
                "moved": self.moved, "schedule_cells": self.cells}


# ---- regions ----------------------------------------------------------------------------------------------------------------

def _regions(pc: PageCheck, any_cloud: bool, start: int) -> list[Region]:
    d, T, a, b = pc.diff, pc.T, pc.old, pc.new
    skip = {t.lower() for t in (a.number, b.number) if t} if pc.match.renumbered or (a.number != b.number) else set()
    items = [it for it in d.items if not (it.kind == "word" and it.text.lower() in skip)]
    out = []
    for k, g in enumerate(clusters(items)):
        box = (min(i.bbox[0] for i in g), min(i.bbox[1] for i in g), max(i.bbox[2] for i in g), max(i.bbox[3] for i in g))
        words_r = [i.text for i in sorted(g, key=lambda i: (round(i.bbox[1]), i.bbox[0])) if i.kind == "word" and i.side == "removed"]
        words_a = [i.text for i in sorted(g, key=lambda i: (round(i.bbox[1]), i.bbox[0])) if i.kind == "word" and i.side == "added"]
        nb = T.box(box)
        r = Region(f"R{start + k + 1}", a.key, b.key, a.index + 1, b.index + 1, box, nb,
                   view=b.view_at(nb) or a.view_at(box), n_removed=sum(i.side == "removed" for i in g),
                   n_added=sum(i.side == "added" for i in g), words_removed=words_r, words_added=words_a)
        if any_cloud:
            inside = 0
            for i in g:
                cx, cy = (i.bbox[0] + i.bbox[2]) / 2, (i.bbox[1] + i.bbox[3]) / 2
                nx0, ny0, nx1, ny1 = T.box((cx, cy, cx, cy))
                if any(c[0] - 4 <= nx0 <= c[2] + 4 and c[1] - 4 <= ny0 <= c[3] + 4 for c in b.clouds):
                    inside += 1
            r.clouded = inside >= 0.5 * len(g)
        out.append(r)
    return out


# ---- the check ---------------------------------------------------------------------------------------------------------------

class _Checker:
    def __init__(self, old: Snapshot, new: Snapshot, facts=None):
        self.old, self.new, self.facts = old, new, facts
        self.pairs, self.removed, self.added = align_sheets(old, new)
        self.any_cloud = any(p.clouds for p in new.pages)
        self.pc: dict[int, PageCheck] = {}
        self.regions: list[Region] = []
        for m in self.pairs:
            T = estimate_transform(m.old, m.new) if (m.old.readable and m.new.readable) else Transform(ok=False, method="unreadable")
            diff = diff_pages(m.old, m.new, T) if T.ok else None
            pc = PageCheck(m, T, diff)
            if diff is not None:
                pc.regions = _regions(pc, self.any_cloud, len(self.regions))
                self.regions += pc.regions
                if diff.items:
                    pc.tables_old = read_tables(old.path, m.old.index)
                    pc.tables_new = read_tables(new.path, m.new.index)
                    pc.cells = diff_tables(pc.tables_old, pc.tables_new, m.old, m.new)
            self.pc[m.old.index] = pc

    def tables(self, pc: PageCheck) -> tuple[list[Table], list[Table]]:
        if pc.tables_old is None:
            pc.tables_old = read_tables(self.old.path, pc.old.index)
            pc.tables_new = read_tables(self.new.path, pc.new.index)
        return pc.tables_old, pc.tables_new or []

    # -- locating a comment
    def old_page(self, c: Comment) -> PageSnap | None:
        if c.sheet:
            key = norm_id(c.sheet)
            for p in self.old.pages:
                if p.number and p.key == key:
                    return p
        if c.page and 1 <= c.page <= len(self.old.pages):
            return self.old.pages[c.page - 1]
        if c.sheet:
            key = norm_id(c.sheet)
            for p in self.old.pages:
                if p.key == key:
                    return p
        return None

    def verdict(self, c: Comment) -> Verdict:
        ev = Evidence()
        op = self.old_page(c)
        if op is None:
            return Verdict(c, CANNOT_TELL, "the comment names no sheet or page that exists in the old set", ev)
        ev.old_place = Place(op.index + 1, op.number, op.view_at(c.bbox) if c.bbox else "", c.bbox)
        pc = self.pc.get(op.index)
        if pc is None:
            ev.person_must_check = f"Sheet {op.number or op.index + 1} has no counterpart in the new set. Check whether it was removed or replaced."
            return Verdict(c, CANNOT_TELL, "the sheet is not in the new set (removed, or too different to pair)", ev)
        a, b, T = pc.old, pc.new, pc.T
        ev.new_place = Place(b.index + 1, b.number, "", None)
        if not T.ok or pc.diff is None:
            ev.person_must_check = "The two versions of this sheet could not be aligned (a scan, or too little drawn content)."
            return Verdict(c, CANNOT_TELL, f"the sheet cannot be compared ({T.method})", ev)
        zone = _pad(c.bbox, PAD) if c.bbox else None
        if zone is not None:
            ev.new_place.bbox = T.box(c.bbox)
            ev.new_place.view = b.view_at(ev.new_place.bbox)
        demand = parse_demand(c.text)
        ev.demand = demand.describe()
        regs = [r for r in pc.regions if zone is None or _inter(r.bbox_old, zone)]
        moved = [m for m in pc.diff.moved if zone is not None and _overlap(m.bbox_old, zone) >= 0.4 * max(1.0, min(_area(zone), _area(m.bbox_old)))]
        renumbered = (a.number or "") != (b.number or "") and (a.number or b.number)
        if moved:
            m = moved[0]
            ev.new_place.bbox = (zone[0] + m.dx, zone[1] + m.dy, zone[2] + m.dx, zone[3] + m.dy)
            ev.checks.append(f"the block holding this place moved by ({m.dx:.0f}, {m.dy:.0f}) points with its content unchanged")
        if renumbered:
            ev.checks.append(f"the sheet number changed from {a.number} to {b.number}")
        cells: list[CellChange] = []
        tags = self._tags(c, pc, zone, demand)
        if tags:
            cells = [x for x in pc.cells if x.tag in tags]
        changed = bool(regs) or bool(cells)
        for r in regs:
            r.linked.append(c.id)
        for r in pc.regions:                      # a changed schedule row answers a comment on its tag
            if r not in regs and any(x.box_old is not None and _inter(r.bbox_old, x.box_old) for x in cells):
                r.linked.append(c.id)
        if regs:
            ev.diff = "; ".join(r.describe() for r in regs[:3])
        if cells:
            ev.diff = "; ".join(filter(None, [ev.diff, *[x.describe() for x in cells[:4]]]))
        if demand.kind == "presence":
            return self._presence(c, demand, pc, ev, changed, bool(moved), renumbered)
        if demand.kind in ("min", "max"):
            return self._numeric(c, demand, pc, ev, changed, bool(moved), renumbered, zone, tags)
        if changed:
            ev.person_must_check = "The place changed but the comment carries no limit or requested text a tool can test. Read the new version there."
            return Verdict(c, CHANGED_NOT_SETTLED, "the region changed; the comment is not testable, so it is not called resolved", ev)
        return self._unchanged(c, ev, bool(moved), renumbered, pc)

    def _unchanged(self, c, ev, moved, renumbered, pc) -> Verdict:
        if moved or renumbered:
            what = "the view moved on the sheet" if moved else f"the sheet is now {pc.new.number or pc.new.index + 1}"
            ev.old_value = ev.new_value = "unchanged"
            return Verdict(c, MOVED, f"{what}; the content at the comment's place is the same", ev)
        ev.old_value = ev.new_value = "unchanged"
        ev.diff = "no difference at this place"
        return Verdict(c, NOT_ADDRESSED, "nothing changed at the place of the comment", ev)

    def _tags(self, c: Comment, pc: PageCheck, zone, demand: Demand) -> set[str]:
        if demand.kind not in ("min", "max") and not pc.cells:
            return set()
        t_old, t_new = self.tables(pc)
        known = all_tags(t_old) | all_tags(t_new)
        if not known:
            return set()
        out = {w for w in re.split(r"[^A-Za-z0-9.\-]+", c.text) if w in known}
        if zone is not None:
            out |= {w.text for w in pc.old.words if w.text in known and TAG_RE.match(w.text) and _inter(w.bbox, zone)}
        return out

    # -- presence of a requested note
    def _presence(self, c, demand, pc, ev, changed, moved, renumbered) -> Verdict:
        texts_new = [p.text for p in pc.new.passages()] + [w.text for w in pc.new.lines]
        texts_old = [p.text for p in pc.old.passages()] + [w.text for w in pc.old.lines]
        in_new, best_new, cov_new = present(texts_new, demand.phrase)
        in_old, best_old, cov_old = present(texts_old, demand.phrase)
        ev.old_value = best_old if in_old else "(not present)"
        ev.new_value = best_new if in_new else "(not present)"
        ev.checks.append(f"requested words found in the old sheet: {in_old} (best coverage {cov_old}); in the new sheet: {in_new} (best coverage {cov_new})")
        if in_new and not in_old:
            ev.diff = f"new text: {best_new}"
            return Verdict(c, RESOLVED, "the requested text is now on the sheet and was not there before", ev)
        if in_new and in_old:
            if changed:
                ev.person_must_check = "The text asked for was already on the sheet before this revision. Check what the comment meant."
                return Verdict(c, CHANGED_NOT_SETTLED, "the requested text was already present and the place changed", ev)
            return self._unchanged(c, ev, moved, renumbered, pc)
        elsewhere = self._elsewhere(demand.phrase, pc.new.index)
        if elsewhere:
            ev.person_must_check = f"The requested text appears on another sheet ({elsewhere}), not on the sheet of the comment."
            return Verdict(c, CHANGED_NOT_SETTLED, f"the requested text is only on sheet {elsewhere}", ev)
        if changed:
            ev.person_must_check = "The place changed but the requested text is not there. Read the new version."
            return Verdict(c, CHANGED_NOT_SETTLED, "the place changed but the requested text is not present", ev)
        return self._unchanged(c, ev, moved, renumbered, pc)

    def _elsewhere(self, phrase: str, skip_index: int) -> str:
        for p in self.new.pages:
            if p.index == skip_index:
                continue
            ok, _t, _c = present([q.text for q in p.passages()] + [w.text for w in p.lines], phrase)
            if ok:
                return p.number or f"page {p.index + 1}"
        return ""

    # -- a numeric limit
    def _values(self, side: str, pc, demand, zone, tags, cells) -> list[tuple[float, str]]:
        out: list[tuple[float, str]] = []
        page = pc.old if side == "old" else pc.new
        pdf = self.old.path if side == "old" else self.new.path
        t_old, t_new = self.tables(pc)
        rows_of = t_old if side == "old" else t_new
        for tag in sorted(tags):
            cells_of_tag = row_values(rows_of, tag)
            pick = [cl for cl in cells_of_tag.values() if cl.value_si is not None and (not demand.quantity or cl.meaning == demand.quantity)]
            if not demand.quantity:
                changed_h = {x.header for x in cells if x.tag == tag}
                pick = [cl for cl in pick if cl.header in changed_h] or pick
            for cl in pick[:1]:
                out.append((cl.value_si, f"schedule {tag} {cl.header} = {cl.text}"))
            if self.facts is not None and demand.quantity:
                got = self.facts.value(side, pdf, page.index, tag, demand.quantity)
                if got:
                    out.append((got[0], f"fact graph {tag} {demand.quantity} = {got[0]:g} ({got[1]})"))
        if not out and zone is not None:
            dim = demand.dim
            for ln in page.lines:
                if _inter(ln.bbox, zone):
                    for v, d, text in numbers_with_units(ln.text):
                        if d == dim:
                            out.append((v, f"printed '{text}'"))
        return out

    def _numeric(self, c, demand, pc, ev, changed, moved, renumbered, zone, tags) -> Verdict:
        if not changed:
            ov = self._values("old", pc, demand, zone, tags, [])
            if ov:
                ev.old_value = ev.new_value = "; ".join(s for _v, s in ov)
            return self._unchanged(c, ev, moved, renumbered, pc)
        cells = [x for x in pc.cells if x.tag in tags]
        ov = self._values("old", pc, demand, zone, tags, cells)
        nv = self._values("new", pc, demand, zone, tags, cells)
        ev.old_value = "; ".join(s for _v, s in ov) or "(no value read)"
        ev.new_value = "; ".join(s for _v, s in nv) or "(no value read)"
        if not nv or not ov:
            ev.person_must_check = f"The place changed but the {demand.quantity or 'figure'} could not be read in both versions. Measure it in the new set against {demand.describe()}."
            return Verdict(c, CHANGED_NOT_SETTLED, "the place changed; the value could not be read in both versions", ev)
        new_ok = all(satisfies(demand, v) for v, _s in nv)
        old_bad = any(not satisfies(demand, v) for v, _s in ov)
        differs = sorted(round(v, 4) for v, _ in ov) != sorted(round(v, 4) for v, _ in nv)
        ev.checks.append(f"limit {demand.describe()}: old values {[round(v, 3) for v, _ in ov]}, new values {[round(v, 3) for v, _ in nv]}")
        if new_ok and old_bad and differs:
            return Verdict(c, RESOLVED, "the value now meets the limit it did not meet before", ev)
        if new_ok and not old_bad:
            ev.person_must_check = "The value already met the limit in the old set. Check what the comment pointed at."
            return Verdict(c, CHANGED_NOT_SETTLED, "the value met the limit before and after; the comment is not explained by it", ev)
        ev.person_must_check = "The value still does not meet the limit."
        return Verdict(c, CHANGED_NOT_SETTLED, "the place changed but the value still does not meet the limit", ev)

    # -- the report parts
    def result(self, verdicts: list[Verdict]) -> BackCheckResult:
        new_issues = [r for r in self.regions if not r.linked]
        not_clouded = [r for r in self.regions if r.clouded is False] if self.any_cloud else []
        cwc = []
        for m in self.pairs:
            pc = self.pc[m.old.index]
            for cb in m.new.clouds:
                if pc.diff is None:
                    continue
                if not any(_inter(pc.T.box(r.bbox_old), _pad(cb, 4)) for r in pc.regions):
                    cwc.append({"sheet": m.new.key, "page": m.new.index + 1, "cloud": [round(x, 1) for x in cb]})
        sheets = [{"old_page": m.old.index + 1, "new_page": m.new.index + 1, "old_sheet": m.old.number, "new_sheet": m.new.number,
                   "how": m.how, "similarity": m.score, "renumbered": bool((m.old.number or "") != (m.new.number or "")),
                   "transform": self.pc[m.old.index].T.to_dict(), "n_changed_places": len(self.pc[m.old.index].regions)} for m in self.pairs]
        moved = [{"sheet": pc.old.key, "page": pc.old.index + 1, "old_box": [round(x, 1) for x in mv.bbox_old],
                  "new_box": [round(x, 1) for x in mv.bbox_new], "shift": [round(mv.dx, 1), round(mv.dy, 1)], "objects": mv.n}
                 for pc in self.pc.values() if pc.diff for mv in pc.diff.moved]
        cells = [{"sheet": pc.old.key, "page": pc.old.index + 1, "change": x.describe(), "tag": x.tag, "header": x.header,
                  "old": x.old_text, "new": x.new_text} for pc in self.pc.values() for x in pc.cells]
        return BackCheckResult(self.old.path, self.new.path, verdicts, self.regions, new_issues, not_clouded, cwc, sheets,
                               [{"page": p.index + 1, "sheet": p.number} for p in self.removed],
                               [{"page": p.index + 1, "sheet": p.number} for p in self.added], moved, cells, self.any_cloud)


def back_check(old_pdf: str | Path, new_pdf: str | Path, comments: list[Comment], *, facts=None,
               old_snap: Snapshot | None = None, new_snap: Snapshot | None = None) -> BackCheckResult:
    """Decide every previous comment against the new version. `facts` (a `FactSource`) adds fact graph values through the ledger."""
    old = old_snap or snapshot_pdf(old_pdf)
    new = new_snap or snapshot_pdf(new_pdf)
    ck = _Checker(old, new, facts)
    verdicts = [ck.verdict(c) for c in comments]
    return ck.result(verdicts)
