"""What do the drawings say about the checklist lines no measured rule can decide? Read on a real drawing set, scored without labels.

    python scripts/evidence_eval.py --plans data/real_plans/your_set.pdf [--docs data/real_docs] [--labels needs_fact] [--out reports/evidence]

For every line of the checklists in benchmarks/checklist_labels.json with one of the given labels, the product's evidence step
(interpreter/drawing_evidence.py) looks for the note of the drawing set that is about it. Three things are reported:

  found        lines for which a note was chosen (the same answer with the options in both orders), with the sheet and the words,
               so each can be read: is the note about the line?
  figures      lines whose figure could be compared with the note's: agrees, contradicts, unclear
  planted      a test that needs no label. For every line whose note AGREES, the figure in the note is rewritten so that it breaks
               the requirement (60 minutes becomes 6 for "at least 20"); the comparison must then say "contradicts". This checks
               the comparison itself, on real wording, the way planted errors check the plan rules.

Retrieval is run twice, by words alone and by words and meaning (when the embedding model is installed), to see what the
embedding model adds. The notes of the PDF are read from its text layer, block by block; a set whose text is drawn as outlines
has none. Documents, drawings and reports are never committed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from real_doc_study import Real  # noqa: E402

from reviewpulse.annotate.passages import MIN_LETTERS, Passage, statements  # noqa: E402
from reviewpulse.interpreter import drawing_evidence as ev  # noqa: E402
from reviewpulse.interpreter.checked import clause_body  # noqa: E402
from reviewpulse.interpreter.context import assemble_context  # noqa: E402
from reviewpulse.rules.clauses import split_document  # noqa: E402

LABELS = Path(__file__).resolve().parent.parent / "benchmarks" / "checklist_labels.json"
NOTE_START = re.compile(r"(?<=[.\s])(?=\d{1,2}\.\s+[A-Z])")


def pdf_passages(path: Path, max_pages: int = 60) -> list[Passage]:
    """The notes of a drawing set from its text layer: one passage per text block, a block of numbered notes cut at each number."""
    import pymupdf

    out, seen = [], set()
    doc = pymupdf.open(path)
    for n in range(min(len(doc), max_pages)):
        for block in doc[n].get_text("blocks"):
            if len(block) < 5 or not isinstance(block[4], str):
                continue
            for part in (s for note in NOTE_START.split(" ".join(block[4].split())) for s in statements(note.strip())):
                if sum(ch.isalpha() for ch in part) >= MIN_LETTERS and part.lower() not in seen:
                    seen.add(part.lower())
                    out.append(Passage(f"{path.stem} p{n + 1}", part))
    return out


def break_figure(note: str, check: dict) -> str | None:
    """The note with the stated figure rewritten so that it breaks the requirement, or None when the figure cannot be found in it."""
    op, limit, _unit = check["required"].split(None, 2)
    stated = re.match(r"([\d.]+)(?: to ([\d.]+))?", check["stated"])
    if not stated:
        return None
    factor = 0.1 if op in (">=", ">") else 10.0
    out = note
    for g in (stated.group(1), stated.group(2)):
        if g is None:
            continue
        new = f"{float(g) * factor:g}"
        out, n = re.subn(rf"(?<![\d.]){re.escape(g)}(?![\d.])", new, out, count=1)
        if n == 0:
            return None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", nargs="+", required=True)
    ap.add_argument("--docs", default="data/real_docs")
    ap.add_argument("--labels", default="needs_fact")
    ap.add_argument("--out", default="reports/evidence")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    passages = [p for plan in args.plans for p in pdf_passages(Path(plan))]
    llm, embedder, reranker = Real(), ev.default_embedder(), ev.default_reranker()
    print(f"{len(passages)} passages from {len(args.plans)} drawing set(s); embedding model: "
          f"{getattr(embedder, 'model', None) or 'not installed (words only)'}; cross-encoder: {'on' if reranker else 'off'}; "
          f"reading model: {llm.model}", flush=True)
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    rows = []
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
            if lab["label"] not in args.labels.split(",") or cid not in ids:
                continue
            body = clause_body(assemble_context(doc.name, full, clauses, cid))
            t0 = time.time()
            words = ev.retrieve(body, passages, None)
            found = ev.find_evidence(body, passages, llm, embedder, reranker)
            row = {"doc": docname, "id": cid, "label": lab["label"], "need": lab.get("need"), "text": body[:300],
                   "chosen": found.chosen, "checks": found.checks, "summary": found.summary,
                   "candidates": found.candidates[:3], "words_only_top": [p.text[:120] for p in words[:3]],
                   "chosen_in_words_only": bool(found.chosen) and any(p.text == found.chosen["text"] for p in words),
                   "planted": None, "seconds": round(time.time() - t0, 1)}
            agreeing = [c for c in found.checks if c["result"] == "agrees"]
            if found.chosen and agreeing:
                broken = break_figure(found.chosen["text"], agreeing[0])
                if broken is not None:
                    again = [c.result for c in ev.compare(body, broken, llm)]
                    row["planted"] = "caught" if "contradicts" in again else f"missed ({', '.join(again) or 'no check'})"
            rows.append(row)
            print(f"  {docname[3:16]:<13} {cid[:10]:<10} {'FOUND' if found.chosen else '-':<6} "
                  f"{','.join(c['result'] for c in found.checks) or '-':<22} {(found.chosen or {}).get('text', '')[:70]}", flush=True)
    (out / "rows.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    found = [r for r in rows if r["chosen"]]
    results = [c["result"] for r in rows for c in r["checks"]]
    planted = [r["planted"] for r in rows if r["planted"]]
    lines = ["# Evidence in the drawings", "",
             f"Lines read: {len(rows)} ({args.labels}). Passages: {len(passages)}. Embedding model: {getattr(embedder, 'model', None) or 'none'}. "
             f"Cross-encoder: {'on' if reranker else 'off'}.", "",
             f"- a note was chosen for {len(found)} of {len(rows)} lines (each is listed below, to be read)",
             f"- of those, the note was also among the top passages by words alone for {sum(r['chosen_in_words_only'] for r in found)}",
             f"- figures compared: {results.count('agrees')} agree, {results.count('contradicts')} contradict, "
             f"{results.count('unclear')} unclear, {results.count('no figure')} with no figure of that kind in the note",
             f"- planted contradictions: {sum(p == 'caught' for p in planted)} of {len(planted)} caught", "",
             "## Lines with a note (read each: is the note about the line?)", ""]
    lines += [f"- {r['doc'][:22]} {r['id']} | {r['text'][:110]} | {r['chosen']['sheet']}: {r['chosen']['text'][:170]} | "
              f"{'; '.join(c['required'] + ' vs ' + str(c['stated']) + ': ' + c['result'] for c in r['checks']) or 'no figure to compare'}"
              f"{' | planted: ' + r['planted'] if r['planted'] else ''}" for r in found] or ["- none"]
    lines += ["", "## Lines with no note chosen (the best passage found is shown)", ""]
    lines += [f"- {r['doc'][:22]} {r['id']} | {r['text'][:110]} | best: {(r['candidates'] or [{'text': '-'}])[0]['text'][:120]}"
              for r in rows if not r["chosen"]]
    (out / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:8]), flush=True)


if __name__ == "__main__":
    main()
