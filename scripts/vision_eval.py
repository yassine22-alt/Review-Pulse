"""Can a vision model confirm what is drawn, and how often does it see what is not there?

    python scripts/vision_eval.py benchmarks/vision_presence.json <folder of the PDFs> <out folder>
        --base-url http://127.0.0.1:11434/v1 --model qwen2.5vl:7b [--mode whole|tiles]

The area is given (chosen by hand), so the score is the model's own, not a search's. Each question is asked once on the whole
area ("whole") or on four overlapping tiles ("tiles"; yes if any tile says yes). Answers are saved one by one, so a stopped run
goes on where it was. The key is an AI grader's first pass: a score says how often the model agrees with it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reviewpulse.interpreter import vision  # noqa: E402
from reviewpulse.llm.openai_compat import OpenAICompatClient  # noqa: E402

WHOLE = (0.0, 0.0, 1.0, 1.0)


def pointing(places, boxes) -> dict:
    """Whether a named place touches a true object, how much of the area was named, and what naming at random would score."""
    cells = [vision.cell_box(c) for c in vision.CELLS]
    chance = sum(any(vision.overlaps(c, b) for b in boxes) for c in cells) / len(cells)
    named = min(1.0, sum((p[2] - p[0]) * (p[3] - p[1]) for p in places))
    return {"touches": any(vision.overlaps(p, b) for p in places for b in boxes), "share_of_area_named": round(named, 3),
            "chance_one_cell": round(chance, 3)}


def score(rows: list[dict]) -> dict:
    there = [r for r in rows if r["present"]]
    gone = [r for r in rows if not r["present"]]
    count = lambda rs, a: sum(r["answer"] == a for r in rs)  # noqa: E731
    found = [r for r in there if r["answer"] == "yes"]
    # a place counts only when it is also narrow: naming most of the picture touches everything and points at nothing
    pointed = [r for r in found if r["pointing"]["touches"] and r["pointing"]["share_of_area_named"] <= 0.35]
    return {"there": len(there), "yes_when_there": count(there, "yes"), "no_when_there": count(there, "no"),
            "unsure_when_there": count(there, "unsure"), "yes_and_points_at_it": len(pointed),
            "not_there": len(gone), "no_when_not_there": count(gone, "no"), "FALSE_YES": count(gone, "yes"),
            "unsure_when_not_there": count(gone, "unsure"), "errors": count(rows, "error"),
            "chance_a_random_cell_touches": round(sum(r["pointing"]["chance_one_cell"] for r in found) / len(found), 2)
            if found else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key", type=Path)
    ap.add_argument("pdfs", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--mode", choices=("whole", "tiles"), default="whole")
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions (to try the plumbing)")
    ap.add_argument("--check", action="store_true", help="render every picture and ask nothing")
    args = ap.parse_args()
    key = json.loads(args.key.read_text(encoding="utf-8"))
    missing = sorted({a["pdf"] for a in key["areas"] if not (args.pdfs / a["pdf"]).is_file()})
    if missing:
        sys.exit(f"missing drawings in {args.pdfs}: {', '.join(missing)}")
    parts = [WHOLE] if args.mode == "whole" else vision.tiles()
    pictures = {a["id"]: [vision.with_grid(vision.render_area(args.pdfs / a["pdf"], a["page"], vision.tile_page_box(a["box"], t)))
                          for t in parts] for a in key["areas"]}
    questions = [(a, q) for a in key["areas"] for q in a["questions"]]
    args.out.mkdir(parents=True, exist_ok=True)
    if args.check:
        for area, got in pictures.items():
            for n, png in enumerate(got):
                (args.out / f"{area}.{n}.png").write_bytes(png)
        print(f"{len(questions)} questions, {sum(len(v) for v in pictures.values())} pictures written to {args.out}")
        return
    client = OpenAICompatClient(args.base_url, None, args.model, provider="local", structured="json_schema", max_tokens=300,
                                timeout_s=900, max_retries=1)
    saved = args.out / f"rows_{args.mode}.jsonl"
    done = {}
    if saved.exists():
        done = {r["id"]: r for r in map(json.loads, saved.read_text(encoding="utf-8").splitlines()) if r["answer"] != "error"}
    rows, started, failures = [], time.time(), 0
    for n, (area, q) in enumerate(questions[: args.limit or None], 1):
        row = done.get(q["id"])
        if row is None:
            t0 = time.time()
            got = [(t, vision.ask(client, png, q["what"])) for t, png in zip(parts, pictures[area["id"]], strict=True)]
            merged = vision.combine(got)
            row = {"id": q["id"], "area": area["id"], "what": q["what"], "present": q["present"], "cue": q.get("cue"),
                   "answer": merged["answer"], "raw": [g for _, g in got], "seconds": round(time.time() - t0, 1),
                   "pointing": pointing(merged["places"], q.get("boxes", []))}
            with saved.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            failures = failures + 1 if merged["answer"] == "error" else 0
            if failures >= 3:
                sys.exit(f"three questions in a row failed; the last said: {got[-1][1].get('why')}")
        rows.append(row)
        mark = "ok " if row["answer"] == ("yes" if row["present"] else "no") else "XX "
        print(f"{n}/{len(questions)} {mark}{row['id']}: {row['answer']} (there: {row['present']}) {row['seconds']} s", flush=True)
    summary = {"model": args.model, "mode": args.mode, "seconds_this_run": round(time.time() - started),
               "model_seconds": round(sum(r["seconds"] for r in rows)), "all": score(rows),
               "named_on_the_drawing": score([r for r in rows if r["cue"] == "named" or not r["present"]]),
               "drawn_only": score([r for r in rows if r["cue"] == "drawn" or not r["present"]]),
               "by_area": {a["id"]: score([r for r in rows if r["area"] == a["id"]]) for a in key["areas"]}}
    (args.out / f"summary_{args.mode}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("model", "mode", "model_seconds", "all")}, indent=1))
    for cue in ("named", "drawn"):
        hits = [r for r in rows if r["present"] and r["cue"] == cue]
        print(f"{cue}: yes for {sum(r['answer'] == 'yes' for r in hits)} of {len(hits)} that are there")


if __name__ == "__main__":
    main()
