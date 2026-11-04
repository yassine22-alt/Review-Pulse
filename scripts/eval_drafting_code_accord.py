"""Clause drafting against CODE-ACCORD (CC BY 4.0): real building-regulation sentences from England
and Finland, annotated by people (Hettiarachchi et al., Scientific Data 2025).

    python scripts/eval_drafting_code_accord.py [--limit N]

Scored on the sentences with exactly one comparison relation between a property and a value
(greater, greater-equal, equal, less-equal, less), so the expected answer is unambiguous:

- direction: lower bound (at least / more than), upper bound (at most / less than) or equal - from the
  model alone, and after the deterministic comparison-word cross-check that the rule actually uses;
- number: the model's threshold is the annotated value's number (when the value is written in digits);
- unsafe: the final direction is wrong and nothing flags the draft for the curator.

Needs Ollama with qwen2.5:7b. Writes reports/drafting_code_accord.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATA = ROOT / "data" / "raw" / "code_accord" / "extracted"
GOLD_DIR = {"greater": "lower", "greater-equal": "lower", "less": "upper", "less-equal": "upper", "equal": "equal"}
OUT_DIR = {"at_least": "lower", "more_than": "lower", "at_most": "upper", "less_than": "upper", "equal_to": "equal"}


def gold_items() -> list[dict]:
    f = next(DATA.glob("*/annotated_data/relations/all.csv"))
    by = defaultdict(list)
    for r in csv.DictReader(open(f, encoding="utf-8")):
        if r["relation_type"] in GOLD_DIR:
            by[r["example_id"]].append(r)
    items = []
    for eid, rs in sorted(by.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else kv[0]):
        if len(rs) != 1:
            continue
        r = rs[0]
        value = re.search(r"<e2>(.*?)</e2>", r["tagged_sentence"])
        nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", value.group(1))] if value else []
        items.append({"id": eid, "text": r["content"], "relation": r["relation_type"],
                      "direction": GOLD_DIR[r["relation_type"]], "value": value.group(1) if value else None,
                      "numbers": nums, "source": r["metadata"]})
    return items


def main() -> None:
    from reviewpulse.rules.clauses import Clause
    from reviewpulse.rules.draft import (
        build_prompt,
        comparison_from_text,
        make_client,
        output_schema,
        validate,
    )

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    items = gold_items()[: a.limit or None]
    client = make_client("ollama")
    schema = output_schema()
    rows, t0 = [], time.time()
    for it in items:
        clause = Clause(id=it["id"], heading="", text=it["text"], page=0, start=0, end=len(it["text"]))
        system, user = build_prompt(clause)
        try:
            out = client.complete(system, user, schema)
        except Exception as e:  # noqa: BLE001 - a failed call is a result
            rows.append({**it, "error": repr(e)[:200]})
            continue
        text_cmp = comparison_from_text(it["text"])
        model_dir = OUT_DIR.get(out.get("comparison"))
        final_dir = OUT_DIR.get(text_cmp or out.get("comparison"))
        d = validate(out, clause, "code-accord")
        num = out.get("number")
        rows.append({**it, "model_comparison": out.get("comparison"), "text_comparison": text_cmp,
                     "model_direction": model_dir, "final_direction": final_dir, "model_number": num,
                     "number_ok": (num is not None and any(abs(float(num) - g) < 1e-6 for g in it["numbers"]))
                     if it["numbers"] else None,
                     "flags": d.flags, "errors": d.errors, "checkable": d.checkable, "property": out.get("property")})
        print(it["id"], it["relation"], "->", out.get("comparison"), num, flush=True)

    ok = [r for r in rows if "error" not in r]
    n = len(ok)

    def share(pred):
        return round(sum(1 for r in ok if pred(r)) / n, 4) if n else 0.0

    with_num = [r for r in ok if r["number_ok"] is not None]
    unsafe = [r for r in ok if r["final_direction"] != r["direction"] and r["final_direction"] is not None
              and not r["flags"] and not r["errors"]]
    summary = {
        "sentences": n, "failed_calls": len(rows) - n, "seconds": round(time.time() - t0),
        "relations": dict(Counter(r["relation"] for r in ok)),
        "direction_correct_model": share(lambda r: r["model_direction"] == r["direction"]),
        "direction_correct_final": share(lambda r: r["final_direction"] == r["direction"]),
        "direction_missing_final": share(lambda r: r["final_direction"] is None),
        "cross_check_fired": share(lambda r: r["text_comparison"] is not None),
        "number_correct": round(sum(r["number_ok"] for r in with_num) / len(with_num), 4) if with_num else None,
        "number_scored_on": len(with_num),
        "unsafe_wrong_direction_unflagged": len(unsafe),
        "checkable_from_drawings": share(lambda r: r["checkable"] == "from_drawings"),
        "confusion_final": dict(Counter(f"{r['direction']}->{r['final_direction']}" for r in ok)),
    }
    out_path = ROOT / "reports" / "drafting_code_accord.json"
    out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
