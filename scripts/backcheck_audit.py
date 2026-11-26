"""Measure the back check.

  synth   pairs of generated plans with planted comments and known edits (truth by construction): per class recall and
          precision, the false RESOLVED count, the share of new issue counts and cloud counts that are exact, metamorphic cases.
  real    real sets: chief_architect_austin.pdf against itself, with its pages reordered, with pages removed; the four designs
          inside rebuildflorida_floorplans.pdf (are they identical?) against themselves and against each other.
  markups the connector path: planted comments written to an annotated PDF by connectors.pdf_io, read back, back checked.

Run: python scripts/backcheck_audit.py synth|real|markups [--out reports/backcheck]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reviewpulse.backcheck import back_check, write_report  # noqa: E402
from reviewpulse.backcheck.align import _wjaccard  # noqa: E402
from reviewpulse.backcheck.model import (  # noqa: E402
    CANNOT_TELL,
    MOVED,
    NOT_ADDRESSED,
    RESOLVED,
    STATUSES,
    Comment,
)
from reviewpulse.backcheck.snapshot import Snapshot, snapshot_pdf  # noqa: E402
from reviewpulse.backcheck.synthpairs import c_label_dummy, make_cases  # noqa: E402

METAMORPHIC = ("identical", "shifted", "turned_content", "rotate_flag")


def _decoys(cases) -> None:
    """A second comment on a place no edit touches: it must stay NOT ADDRESSED (MOVED when the sheet is renumbered)."""
    for c in cases:
        if c.name.startswith(("sheet_removed", "view_moved", "identical", "shifted", "turned", "wrong_place", "door_unfixed")):
            continue
        if "C3" in c.expect:
            continue
        try:
            d = c_label_dummy(c.old)
        except Exception:
            continue
        c.comments = [*c.comments, d]
        c.expect["C3"] = MOVED if c.name.startswith("sheet_renumbered") else NOT_ADDRESSED


def synth(args) -> dict:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work)
    cases = make_cases(work, seeds=tuple(args.seeds))
    _decoys(cases)
    rows, issue_ok, cloud_ok, n_cases = [], 0, 0, 0
    meta = {"cases": 0, "comments": 0, "wrong_status": 0, "regions": 0}
    t0 = time.time()
    shown = set()
    for c in cases:
        res = back_check(c.old, c.new, c.comments)
        n_cases += 1
        issue_ok += len(res.new_issues) == c.new_issues
        if c.not_clouded is not None:
            cloud_ok += len(res.not_clouded) == c.not_clouded
        is_meta = c.name.startswith(METAMORPHIC)
        if is_meta:
            meta["cases"] += 1
            meta["regions"] += len(res.regions)
        for v in res.verdicts:
            exp = c.expect[v.comment.id]
            rows.append({"case": c.name, "comment": v.comment.id, "expected": exp, "got": v.status, "reason": v.reason,
                         "nothing_relevant_changed": exp in (NOT_ADDRESSED, MOVED)})
            if is_meta:
                meta["comments"] += 1
                meta["wrong_status"] += v.status != exp
        kind = c.name.rsplit("_s", 1)[0]
        if kind not in shown and not c.name.startswith(("identical",)):
            shown.add(kind)
            write_report(res, out / "html" / c.name, f"Back check: {c.name}")
    stats = _class_stats(rows)
    false_resolve = [r for r in rows if r["got"] == RESOLVED and r["expected"] != RESOLVED]
    nothing = [r for r in rows if r["nothing_relevant_changed"]]
    summary = {"cases": n_cases, "comments": len(rows), "seeds": args.seeds, "seconds": round(time.time() - t0, 1),
               "per_class": stats, "false_resolved": len(false_resolve), "false_resolved_rows": false_resolve,
               "comments_where_nothing_relevant_changed": len(nothing),
               "resolved_among_those": sum(r["got"] == RESOLVED for r in nothing),
               "exact_new_issue_counts": f"{issue_ok}/{n_cases}", "exact_not_clouded_counts": f"{cloud_ok}/{sum(c.not_clouded is not None for c in cases)}",
               "metamorphic": meta, "wrong": [r for r in rows if r["got"] != r["expected"]]}
    (out / "synth_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    _print(summary)
    return summary


def _class_stats(rows) -> dict:
    out = {}
    for s in STATUSES:
        tp = sum(r["got"] == s and r["expected"] == s for r in rows)
        fp = sum(r["got"] == s and r["expected"] != s for r in rows)
        fn = sum(r["got"] != s and r["expected"] == s for r in rows)
        out[s] = {"n_expected": tp + fn, "tp": tp, "fp": fp, "fn": fn,
                  "recall": round(tp / (tp + fn), 3) if tp + fn else None, "precision": round(tp / (tp + fp), 3) if tp + fp else None}
    return out


def _print(summary) -> None:
    print(f"cases {summary['cases']}  comments {summary['comments']}  {summary['seconds']} s")
    for s, d in summary["per_class"].items():
        print(f"  {s:26s} n={d['n_expected']:3d} recall={d['recall']} precision={d['precision']}  (tp {d['tp']} fp {d['fp']} fn {d['fn']})")
    print("FALSE RESOLVED:", summary["false_resolved"], "| resolved among comments where nothing relevant changed:",
          summary["resolved_among_those"], "of", summary["comments_where_nothing_relevant_changed"])
    print("new issue counts exact:", summary["exact_new_issue_counts"], "| not clouded counts exact:", summary["exact_not_clouded_counts"])
    print("metamorphic:", summary["metamorphic"])
    for w in summary["wrong"]:
        print("  WRONG", w["case"], w["comment"], "expected", w["expected"], "got", w["got"], "|", w["reason"])


# ---- real sets --------------------------------------------------------------------------------------------------------------

def subset(snap: Snapshot, positions: list[int]) -> Snapshot:
    """A version of a set built from the pages of a read set (reordered, some removed): the same data a PDF with those pages
    would give, without writing a second copy of a large file."""
    return Snapshot(snap.path, [snap.pages[i] for i in positions], snap.name)


def line_comment(snap: Snapshot, pos: int, cid: str) -> Comment:
    """A comment on the longest text line of the middle of a real sheet page (a plausible place), with a text no tool can test."""
    p = snap.pages[pos]
    lines = [w for w in p.lines if 8 < len(w.text) < 60 and p.width * 0.1 < w.bbox[0] < p.width * 0.9]
    ln = max(lines, key=lambda w: len(w.text)) if lines else None
    box = ln.bbox if ln else (p.width * 0.4, p.height * 0.4, p.width * 0.5, p.height * 0.45)
    return Comment(cid, "Verify the dimension at this location. (local amendment 9)", "", p.number, pos + 1,
                   tuple(round(x, 1) for x in box))


def _run_real(name, old: Snapshot, new: Snapshot, comments, expect, out: Path | None = None) -> dict:
    t = time.time()
    res = back_check(old.path, new.path, comments, old_snap=old, new_snap=new)
    got = {v.comment.id: v.status for v in res.verdicts}
    bad = {k: (got[k], expect[k]) for k in expect if got[k] != expect[k]}
    row = {"case": name, "sheets_paired": len(res.sheets), "removed": len(res.sheets_removed), "added": len(res.sheets_added),
           "changed_places": len(res.regions), "new_issues": len(res.new_issues), "moved_views": len(res.moved),
           "counts": res.counts(), "false_resolved": sum(s == RESOLVED for s in got.values()), "unexpected": bad,
           "seconds": round(time.time() - t, 1)}
    if out is not None:
        write_report(res, out / name, f"Back check: {name}")
    return row


def real(args) -> dict:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    t = time.time()
    austin = snapshot_pdf(ROOT / "data/real_plans/chief_architect_austin.pdf")
    print("austin read", round(time.time() - t), "s", len(austin.pages), "pages")
    pick = [1, 2, 4, 7, 9, 12, 16, 19]
    comments = [line_comment(austin, i, f"A{k + 1}") for k, i in enumerate(pick)]
    n = len(austin.pages)
    exp_same = {c.id: NOT_ADDRESSED for c in comments}
    rows.append(_run_real("austin_identical", austin, austin, comments, exp_same))
    rows.append(_run_real("austin_reordered", austin, subset(austin, list(range(n))[::-1]), comments, exp_same, out / "html"))
    drop = {4, 12}
    keep = [i for i in range(n) if i not in drop]
    exp_drop = {c.id: (CANNOT_TELL if i in drop else NOT_ADDRESSED) for c, i in zip(comments, pick, strict=True)}
    rows.append(_run_real("austin_pages_removed", austin, subset(austin, keep), comments, exp_drop, out / "html"))
    rows.append(_run_real("austin_removed_and_reordered", austin, subset(austin, keep[::-1]), comments, exp_drop))

    t = time.time()
    fl = snapshot_pdf(ROOT / "data/real_plans/rebuildflorida_floorplans.pdf")
    print("florida read", round(time.time() - t), "s", len(fl.pages), "pages")
    ranges = [(0, 14), (14, 28), (28, 42), (42, 57)]
    designs = [subset(fl, list(range(a, b))) for a, b in ranges]
    bags = [p.token_bag() for p in fl.pages]
    sims = [_wjaccard(bags[i], bags[j]) for i in range(len(bags)) for j in range(i + 1, len(bags))]
    ident = sum(s > 0.999 for s in sims)
    best = []
    for d in range(1, 4):
        for k, p in enumerate(designs[0].pages):
            q = designs[d].pages
            best.append(max((_wjaccard(bags[p.index], bags[x.index]) for x in q), default=0.0))
    florida = {"page_pairs_identical": ident, "pages": len(fl.pages), "median_best_match_similarity_design1_vs_others": round(statistics.median(best), 3),
               "share_best_match_above_0.95": round(sum(b > 0.95 for b in best) / len(best), 3)}
    for d, dsn in enumerate(designs):
        cm = [line_comment(dsn, i, f"F{k + 1}") for k, i in enumerate([1, 2, 4, 7])]
        ex = {c.id: NOT_ADDRESSED for c in cm}
        rows.append(_run_real(f"florida_design{d + 1}_identical", dsn, dsn, cm, ex))
        rows.append(_run_real(f"florida_design{d + 1}_reordered", dsn, subset(dsn, list(range(len(dsn.pages)))[::-1]), cm, ex))
    cm = [line_comment(designs[0], i, f"F{k + 1}") for k, i in enumerate([1, 2, 4, 7])]
    for d in (1, 2, 3):
        rows.append(_run_real(f"florida_design1_vs_design{d + 1}", designs[0], designs[d], cm, {}))
    summary = {"florida_copies": florida, "rows": rows}
    (out / "real_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps(florida))
    for r in rows:
        print(r)
    return summary


def markups(args) -> dict:
    """Planted comments written as markups by the connectors, read back from the annotated PDF, then back checked."""
    import pymupdf

    from reviewpulse.backcheck.comments import load_markups
    from reviewpulse.connectors.model import ReviewComment
    from reviewpulse.connectors.pdf_io import write_annotations

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = [c for c in make_cases(Path(args.work), seeds=(12,)) if c.name.startswith(("door_widened_s", "room_labelled", "wrong_place"))]
    rows = []
    for c in cases:
        rcs = [ReviewComment(id=k.id, number=i + 1, citation=k.code, text=k.text, sheet=k.sheet or "", page=k.page,
                             bbox=list(k.bbox) if k.bbox else None, located=bool(k.bbox)) for i, k in enumerate(c.comments)]
        ann = Path(args.work) / f"{c.name}_annotated.pdf"
        write_annotations(c.old, ann, rcs, author="plan reviewer")
        got = load_markups(ann)
        with pymupdf.open(str(ann)) as d:
            n_annots = sum(len(list(p.annots())) for p in d)
        res = back_check(c.old, c.new, got)
        for v in res.verdicts:
            rows.append({"case": c.name, "comment_read": v.comment.id, "text_kept": any(v.comment.text.strip() == k.text.strip() for k in c.comments),
                         "status": v.status, "expected": c.expect.get(v.comment.id), "annotations_in_pdf": n_annots})
    print(json.dumps(rows, indent=1))
    (out / "markups_summary.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return {"rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["synth", "real", "markups"])
    ap.add_argument("--out", default=str(ROOT / "reports" / "backcheck"))
    ap.add_argument("--work", default=str(Path(__import__("tempfile").gettempdir()) / "backcheck_work"))
    ap.add_argument("--seeds", type=int, nargs="+", default=[12, 13, 14, 15, 16, 17])
    args = ap.parse_args()
    {"synth": synth, "real": real, "markups": markups}[args.mode](args)


if __name__ == "__main__":
    main()
