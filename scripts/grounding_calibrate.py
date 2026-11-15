"""Does a sentence say what the facts of its rule are about? Measure multilingual embeddings on the synthetic corpus.

    python scripts/grounding_calibrate.py [--model paraphrase-multilingual-MiniLM-L12-v2]

For each corpus clause (English and French, several domains) the facts its gold rule uses are the positives; every other
fact in the catalogue is a negative. A good grounding score separates the two without being told the language or the domain.
Reported: AUC, and at the threshold that keeps 98 % of the true facts, the share of unrelated facts rejected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def facts_of(node, out: set) -> set:
    if isinstance(node, dict):
        if node.get("node") == "fact" and node.get("entity") != "building" or node.get("node") == "fact":
            out.add(node["name"])
        for v in node.values():
            facts_of(v, out)
    elif isinstance(node, list):
        for v in node:
            facts_of(v, out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--prefix", default="")
    args = ap.parse_args()
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model)
    items = [json.loads(line) for line in Path("reports/extractor_eval/corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    pos, neg, by_lang = [], [], {}
    for it in items:
        gold = set()
        for key in ("requirement", "applicability", "exemption"):
            facts_of(it["program"].get(key), gold)
        desc = {n: b["description"] for n, b in it["catalogue"]["bindings"].items()}
        names = [n for n in desc if n in it["catalogue"]["bindings"]]
        enc = model.encode([args.prefix + it["text"]] + [args.prefix + desc[n] for n in names], normalize_embeddings=True)
        sims = enc[1:] @ enc[0]
        for n, s in zip(names, sims, strict=True):
            (pos if n in gold else neg).append(float(s))
            by_lang.setdefault(it["lang"], ([], []))[0 if n in gold else 1].append(float(s))
    pos, neg = np.array(pos), np.array(neg)
    auc = float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())
    thr = float(np.quantile(pos, 0.02))
    print(f"{args.model}: {len(pos)} true facts, {len(neg)} unrelated facts")
    print(f"AUC {auc:.3f}; true facts median {np.median(pos):.2f}, unrelated median {np.median(neg):.2f}")
    print(f"threshold {thr:.2f} keeps 98% of true facts and rejects {float((neg < thr).mean()):.1%} of unrelated ones")
    for lang, (p, n) in sorted(by_lang.items()):
        p, n = np.array(p), np.array(n)
        a = float((p[:, None] > n[None, :]).mean())
        print(f"  {lang}: AUC {a:.3f}  true median {np.median(p):.2f}  unrelated median {np.median(n):.2f}")


if __name__ == "__main__":
    main()
