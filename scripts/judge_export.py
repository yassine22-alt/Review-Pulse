"""The candidates a larger model will read (docs/progress/M36), made where the search runs.

    python scripts/judge_export.py <app data folder> <project id> reports/parts_eval/run2 <out candidates.jsonl>

One line per part: the part, its whole line, up to 80 candidates (the first 20 of the first search stage, four ways), and the
list of every drawing text, so that names proposed by a model can be matched exactly. The file holds words from the drawings:
it goes to a machine we run ourselves, never to a hosted service, and is not committed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reviewpulse.annotate.passages import set_passages  # noqa: E402
from reviewpulse.app import interpret, service  # noqa: E402
from reviewpulse.app.store import Store  # noqa: E402
from reviewpulse.interpreter.drawing_evidence import bm25_ranking, default_embedder, dense_ranking, fuse  # noqa: E402

DEPTH = 20


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("project")
    ap.add_argument("run", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    store = Store(args.data)
    models = service._models(store, args.project)
    notes = [{"sheet": p.sheet, "text": p.text, "search": p.text, "kind": "note"} for p in set_passages(models)]
    written = [{"sheet": u.sheet, "text": u.text, "search": u.search, "kind": u.kind}
               for u in interpret.drawing_texts(store, args.project, models)]
    embedder = default_embedder()
    if embedder is None:
        sys.exit("the embedding model is needed")
    rows = json.loads((args.run / "rows.json").read_text(encoding="utf-8"))
    lines = []
    for row in rows:
        for part in row["parts"]:
            found: dict[str, dict] = {}
            searches = []
            for pool in (notes, written):
                docs = [p["search"] for p in pool]
                for words in (part["text"], row["line"]):
                    order = fuse([bm25_ranking(words, docs), dense_ranking(words, docs, embedder)])[:DEPTH]
                    searches.append([pool[i] for i in order])
            for depth in range(DEPTH):                       # in turn, so that "search order" means something across the four
                for got in searches:
                    if depth < len(got):
                        p = got[depth]
                        found.setdefault(f"{p['sheet']}|{p['text']}", {**p, "key": f"{p['sheet']}|{p['text']}"})
            lines.append({"part": part["id"], "asks": part["text"], "line": row["line"], "candidates": list(found.values())})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")
    every = [{"key": f"{p['sheet']}|{p['text']}", "text": p["text"]} for p in [*written, *notes]]
    args.out.with_suffix(".pieces.json").write_text(json.dumps(every, ensure_ascii=False), encoding="utf-8")
    n = sum(len(x["candidates"]) for x in lines)
    print(f"{len(lines)} parts, {n} candidates ({n / len(lines):.0f} a part), {len(every)} drawing texts -> {args.out}")


if __name__ == "__main__":
    main()
