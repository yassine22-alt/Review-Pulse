"""Which retrieval method finds the note about a requirement? Compared on a real drawing set, with no labels.

    python scripts/retrieval_eval.py --plans data/real_plans/your_set.pdf [--lines 46] [--out reports/retrieval]

For every checklist line (the `needs_fact` lines of benchmarks/checklist_labels.json), the local model writes the note an architect
would put on a drawing to show that the design provides what the line requires, once in English, once in French and once in German.
That note is planted, alone, among the real passages of the drawing set, and every method must rank it from the requirement alone.
Nothing is labelled by hand: the planted note is the answer. Reported per method and per language: how often the planted note is
first (recall@1), in the first five (recall@5, the number shown to the choosing model) and its mean reciprocal rank.

A second, small check uses real notes only: for lines where the set holds a note that I read and judged to be about the line
(listed in REAL below, by what the note starts with), is that note in the first five? It is a handful of lines labelled by one
person, so it is a sanity check on the planted result and not a measure of its own.

Methods: words (BM25); meaning (bge-m3); both fused by reciprocal rank (the method of M15); the fusion, then reranked by a
cross-encoder that reads the requirement and each candidate together (bge-reranker-v2-m3); the same with a hypothetical note
written by the model first (HyDE: the query is replaced by a note that would answer it).

The planted notes are written by the same kind of model that reads the clause, so they are closer to the requirement than a real
note is: absolute numbers are optimistic and only the comparison between methods is meaningful. Documents, drawings and reports
are never committed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evidence_eval import LABELS, pdf_passages  # noqa: E402
from real_doc_study import Real  # noqa: E402

from reviewpulse.annotate.passages import Passage  # noqa: E402
from reviewpulse.interpreter import drawing_evidence as ev  # noqa: E402
from reviewpulse.interpreter.checked import clause_body  # noqa: E402
from reviewpulse.interpreter.context import assemble_context  # noqa: E402
from reviewpulse.rules.clauses import split_document  # noqa: E402

LANGS = {"en": "English", "fr": "French", "de": "German"}
WRITE = ("A building requirement is given. Write the note an architect would put on a construction drawing to show that the design "
         "provides what the requirement asks for: one or two short sentences, written in capital letters, in {language}. "
         "Do not copy the requirement's wording; write it as a drawing note. Reply with JSON only: {{\"note\": \"...\"}}.")
HYDE = ("A building requirement is given. Write one or two sentences, in English, as they would appear in a note on a construction "
        "drawing that answers the requirement. Reply with JSON only: {\"note\": \"...\"}.")
SCHEMA = {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}

# lines where the permit set holds a note I judged, by reading, to be about the line: (document part, line id, start of the note)
REAL = [("allentown", "item 4", "4. DOORS BETWEEN GARAGE"), ("allentown", "item 16", "1. STAIRWAYS SHALL HAVE A MIN. WIDTH"),
        ("allentown", "item 21", "8. GUARDRAILS SHALL BE PROVIDED"), ("allentown", "item 24", "CONNECT SMOKE DETECTORS"),
        ("bloomfield", "item 64", "4. DOORS BETWEEN GARAGE"), ("bloomfield", "item 66", "8. ALL GLAZING WITHIN")]


def write_note(llm, text: str, prompt: str) -> str | None:
    try:
        out = llm.complete(prompt, json.dumps({"requirement": text[:600]}, ensure_ascii=False), SCHEMA)
    except Exception:  # noqa: BLE001
        return None
    note = (out.get("note") or "").strip() if isinstance(out, dict) else ""
    return note if len(note) >= 12 else None


def rankings(clause: str, passages: list[Passage], embedder, reranker, hyde: str | None) -> dict[str, list[int]]:
    docs = [p.text for p in passages]
    words = ev.bm25_ranking(clause, docs)
    dense = ev.dense_ranking(clause, docs, embedder) if embedder else []
    fused = ev.fuse([words, dense[:20]])
    out = {"words": words, "meaning": dense, "fused": fused}
    if reranker is not None:
        pool = fused[:20]
        out["fused+rerank"] = ev.rerank(clause, docs, pool, reranker) + [i for i in fused if i not in pool]
        if hyde:
            hw, hd = ev.bm25_ranking(hyde, docs), ev.dense_ranking(hyde, docs, embedder)
            both = ev.fuse([words, dense[:20], hw, hd[:20]])
            pool2 = both[:20]
            out["hyde+fused+rerank"] = ev.rerank(clause, docs, pool2, reranker) + [i for i in both if i not in pool2]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", nargs="+", required=True)
    ap.add_argument("--docs", default="data/real_docs")
    ap.add_argument("--lines", type=int, default=46)
    ap.add_argument("--out", default="reports/retrieval")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pool = [p for plan in args.plans for p in pdf_passages(Path(plan))]
    llm, embedder, reranker = Real(), ev.default_embedder(), ev.default_reranker()
    print(f"{len(pool)} passages; embedder {getattr(embedder, 'model', None)}; reranker {'bge-reranker-v2-m3' if reranker else None}", flush=True)
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    lines = []
    for docname, spec in labels.items():
        doc = Path(args.docs) / docname
        if not doc.exists():
            continue
        full, clauses = split_document(doc)
        default = spec.get("_default")
        if default:
            spec = {**{c.id: dict(default) for c in clauses if c.kind != "heading"}, **{k: v for k, v in spec.items() if k != "_default"}}
        ids = {c.id for c in clauses}
        for cid, lab in spec.items():
            if lab["label"] == "needs_fact" and cid in ids:
                lines.append((docname, cid, clause_body(assemble_context(doc.name, full, clauses, cid))))
    lines = lines[:args.lines]
    ranks: dict[tuple[str, str], list[int]] = {}
    rows = []
    for k, (docname, cid, text) in enumerate(lines):
        t0 = time.time()
        hyde = write_note(llm, text, HYDE)
        for code, language in LANGS.items():
            note = write_note(llm, text, WRITE.format(language=language))
            if note is None:
                continue
            passages = [*pool, Passage("planted", note)]
            target = len(passages) - 1
            got = rankings(text, passages, embedder, reranker, hyde)
            row = {"doc": docname, "id": cid, "lang": code, "requirement": text[:200], "planted": note[:200], "ranks": {}}
            for method, order in got.items():
                rank = order.index(target) + 1 if target in order else None
                row["ranks"][method] = rank
                ranks.setdefault((method, code), []).append(rank or 10**6)
            rows.append(row)
        print(f"  line {k + 1}/{len(lines)} {docname[3:14]} {cid} ({time.time() - t0:.0f} s)", flush=True)
    real: dict[str, list[bool]] = {}
    for part, cid, start in REAL:
        hit = next(((d, c, t) for d, c, t in lines if part in d and c == cid), None)
        if hit is None:
            continue
        got = rankings(hit[2], pool, embedder, reranker, write_note(llm, hit[2], HYDE))
        target = next((i for i, p in enumerate(pool) if p.text.startswith(start)), None)
        for method, order in got.items():
            real.setdefault(method, []).append(target is not None and target in order[:5])
    (out / "rows.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    methods = list(dict.fromkeys(m for m, _ in ranks))
    md = ["# Retrieval methods, planted notes", "", f"Lines: {len(lines)}. Pool: {len(pool)} real passages from the drawing set, one planted note at a time.", "",
          "| method | language | notes | recall@1 | recall@5 | mean reciprocal rank |", "| --- | --- | --- | --- | --- | --- |"]
    for m in methods:
        every = []
        for code in LANGS:
            rs = ranks.get((m, code), [])
            every += rs
            if rs:
                md.append(f"| {m} | {code} | {len(rs)} | {sum(r == 1 for r in rs) / len(rs):.2f} | {sum(r <= 5 for r in rs) / len(rs):.2f} | "
                          f"{sum(1 / r for r in rs) / len(rs):.3f} |")
        md.append(f"| **{m}** | all | {len(every)} | **{sum(r == 1 for r in every) / len(every):.2f}** | **{sum(r <= 5 for r in every) / len(every):.2f}** | "
                  f"**{sum(1 / r for r in every) / len(every):.3f}** |")
    md += ["", "## Real notes (6 lines read by one person): is the note among the first five?", ""]
    md += [f"- {m}: {sum(v)} of {len(v)}" for m, v in real.items()]
    (out / "retrieval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md), flush=True)


if __name__ == "__main__":
    main()
