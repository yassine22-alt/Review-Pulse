"""Does searching part by part, with the text written on the drawings, put more of what an item asks in front of a reviewer?

    python scripts/parts_eval.py run <app data folder> <project id> benchmarks/stpete_evidence_needs.json <out folder>
    python scripts/parts_eval.py score <out folder> <judgements.json>

``run`` uses the app's own code (app.interpret.find_parts) with the local reading model, and today's search (five notes for
the whole line) beside it, then writes a pool per part with the two mixed and shuffled, so that whoever judges a piece does
not know which search showed it. The judgement is one question: opened on the sheet, would this piece let a reviewer see the
thing the part asks about, or does it state it? ``judgements.json`` maps a part ("48.1") to the pool numbers that would.
``score`` then counts, for each search, the parts with at least one such piece among what it showed.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def key(piece: dict) -> str:
    return f"{piece['sheet']}|{piece['text']}"


def run(args) -> None:
    from reviewpulse.app import interpret
    from reviewpulse.app.store import Store
    from reviewpulse.rules.draft import OllamaClient

    needs = json.loads(args.needs.read_text(encoding="utf-8"))["items"]
    items = [i for i, kind in needs.items() if kind == args.kind]
    store = Store(args.data)
    client = OllamaClient(model=args.model)
    args.out.mkdir(parents=True, exist_ok=True)
    rows, pools = [], []
    for n, cid in enumerate(items, 1):
        started = time.time()
        got = interpret.find_parts(store, args.project, cid, lambda: client)
        seconds = round(time.time() - started, 1)
        today = interpret.find_notes(store, args.project, cid)["candidates"]
        from reviewpulse.interpreter.checked import clause_body

        row = {"id": cid, "line": clause_body(interpret._context(store, args.project, cid)), "seconds": seconds,
               "split_by_model": got["split_by_model"], "left_out": got["left_out"], "today": [key(p) for p in today],
               "parts": [{"id": f"{cid}.{k}", "text": p["text"], "notes": [key(x) for x in p["notes"]],
                          "written": [key(x) for x in p["written"]]} for k, p in enumerate(got["parts"], 1)]}
        rows.append(row)
        by_key = {key(x): x for x in [*today, *(x for p in got["parts"] for x in [*p["notes"], *p["written"]])]}
        for part, mine in zip(row["parts"], got["parts"], strict=True):
            pool = sorted({*row["today"], *part["notes"], *part["written"]})
            random.Random(part["id"]).shuffle(pool)
            pools.append({"part": part["id"], "line": row["line"], "asks": mine["text"], "pool": pool,
                          "shown": [f"{k}: [{by_key[p]['sheet']}] {by_key[p]['text'][:170]}" for k, p in enumerate(pool)]})
        print(f"{n}/{len(items)} {cid}: {len(got['parts'])} parts, {seconds} s", flush=True)
    (args.out / "rows.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.out / "pools.json").write_text(json.dumps(pools, indent=1, ensure_ascii=False), encoding="utf-8")


def score(args) -> None:
    rows = json.loads((args.out / "rows.json").read_text(encoding="utf-8"))
    pools = {p["part"]: p["pool"] for p in json.loads((args.out / "pools.json").read_text(encoding="utf-8"))}
    judged = json.loads(args.judgements.read_text(encoding="utf-8"))["relevant"]
    missing = sorted(set(pools) - set(judged))
    if missing:
        sys.exit(f"{len(missing)} parts are not judged yet, e.g. {missing[:5]}")
    totals = {"items": len(rows), "parts": len(pools), "parts_today": 0, "parts_new": 0, "parts_notes_by_part": 0,
              "parts_only_written": 0, "parts_lost": [], "parts_gained": [], "parts_nothing_either": [],
              "items_all_parts_today": 0, "items_all_parts_new": 0, "items_no_part_today": 0, "items_no_part_new": 0,
              "pieces_shown_today": 0, "pieces_shown_new": 0}
    for row in rows:
        old_hits, new_hits = [], []
        shown_new = set()
        for part in row["parts"]:
            good = {pools[part["id"]][k] for k in judged[part["id"]]}
            old = bool(good & set(row["today"]))
            by_note, by_written = bool(good & set(part["notes"])), bool(good & set(part["written"]))
            new = by_note or by_written
            shown_new |= {*part["notes"], *part["written"]}
            old_hits.append(old)
            new_hits.append(new)
            totals["parts_notes_by_part"] += by_note
            totals["parts_only_written"] += by_written and not by_note
            if new and not old:
                totals["parts_gained"].append(part["id"])
            if old and not new:
                totals["parts_lost"].append(part["id"])
            if not old and not new:
                totals["parts_nothing_either"].append(part["id"])
        totals["parts_today"] += sum(old_hits)
        totals["parts_new"] += sum(new_hits)
        for name, hits in (("today", old_hits), ("new", new_hits)):
            totals[f"items_all_parts_{name}"] += all(hits)
            totals[f"items_no_part_{name}"] += not any(hits)
        totals["pieces_shown_today"] += len(row["today"])
        totals["pieces_shown_new"] += len(shown_new)
    totals["split_by_model"] = sum(r["split_by_model"] for r in rows)
    totals["seconds_first_opening"] = round(sum(r["seconds"] for r in rows))
    (args.out / "score.json").write_text(json.dumps(totals, indent=1), encoding="utf-8")
    print(json.dumps(totals, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(required=True)
    r = sub.add_parser("run")
    r.add_argument("data", type=Path)
    r.add_argument("project")
    r.add_argument("needs", type=Path)
    r.add_argument("out", type=Path)
    r.add_argument("--kind", default="drawn_content")
    r.add_argument("--model", default="qwen2.5:7b")
    r.set_defaults(act=run)
    s = sub.add_parser("score")
    s.add_argument("out", type=Path)
    s.add_argument("judgements", type=Path)
    s.set_defaults(act=score)
    args = ap.parse_args()
    args.act(args)


if __name__ == "__main__":
    main()
