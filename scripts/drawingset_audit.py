"""Audit of the drawing set model on real PDF sets. No label is needed.

    python scripts/drawingset_audit.py data/real_plans/chief_architect_austin.pdf [more.pdf] [--json out.json]

For every set it reports:
  views        views found per sheet, their kinds, and how many carry their own scale (and where the scale came from)
  callouts     how many resolve to a view or a sheet that exists, and every case that does not, with the reason
  null         the same share when the view labels are shuffled between callouts (what chance would give)
  baselines    sheet level resolution against view level; the three ways of cutting a sheet (X-Y cut, nearest title, none)
               compared on two label free measures: views overlapping each other, and views holding a scale line that
               is not their own
  metamorphic  rotate every page, rename a sheet number, move a view: the callouts must still resolve the same way
  index        the sheet index against the title blocks
  legends      legend rows kept as exemplars; levels given to plan views
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from reviewpulse.drawingset import METHODS, build_drawing_set, from_pdf
from reviewpulse.drawingset.pagedata import PageData, canonicalize, rotate_cw90, translate_box
from reviewpulse.drawingset.refs import resolve
from reviewpulse.drawingset.scale import parse_scale
from reviewpulse.drawingset.views import in_box
from reviewpulse.drawingset.vocab import load_vocab

RESOLVED = ("view", "sheet")
IN_SCOPE_BAD = ("partial", "unresolved_sheet", "unresolved_view", "ambiguous")
SCALED_KINDS = ("plan", "section", "elevation", "detail", "site")


def context_of(pages: list[PageData], c) -> str:
    pg = next(p for p in pages if p.index == c.sheet)
    near = [ln for ln in pg.lines if abs(ln.cx - (c.where[0] + c.where[2]) / 2) < 120 and abs(ln.cy - (c.where[1] + c.where[3]) / 2) < 40]
    return " | ".join(ln.text for ln in near[:6])[:140]


def callout_report(ds, pages) -> dict:
    cs = ds.callouts
    c = Counter(x.status for x in cs)
    scope = [x for x in cs if x.status in RESOLVED + IN_SCOPE_BAD]
    resolved = [x for x in scope if x.status in RESOLVED]
    uniq = {(x.sheet, x.view_label, x.target_sheet, x.status) for x in scope}
    uniq_ok = {(x.sheet, x.view_label, x.target_sheet, x.status) for x in resolved}
    with_view = [x for x in scope if x.view_label]
    sheet_known = [x for x in with_view if x.target_sheet_index is not None]
    view_ok = [x for x in with_view if x.status == "view"]
    bad = [x for x in scope if x.status in IN_SCOPE_BAD]
    seen, cases = set(), []
    for x in bad:
        key = (x.sheet, x.text, x.status)
        if key in seen:
            continue
        seen.add(key)
        cases.append({"sheet": x.sheet, "text": x.text, "grammar": x.grammar, "status": x.status, "reason": x.reason,
                      "context": context_of(pages, x)})
    rej = Counter((x.text, x.reason[:40]) for x in cs if x.status == "rejected_shape")
    return {"rejected_examples": [f"{t} x{n}" for (t, _), n in rej.most_common(12)], "all": dict(c), "in_scope": len(scope), "resolved": len(resolved),
            "rate": round(len(resolved) / len(scope), 3) if scope else None,
            "unique_in_scope": len(uniq), "unique_resolved": len(uniq_ok),
            "unique_rate": round(len(uniq_ok) / len(uniq), 3) if uniq else None,
            "with_view_label": len(with_view), "sheet_level_rate": round(len(sheet_known) / len(with_view), 3) if with_view else None,
            "view_level_rate": round(len(view_ok) / len(with_view), 3) if with_view else None,
            "rejected_shape": c.get("rejected_shape", 0), "in_legend": c.get("in_legend", 0), "unresolved_cases": cases}


def null_rate(ds, seed: int = 0, n: int = 20) -> dict:
    """Shuffle the view labels among the callouts that name a sheet and a view; how many still resolve (chance)."""
    pool = [c for c in ds.callouts if c.view_label and c.target_sheet and c.status in RESOLVED + IN_SCOPE_BAD]
    if len(pool) < 5:
        return {"n": len(pool), "real": None, "null": None}
    real = sum(c.status == "view" for c in pool) / len(pool)
    views = {v.id: v for v in ds.views()}

    def kind_ok(cs):
        """Of callouts that say what they point to (detail, section, elevation) and resolved to a view: share where the view is of that kind."""
        have = [c for c in cs if c.status == "view" and c.kind]
        return (sum(1 for c in have if views[c.target_view].kind == c.kind), len(have))

    k_real = kind_ok(pool)
    rng = random.Random(seed)
    shapes = set(ds.shapes)
    rates, kinds = [], []
    for _ in range(n):
        cp = [copy.copy(c) for c in pool]
        labels = [c.view_label for c in cp]
        rng.shuffle(labels)
        for c, lab in zip(cp, labels, strict=True):
            c.view_label, c.alt, c.status, c.target_view = lab, None, "unresolved", None
        resolve(cp, ds.sheets, shapes, set())
        rates.append(sum(c.status == "view" for c in cp) / len(cp))
        ok, tot = kind_ok(cp)
        kinds.append(ok / tot if tot else 0.0)
    return {"n": len(pool), "real": round(real, 3), "null_mean": round(sum(rates) / len(rates), 3), "null_max": round(max(rates), 3),
            "kind_words_agree_real": f"{k_real[0]}/{k_real[1]}", "kind_words_agree_null_mean": round(sum(kinds) / len(kinds), 3)}


def view_report(ds) -> dict:
    vs = ds.views()
    kinds = Counter(v.kind for v in vs)
    scaled = [v for v in vs if v.kind in SCALED_KINDS]
    src = Counter(v.scale_source for v in scaled)
    own = sum(1 for v in scaled if v.scale_source in ("title", "own line", "region"))
    multi = sum(1 for s in ds.sheets if len({round(v.scale.ratio, 1) for v in s.views if v.scale and v.scale.ratio}) > 1)
    per_sheet = Counter(len(s.views) for s in ds.sheets)
    return {"sheets": len(ds.sheets), "with_number": sum(1 for s in ds.sheets if s.number), "with_title_block": sum(1 for s in ds.sheets if s.title_block),
            "views": len(vs), "views_per_sheet": dict(sorted(per_sheet.items())), "kinds": dict(kinds), "scaled_kind_views": len(scaled),
            "scale_sources": dict(src), "own_scale": own, "sheets_with_several_scales": multi,
            "levels": sorted({(v.level, v.level_rank) for v in vs if v.level}, key=lambda t: t[1])}


def segmentation_measures(ds, pages) -> dict:
    """Two label free measures of how well a sheet was cut: overlap among views, and foreign scale lines inside a view."""
    vocab = load_vocab()
    by = {p.index: p for p in pages}
    ov_num = ov_den = 0.0
    contaminated = scaled = 0
    for s in ds.sheets:
        vs = s.views
        for i, v in enumerate(vs):
            b = v.bbox
            a = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
            inter = 0.0
            for j, w in enumerate(vs):
                if i != j:
                    c = w.bbox
                    inter += max(0, min(b[2], c[2]) - max(b[0], c[0])) * max(0, min(b[3], c[3]) - max(b[1], c[1]))
            ov_num += min(a, inter)
            ov_den += a
            if v.scale and v.scale.ratio:
                scaled += 1
                foreign = False
                for ln in by[s.index].lines:
                    if b[0] <= ln.cx <= b[2] and b[1] <= ln.cy <= b[3] and len(ln.text) <= 48 and not in_box(ln, s.title_block):
                        sc = parse_scale(ln.text, vocab)
                        if sc is not None and sc.ratio and abs(sc.ratio - v.scale.ratio) > 0.5:
                            foreign = True
                            break
                contaminated += foreign
    return {"overlap_share": round(ov_num / ov_den, 3) if ov_den else None, "scaled_views": scaled,
            "views_with_foreign_scale": contaminated,
            "foreign_scale_share": round(contaminated / scaled, 3) if scaled else None}


def signature(ds, drop_text: bool = False) -> dict:
    """What must not change under rotation, a renamed number or a moved view (names, not ids)."""
    by_idx = {s.index: s for s in ds.sheets}
    views = {v.id: v for v in ds.views()}

    def tv(c):
        v = views.get(c.target_view) if c.target_view else None
        return (v.title, tuple(v.labels)) if v else None

    cs = sorted(((c.sheet, "" if drop_text else c.text, c.status, tv(c), c.target_sheet_index) for c in ds.callouts), key=repr)
    vs = sorted(((s.index, v.kind, v.title, () if drop_text else tuple(v.labels), v.scale.text if v.scale else None, v.level)
                 for s in ds.sheets for v in s.views), key=repr)
    nums = [(s.index, s.title) for s in by_idx.values()]
    return {"callouts": cs, "views": vs, "titles": nums}


def compare_sig(a: dict, b: dict, rename: tuple[str, str] | None = None) -> dict:
    def fix(t):
        return t

    ca, cb = Counter(map(repr, a["callouts"])), Counter(map(repr, b["callouts"]))
    va, vb = Counter(map(repr, a["views"])), Counter(map(repr, b["views"]))
    n_c = sum(ca.values())
    n_v = sum(va.values()) or 1
    same_status = Counter((c[0], c[2]) for c in a["callouts"]) == Counter((c[0], c[2]) for c in b["callouts"])
    return {"callouts_same": round(sum((ca & cb).values()) / n_c, 3) if n_c else None, "views_same": round(sum((va & vb).values()) / n_v, 3),
            "status_counts_same": same_status, "n_callouts": n_c, "n_callouts_after": sum(cb.values()), "n_views": n_v}


def rotate_pages(pages: list[PageData], k: int) -> list[PageData]:
    out = []
    for p in pages:
        q = p
        for _ in range(k):
            q = rotate_cw90(q)
        out.append(canonicalize(q))
    return out


def rotate_pdf(path: Path, deg: int, n_pages: int, tmp: Path) -> list[PageData]:
    """A real rotated PDF (page /Rotate) for the first n pages, read back with the production reader."""
    import pymupdf

    doc = pymupdf.open(str(path))
    doc.select(list(range(min(n_pages, len(doc)))))
    for pg in doc:
        pg.set_rotation((pg.rotation + deg) % 360)
    out = tmp / f"rot{deg}_{path.name}"
    doc.save(str(out))
    return from_pdf(out)


def rename_where_it_names_the_sheet(pages: list[PageData], ds, idx: int, old: str, new: str) -> list[PageData]:
    """Rename a sheet number where the set names that sheet: in its title block and inside the callouts that point to it. A plain
    replacement of the token everywhere would also rewrite the same figure used as a dimension or a label (a numeric sheet "14")."""
    pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(old) + r"(?![A-Za-z0-9])")
    out = copy.deepcopy(pages)
    tb = next(s.title_block for s in ds.sheets if s.index == idx)
    for pg in out:
        if pg.index == idx and tb is not None:
            for ln in pg.lines:
                if in_box(ln, tb):
                    ln.text = pat.sub(new, ln.text)
        for c in ds.callouts:
            if c.sheet != pg.index or c.target_sheet_index != idx or c.status not in RESOLVED:
                continue
            w = c.where
            for ln in pg.lines:
                if ln.x1 >= w[0] and ln.x0 <= w[2] and ln.y1 >= w[1] and ln.y0 <= w[3]:
                    ln.text = pat.sub(new, ln.text)
    return out


def metamorphic(path: Path, pages: list[PageData], ds, name: str, quick: bool) -> dict:
    out: dict = {}
    base = signature(ds)
    for k in (1, 2, 3):
        d2 = build_drawing_set(rotate_pages(pages, k), name)
        out[f"rotate_{90 * k}"] = compare_sig(base, signature(d2))
    # a real rotated PDF through the production reader (first pages only: a prefix of a set is its own set)
    try:
        with tempfile.TemporaryDirectory() as td:
            n = 6 if not quick else 3
            ref_pages = from_pdf(path, list(range(n)))
            ref = signature(build_drawing_set(ref_pages, name))
            rp = rotate_pdf(path, 90, n, Path(td))
            out["rotate_pdf_90_first_pages"] = compare_sig(ref, signature(build_drawing_set(rp, name)))
    except Exception as e:   # not every file can be re-saved as a PDF
        out["rotate_pdf_90_first_pages"] = {"skipped": f"{type(e).__name__}: {e}"}
    # rename: pick the sheet that most callouts point at
    tgt = Counter(c.target_sheet_index for c in ds.callouts if c.status in RESOLVED and c.target_sheet_index is not None)
    if tgt:
        idx = tgt.most_common(1)[0][0]
        old = next(s.number for s in ds.sheets if s.index == idx)
        new = "ZZ-77"
        d3 = build_drawing_set(rename_where_it_names_the_sheet(pages, ds, idx, old, new), name)
        sa, sb = signature(ds, drop_text=True), signature(d3, drop_text=True)
        res = compare_sig(sa, sb)
        res["renamed"] = f"{old} -> {new}"
        res["callouts_to_it"] = tgt[idx]
        res["still_resolved_to_it"] = sum(1 for c in d3.callouts if c.status in RESOLVED and c.target_sheet_index == idx)
        out["rename_sheet"] = res
    # move the biggest view of every sheet that has two views or more, to the far side when there is room
    moved = []
    for p in pages:
        s = next(s for s in ds.sheets if s.index == p.index)
        vs = [v for v in s.views if v.kind in SCALED_KINDS]
        if len(vs) < 2:
            moved.append(p)
            continue
        v = min(vs, key=lambda v: (v.bbox[2] - v.bbox[0]) * (v.bbox[3] - v.bbox[1]))
        dx = 0.08 * p.width
        box = v.bbox
        moved.append(translate_box(p, (box[0], box[1], box[2], box[3]), dx, 0.0))
    d4 = build_drawing_set(moved, name)
    out["move_view_8pct"] = compare_sig(base, signature(d4))
    return out


def index_report(ds) -> dict:
    return {"entries": len(ds.index), "status": dict(Counter(e.status for e in ds.index)), "sheets_not_listed": ds.index_missing,
            "mismatches": [{"number": e.number, "index_title": e.title, "block_title": next((s.title for s in ds.sheets if s.index == e.matched_sheet), None),
                            "similarity": e.similarity} for e in ds.index if e.status == "title differs"]}


def audit(path: Path, quick: bool = False) -> dict:
    t0 = time.time()
    pages = from_pdf(path)
    name = path.stem
    res: dict = {"set": name, "pages": len(pages)}
    ds = build_drawing_set(pages, name, "xycut")
    res["time_s"] = round(time.time() - t0, 1)
    res["views"] = view_report(ds)
    res["callouts"] = callout_report(ds, pages)
    res["null"] = null_rate(ds)
    res["index"] = index_report(ds)
    res["legend"] = {"rows": len(ds.legend), "with_symbol": sum(1 for e in ds.legend if e.symbol_bbox)}
    res["segmentation"] = {}
    for m in METHODS:
        d = ds if m == "xycut" else build_drawing_set(pages, name, m)
        res["segmentation"][m] = {**segmentation_measures(d, pages), "views": len(d.views())}
    res["metamorphic"] = metamorphic(path, pages, ds, name, quick)
    res["sheets"] = [{"page": s.index, "number": s.number, "title": s.title, "views": [
        {"id": v.id, "kind": v.kind, "title": v.title, "labels": v.labels, "scale": v.scale.text if v.scale else None,
         "scale_source": v.scale_source, "level": v.level} for v in s.views]} for s in ds.sheets]
    return res


def show(r: dict) -> None:
    v, c = r["views"], r["callouts"]
    print(f"\n=== {r['set']}: {r['pages']} pages, built in {r['time_s']} s")
    print(f"views: {v['views']} on {v['sheets']} sheets ({v['with_number']} with a sheet number from the title block); kinds {v['kinds']}")
    print(f"  views per sheet {v['views_per_sheet']}; plan/section/elevation/detail/site views {v['scaled_kind_views']}, "
          f"scale sources {v['scale_sources']}; sheets holding several scales {v['sheets_with_several_scales']}; levels {v['levels']}")
    print(f"callouts: all {c['all']}")
    print(f"  in scope {c['in_scope']}, resolved {c['resolved']} ({c['rate']}); unique {c['unique_in_scope']}, resolved {c['unique_resolved']} ({c['unique_rate']}); "
          f"rejected by shape {c['rejected_shape']} {c['rejected_examples']}, inside legends {c['in_legend']}")
    print(f"  callouts with a view label {c['with_view_label']}: sheet found {c['sheet_level_rate']} (sheet level baseline), view found {c['view_level_rate']}")
    print(f"  chance (view labels shuffled): {r['null']}")
    for u in c["unresolved_cases"][:60]:
        print(f"   - p{u['sheet']} [{u['grammar']}] {u['text']!r}: {u['status']}; {u['reason']}; near: {u['context']}")
    print(f"index: {r['index']['entries']} entries {r['index']['status']}, sheets not listed {r['index']['sheets_not_listed'][:8]}")
    for m in r["index"]["mismatches"][:6]:
        print(f"   - {m}")
    print(f"legend rows {r['legend']}")
    print(f"cutting methods {json.dumps(r['segmentation'])}")
    print(f"metamorphic {json.dumps(r['metamorphic'])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--json", default=None)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    out = []
    for p in a.pdfs:
        try:
            r = audit(Path(p), a.quick)
        except Exception as e:
            print(f"\n=== {p}: failed with {type(e).__name__}: {e}")
            out.append({"set": Path(p).stem, "error": f"{type(e).__name__}: {e}"})
            continue
        show(r)
        sys.stdout.flush()
        out.append(r)
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
