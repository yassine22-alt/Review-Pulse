"""Does the evidence search put the right sheet in front of the reviewer?

    python scripts/sheet_search_eval.py <app data folder> <project id> <plan.pdf> benchmarks/austin_stpete_sheets.json <out folder>

For each graded requirement and each variant of what is searched, the sheets of the best pieces are compared with the graded
sheets. No reading model is asked. The grading is one person's first pass: a score says how often the search agrees with it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reviewpulse.annotate.evidence_units import Unit, evidence_units, sheets_in_order  # noqa: E402
from reviewpulse.annotate.passages import Passage  # noqa: E402
from reviewpulse.app import interpret, service  # noqa: E402
from reviewpulse.app.store import Store  # noqa: E402
from reviewpulse.drawingset import build_from_pdf  # noqa: E402
from reviewpulse.interpreter.checked import clause_body  # noqa: E402
from reviewpulse.interpreter.drawing_evidence import default_embedder, default_reranker, retrieve  # noqa: E402

TOP_PIECES = 15


def search(clause: str, units: list[Unit], embedder, reranker) -> list[Unit]:
    passages = [Passage(str(i), u.search) for i, u in enumerate(units)]
    return [units[int(p.sheet)] for p in retrieve(clause, passages, embedder, top=TOP_PIECES, reranker=reranker)]


def score(rows: list[dict], gold: dict[str, list[int]], variant: str, keep=lambda cid: True) -> dict:
    mine = [r for r in rows if r["variant"] == variant and gold[r["id"]] and keep(r["id"])]
    hit = lambda r, k: bool(set(r["sheets"][:k]) & set(gold[r["id"]]))  # noqa: E731
    return {"items": len(mine), "first_sheet_right": sum(hit(r, 1) for r in mine),
            "right_sheet_in_top3": sum(hit(r, 3) for r in mine)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("project")
    ap.add_argument("plan", type=Path)
    ap.add_argument("gold", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    gold = json.loads(args.gold.read_text(encoding="utf-8"))["items"]
    needs = json.loads((ROOT / "benchmarks" / "stpete_evidence_needs.json").read_text(encoding="utf-8"))["items"]
    store = Store(args.data)
    models = service._models(store, args.project)
    drawing_set = build_from_pdf(args.plan)
    full = evidence_units(models, drawing_set)
    notes = [u for u in full if u.kind == "note"]
    variants = {
        "today_notes_only": [Unit(u.page, u.kind, u.text, u.text, u.box) for u in notes],
        "notes_with_context": notes,
        "titles_only": [u for u in full if u.kind != "note"],
        "notes_with_context_and_titles": full,
    }
    embedder, reranker = default_embedder(), default_reranker()
    print(f"pieces: {len(notes)} notes, {len(full) - len(notes)} titles | embedder {bool(embedder)} reranker {bool(reranker)}", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, units in variants.items():
        started = time.time()
        for cid, sheets in gold.items():
            if not sheets:
                continue
            body = clause_body(interpret._context(store, args.project, cid))
            ranked = search(body, units, embedder, reranker)
            rows.append({"variant": name, "id": cid, "sheets": sheets_in_order(ranked),
                         "pieces": [{"page": u.page, "kind": u.kind, "text": u.text[:160]} for u in ranked[:5]]})
        print(f"{name}: {time.time() - started:.0f} s {score(rows, gold, name)}", flush=True)
    summary = {name: {"all": score(rows, gold, name),
                      "without_site_plan_items": score(rows, gold, name, lambda c: needs[c] != "site_plan"),
                      "by_kind": {k: score(rows, gold, name, lambda c, k=k: needs[c] == k)
                                  for k in sorted({needs[c] for c in gold if gold[c]})}}
               for name in variants}
    (args.out / "rows.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    pages = len(drawing_set.sheets)
    chance = [1 - __import__("math").comb(pages - len(v), 3) / __import__("math").comb(pages, 3) for v in gold.values() if v]
    print(f"three sheets picked at random would hold a right one for about {sum(chance):.0f} of {len(chance)}")
    for name, s in summary.items():
        print(name, "| all", s["all"], "| without site plan items", s["without_site_plan_items"])


if __name__ == "__main__":
    main()
