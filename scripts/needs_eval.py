"""How well the kind of evidence a requirement needs is read, against a graded list.

    python scripts/needs_eval.py <requirements document> benchmarks/stpete_evidence_needs.json reports/needs/run1 [--model qwen2.5:7b]

Writes one line per item as it goes (a stopped run resumes), then a summary. The grading is a first pass by one person, so the
numbers say how often the reading agrees with it. The errors that matter are counted apart: a real requirement called
"nothing to check" (it could be skipped) and a drawing requirement sent to the filed documents (nobody looks at the sheets).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reviewpulse.app.interpret import _is_title  # noqa: E402
from reviewpulse.interpreter.needs import NOTHING, UNSURE, what_settles  # noqa: E402
from reviewpulse.llm.openai_compat import OpenAICompatClient  # noqa: E402
from reviewpulse.rules.clauses import split_cached  # noqa: E402
from reviewpulse.rules.draft import OllamaClient  # noqa: E402

DRAWING = {"drawn_content", "written_fact", "numeric_limit", "whole_drawing", "site_plan", "across_sheets"}


def summarise(rows: list[dict], gold: dict[str, str]) -> dict:
    n = len(rows)
    right = sum(r["kind"] == gold[r["id"]] for r in rows)
    first = sum(r["votes"][0] == gold[r["id"]] for r in rows)
    unsure = [r for r in rows if r["kind"] == UNSURE]
    sure = [r for r in rows if r["kind"] != UNSURE]
    pairs = Counter((gold[r["id"]], r["kind"]) for r in rows if r["kind"] != gold[r["id"]])
    return {
        "items": n, "agree": right, "agree_share": round(right / n, 3),
        "one_question_agree_share": round(first / n, 3),
        "most_common_kind_share": round(Counter(gold[r["id"]] for r in rows).most_common(1)[0][1] / n, 3),
        "unsure": len(unsure), "agree_when_sure_share": round(sum(r["kind"] == gold[r["id"]] for r in sure) / max(len(sure), 1), 3),
        "drawing_or_not_agree_share": round(sum((r["kind"] in DRAWING) == (gold[r["id"]] in DRAWING) for r in sure) / max(len(sure), 1), 3),
        "requirement_called_nothing": [r["id"] for r in rows if r["kind"] == NOTHING and gold[r["id"]] != NOTHING],
        "drawing_item_sent_to_filed_documents": [r["id"] for r in rows if r["kind"] == "submission_package" and gold[r["id"]] in DRAWING],
        "disagreements": [{"graded": g, "read": k, "n": c} for (g, k), c in pairs.most_common()],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("document", type=Path)
    ap.add_argument("gold", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--votes", type=int, default=3)
    ap.add_argument("--base-url", help="an OpenAI compatible server (vLLM on a cluster node) instead of Ollama")
    args = ap.parse_args()
    gold = json.loads(args.gold.read_text(encoding="utf-8"))["items"]
    _full, clauses = split_cached(args.document, args.out / "cache")
    by_id = {c.id: c for c in clauses if c.id in gold and len(c.text.strip()) > 15 and not _is_title(c)}
    missing = sorted(set(gold) - set(by_id))
    if missing:
        sys.exit(f"the split no longer holds {len(missing)} graded items, e.g. {missing[:5]}")
    args.out.mkdir(parents=True, exist_ok=True)
    log = args.out / "rows.jsonl"
    done = {json.loads(x)["id"]: json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()} if log.exists() else {}
    client = (OpenAICompatClient(args.base_url, None, args.model, provider="vllm", structured="json_schema", max_tokens=200)
              if args.base_url else OllamaClient(model=args.model))
    for k, cid in enumerate(gold, 1):
        if cid in done:
            continue
        c = by_id[cid]
        t = time.time()
        got = what_settles(client, " ".join(c.text.split()), c.scope, args.votes)
        done[cid] = {"id": cid, **got, "seconds": round(time.time() - t, 1)}
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(done[cid]) + "\n")
        print(f"{k}/{len(gold)} {cid}: {got['kind']} ({done[cid]['seconds']} s)", flush=True)
    out = {"model": args.model, "votes": args.votes, **summarise([done[c] for c in gold], gold),
           "seconds": round(sum(r["seconds"] for r in done.values()))}
    (args.out / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
