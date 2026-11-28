"""The visual search test against its pass marks (docs/progress/M35): the model, chance, and the app's text search.

    python scripts/visual_score.py <folder with tasks.json> <scores.json> [--out report.json]

A hit: a right tile among the first 3 of the query's pool. Chance and the share of tiles without text are expected values.
"""

from __future__ import annotations

import argparse
import json
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FIRST = 3
MARKS = {"right tile in the first 3": 0.70, "above chance": 0.25, "above the text search": 0.25}


def drawn(n: int, right: int, slots: int = FIRST) -> float:
    """The probability that ``slots`` of ``n`` tiles taken at random hold at least one of the ``right`` ones."""
    slots = min(slots, n)
    return 1.0 - comb(n - right, slots) / comb(n, slots) if slots else 0.0


def model_hit(query: dict, scores: dict) -> float:
    order = sorted(query["pool"], key=lambda i: (-scores[i], i))
    return float(any(i in query["right"] for i in order[:FIRST]))


def text_hit(query: dict, text: dict, search) -> float:
    """``search(words, documents)`` gives the documents' positions, best first, leaving out those it has no reason to list."""
    with_text = [i for i in query["pool"] if text[i]]
    listed = [with_text[n] for n in search(query["what"], [text[i] for i in with_text])] if with_text else []
    first = listed[:FIRST]
    if any(i in query["right"] for i in first):
        return 1.0
    rest = [i for i in query["pool"] if i not in listed]
    return drawn(len(rest), sum(i in query["right"] for i in rest), FIRST - len(first)) if rest else 0.0


def app_search():
    from reviewpulse.annotate.passages import Passage
    from reviewpulse.interpreter.drawing_evidence import default_embedder, default_reranker, retrieve

    embedder, reranker = default_embedder(), default_reranker()
    if embedder is None or reranker is None:
        sys.exit("the embedding model and the reranker are needed: the comparison is with the search the app uses")

    def search(words: str, docs: list[str]) -> list[int]:
        passages = [Passage(sheet=str(n), text=d) for n, d in enumerate(docs)]
        return [int(p.sheet) for p in retrieve(words, passages, embedder, top=len(docs), reranker=reranker)]

    return search


def report(rows: list[dict]) -> dict:
    if not rows:
        return {"queries": 0}
    mean = lambda k: sum(r[k] for r in rows) / len(rows)  # noqa: E731
    return {"queries": len(rows), "model": round(mean("model"), 3), "chance": round(mean("chance"), 3),
            "text_search": round(mean("text"), 3)}


def passes(result: dict) -> dict:
    got = {"right tile in the first 3": result["model"], "above chance": result["model"] - result["chance"],
           "above the text search": result["model"] - result["text_search"]}
    return {k: {"got": round(v, 3), "needed": MARKS[k], "met": v >= MARKS[k] - 1e-9} for k, v in got.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", type=Path)
    ap.add_argument("scores", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    work = json.loads((args.tasks / "tasks.json").read_text(encoding="utf-8"))
    got = json.loads(args.scores.read_text(encoding="utf-8"))
    text = {t["id"]: t["text"] for t in work["tiles"]}
    search = app_search()
    rows = [{"id": q["id"], "key": q["key"], "cue": q["cue"], "pool": len(q["pool"]), "right": len(q["right"]),
             "model": model_hit(q, got["scores"][q["id"]]), "chance": drawn(len(q["pool"]), len(q["right"])),
             "text": text_hit(q, text, search)} for q in work["queries"]]
    out = {"model": got["model"], "groups": {f"{k}, {c}": report([r for r in rows if r["key"] == k and r["cue"] == c])
                                             for k in ("held_out", "older") for c in ("drawn", "named")}, "queries": rows}
    out["pass_marks"] = passes(out["groups"]["held_out, drawn"])
    out["passed"] = all(m["met"] for m in out["pass_marks"].values())
    if args.out:
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("model", "groups", "pass_marks", "passed")}, indent=1))


if __name__ == "__main__":
    main()
