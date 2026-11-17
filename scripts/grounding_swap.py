"""Can a scorer tell a rule that says what the clause says from one with the compared fact swapped for another?

    python scripts/grounding_swap.py --scorer nli [--model MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7]
    python scripts/grounding_swap.py --scorer cos --model BAAI/bge-m3

This is the failure that matters in practice: a rule that is valid, uses the sentence's number and direction, and measures the
wrong thing ("sockets less than 1.30 m above the floor" became "travel distance to the outside is less than 1.3 m").
No annotation is needed. Positives: the gold rule of each synthetic clause (English and French) read back in plain words.
Negatives: the same rule with its compared fact replaced by another numeric fact of the same unit from the same catalogue.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path

import numpy as np

from reviewpulse.xeval.readback import describe_rule


def first_fact(node):
    if isinstance(node, dict):
        if node.get("node") == "fact":
            return node
        for v in node.values():
            r = first_fact(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = first_fact(v)
            if r:
                return r
    return None


def read(prog, cat):
    d = describe_rule(prog["requirement"], prog.get("applicability"), prog.get("exemption"), cat.get("bindings", {}),
                      cat.get("whole") or "building")
    return d.get("plain") or ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorer", choices=["nli", "cos"], default="nli")
    ap.add_argument("--model", default="MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")
    ap.add_argument("--prefix", default="")
    args = ap.parse_args()
    items = [json.loads(line) for line in Path("reports/extractor_eval/corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    rng = random.Random(3)
    pairs = []          # (lang, text, readback, label)
    for it in items:
        prog, cat = it["program"], it["catalogue"]
        f = first_fact(prog["requirement"])
        if not f:
            continue
        b = cat["bindings"].get(f["name"], {})
        same = [n for n, x in cat["bindings"].items()
                if n != f["name"] and x.get("kind") == b.get("kind") and x.get("unit") == b.get("unit")]
        if not same:
            continue
        good = read(prog, cat)
        bad_prog = copy.deepcopy(prog)
        first_fact(bad_prog["requirement"])["name"] = rng.choice(same)
        bad = read(bad_prog, cat)
        if good and bad and good != bad:
            pairs += [(it["lang"], it["text"], good, 1), (it["lang"], it["text"], bad, 0)]
    print(f"{len(pairs) // 2} clauses, each with its true rule and a swapped one")
    if args.scorer == "cos":
        from sentence_transformers import SentenceTransformer

        m = SentenceTransformer(args.model)
        a = m.encode([args.prefix + p[1] for p in pairs], normalize_embeddings=True, batch_size=32)
        b = m.encode([args.prefix + p[2] for p in pairs], normalize_embeddings=True, batch_size=32)
        scores = (a * b).sum(1)
    else:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(args.model)
        net = AutoModelForSequenceClassification.from_pretrained(args.model).eval()
        ent = [i for i, lab in net.config.id2label.items() if lab.lower().startswith("entail")][0]
        out = []
        with torch.no_grad():
            for k in range(0, len(pairs), 16):
                chunk = pairs[k:k + 16]
                enc = tok([p[1] for p in chunk], [p[2] for p in chunk], return_tensors="pt", padding=True, truncation=True)
                out += torch.softmax(net(**enc).logits, -1)[:, ent].tolist()
        scores = np.array(out)
    y = np.array([p[3] for p in pairs])
    langs = np.array([p[0] for p in pairs])

    def auc(mask):
        p, n = scores[mask & (y == 1)], scores[mask & (y == 0)]
        return float((p[:, None] > n[None, :]).mean() + 0.5 * (p[:, None] == n[None, :]).mean())

    # a pairwise decision is also what the product needs: accept a rule only when its score clears a threshold
    thr = float(np.quantile(scores[y == 1], 0.10))
    print(f"{args.scorer} {args.model}: AUC {auc(np.ones(len(y), bool)):.3f}; "
          + "; ".join(f"{lg} {auc(langs == lg):.3f}" for lg in sorted(set(langs))))
    print(f"threshold {thr:.2f} keeps 90% of true rules and rejects {float((scores[y == 0] < thr).mean()):.1%} of swapped ones")


if __name__ == "__main__":
    main()
