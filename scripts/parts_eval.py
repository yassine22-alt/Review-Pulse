"""Does searching part by part, with the text written on the drawings, put more of what an item asks in front of a reviewer?

    python scripts/parts_eval.py run <app data folder> <project id> benchmarks/stpete_evidence_needs.json <out folder>
    python scripts/parts_eval.py score <out folder> <judgements.json>

``run`` uses the app's own code (app.interpret.find_parts) with the local reading model, and today's search (five notes for
the whole line) beside it, then writes a pool per part with the two mixed and shuffled, so that whoever judges a piece does
not know which search showed it. The judgement is one question: opened on the sheet, would this piece let a reviewer see the
thing the part asks about, or does it state it? ``judgements.json`` holds, per part, the fingerprints of the pieces judged
yes and no, so it carries over to later runs; ``score`` stops if a run showed a piece nobody has judged. It counts, for each
search, the parts with at least one useful piece among what it showed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def fingerprint(piece_key: str) -> str:
    return hashlib.sha256(piece_key.encode()).hexdigest()[:12]


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
    judged = json.loads(args.judgements.read_text(encoding="utf-8"))
    pools = {p["part"]: p["pool"] for p in json.loads((args.out / "pools.json").read_text(encoding="utf-8"))}
    unjudged = [(part, x) for part, pool in pools.items() for x in pool
                if fingerprint(x) not in {*judged["yes"].get(part, []), *judged["no"].get(part, [])}]
    if unjudged:
        sys.exit(f"{len(unjudged)} pieces are not judged yet, e.g. {unjudged[:3]}")
    layouts = {
        "today: five notes for the line": lambda row, part: row["today"],
        "parts only: two notes and three drawing texts each": lambda row, part: part["notes"] + part["written"],
        "app: five notes, and each part's notes and drawing texts": lambda row, part: row["today"] + part["notes"] + part["written"],
    }
    totals = {"items": len(rows), "parts": len(pools)}
    got = {}
    for name, shows in layouts.items():
        hits, whole, none, pieces = set(), 0, 0, 0
        for row in rows:
            found, shown = [], set()
            for part in row["parts"]:
                mine = set(shows(row, part))
                shown |= mine
                useful = any(fingerprint(x) in judged["yes"][part["id"]] for x in mine)
                found.append(useful)
                if useful:
                    hits.add(part["id"])
            whole += all(found)
            none += not any(found)
            pieces += len(shown)
        got[name] = hits
        totals[name] = {"parts_with_a_useful_piece": len(hits), "items_all_parts": whole, "items_no_part": none,
                        "pieces_shown": pieces}
    today, app = got["today: five notes for the line"], got["app: five notes, and each part's notes and drawing texts"]
    totals["app_gains"], totals["app_loses"] = sorted(app - today), sorted(today - app)
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
