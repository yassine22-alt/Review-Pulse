"""Could a model that reads more search results reach the evidence the search misses? Only if that evidence is among them.

    python scripts/depth_eval.py <app data folder> <project id> reports/parts_eval/run2 <out folder>

For the parts of the graded set where text that bears on the part is written on the drawings but nothing useful was shown
(docs/progress/M32), this reports the rank of the first such piece among the candidates of the first search stage (words and
meaning fused, before reordering), separately for notes and for other written text, and with the part or the whole line as
the question. The patterns below say which words count as bearing on a part; they were written from a search of the set's
text, by an AI grader, and a piece matching them is a candidate to be judged, not a piece judged useful.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reviewpulse.annotate.passages import set_passages  # noqa: E402
from reviewpulse.app import interpret, service  # noqa: E402
from reviewpulse.app.store import Store  # noqa: E402
from reviewpulse.interpreter.drawing_evidence import bm25_ranking, default_embedder, dense_ranking, fuse  # noqa: E402

BEARS = {
    "item 48.1": r"\b(kitchen|bedroom|bath suite|office|living|garage|laundry|closet)\b",
    "item 49.2": r"ceiling height|headroom|\bSECTION @",
    "item 60.1": r"heat\s*/?\s*(ac )?pump|gas furnace",
    "item 61.1": r"exhaust fan|fan / fan light|fan light",
    "item 64.1": r"water heater|\bwasher\b|\bdryer\b|gas range|gas furnace",
    "item 66.3": r"\b1 ?: ?12\b",
    "item 66.6": r"fireplace|chimney",
    "item 73.2": r"simpson|uplift",
    "item 74.1": r"type .?x.? gypsum|type .?x\b",
}
DEPTHS = (5, 10, 20, 50)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("project")
    ap.add_argument("run", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    store = Store(args.data)
    models = service._models(store, args.project)
    pools = {"notes": [p.text for p in set_passages(models)],
             "written": [u.search for u in interpret.drawing_texts(store, args.project, models)]}
    embedder = default_embedder()
    if embedder is None:
        sys.exit("the embedding model is needed")
    rows = {r["id"]: r for r in json.loads((args.run / "rows.json").read_text(encoding="utf-8"))}
    out = []
    for part_id, pattern in BEARS.items():
        row = rows[part_id.rsplit(".", 1)[0]]
        part = next(p for p in row["parts"] if p["id"] == part_id)
        got = {"part": part_id, "asks": part["text"]}
        for name, docs in pools.items():
            wanted = {i for i, d in enumerate(docs) if re.search(pattern, d, re.I)}
            for question, words in (("part", part["text"]), ("line", row["line"])):
                order = fuse([bm25_ranking(words, docs), dense_ranking(words, docs, embedder)])
                rank = next((k for k, i in enumerate(order, 1) if i in wanted), None)
                got[f"{name}/{question}"] = {"rank_of_first": rank, "pieces_that_bear": len(wanted)}
        got["best_rank"] = min((v["rank_of_first"] for k, v in got.items() if "/" in k and v["rank_of_first"]), default=None)
        out.append(got)
        print(f"{part_id:10s} {part['text'][:42]:44s} " + "  ".join(
            f"{k}={v['rank_of_first']}" for k, v in got.items() if isinstance(v, dict)), flush=True)
    summary = {f"within_{d}": sum(1 for g in out if g["best_rank"] and g["best_rank"] <= d) for d in DEPTHS}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "depth.json").write_text(json.dumps({"parts": out, "summary": summary, "of": len(out)}, indent=1),
                                         encoding="utf-8")
    print("parts with such text within the first N of any of the four searches:", summary, "of", len(out))


if __name__ == "__main__":
    main()
