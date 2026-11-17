"""Measure the round-trip gate on the rules a benchmark run wrote, without running the pipeline again.

    python scripts/roundtrip_eval.py reports/benchmark_x/rows.jsonl [--judge local|hosted]

Every drafted rule of the run is shown to the judge next to its sentence. What matters: how many rules that are right (a correct
rule on a decidable line) would be refused (a loss), and how many rules that should not exist (a rule on a line that is not about a
plan) would be refused (a gain). Rules that are partial are only counted, since they stay with a note.
"""

from __future__ import annotations

import argparse
import json
import sys

from reviewpulse.interpreter.roundtrip import compare


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--judge", default="local", choices=["local", "hosted"])
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.judge == "hosted":
        from reviewpulse.llm import primary_from_env

        client = primary_from_env()
    else:
        from reviewpulse.xeval.drafters import BoundedOllama

        client = BoundedOllama()
    rows = [json.loads(line) for line in open(args.rows, encoding="utf-8")]
    kept = lost = gained = missed = 0
    for r in rows:
        if not r.get("readback"):
            continue
        verdict = compare(client, r["text"], r.get("plain") or r["readback"], r.get("not_checked"))
        should_exist = r["outcome"] == "correct"
        refused = verdict == "different"
        kept += (not refused) and should_exist
        lost += refused and should_exist
        gained += refused and not should_exist
        missed += (not refused) and not should_exist
        print(f"{r['outcome']:<12} {verdict:<9} {r['doc'][:12]} {r['id']:<8} {r['text'][:70]}")
    print(f"\njudge={args.judge}: right rules kept {kept}, right rules lost {lost}; wrong or unsupported rules refused {gained}, "
          f"still accepted {missed}")


if __name__ == "__main__":
    main()
