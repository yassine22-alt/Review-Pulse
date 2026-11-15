"""Slot filling against the free-form arm on the synthetic corpus (English and French, several domains).

    python scripts/slots_eval.py [--n 60] [--model qwen2.5:7b]

For a random sample of corpus clauses: the slot arm (declines when the sentence is not a plain limit), and the free-form arm
that is used otherwise. Correct means behaviourally equivalent to the gold rule on generated plans (xeval/behavior.py), not
text equal. Reported: how often the slot arm applies, how often it is right when it does, and the free-form arm on the same
sentences, so the two can be compared on what they both attempt.
"""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.arms import draft_arm
from reviewpulse.xeval.behavior import compare
from reviewpulse.xeval.drafters import BoundedOllama
from reviewpulse.xeval.synth import read_corpus


def right(ref, program, cat) -> bool:
    if program is None:
        return False
    r = compare(ref, program, cat, 200, seed=1)
    return bool(r.get("equivalent"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--model", default="qwen2.5:7b")
    args = ap.parse_args()
    items = read_corpus(Path("reports/extractor_eval/corpus.jsonl"))
    random.Random(11).shuffle(items)
    client = BoundedOllama(model=args.model)
    tot = {"n": 0, "slot_applies": 0, "slot_right": 0, "slot_wrong": 0, "free_on_slot": 0, "free_right_on_slot": 0,
           "free_right_all": 0}
    t_slot = t_free = 0.0
    for it in items[: args.n]:
        ref = Program.model_validate(it.program)
        tot["n"] += 1
        t0 = time.time()
        d = draft_arm("expr_slots", it, client)
        t_slot += time.time() - t0
        t0 = time.time()
        f = draft_arm("expr_verify", it, client)
        t_free += time.time() - t0
        fr = right(ref, f.program, it.catalogue)
        tot["free_right_all"] += fr
        if d.program is not None:
            tot["slot_applies"] += 1
            ok = right(ref, d.program, it.catalogue)
            tot["slot_right"] += ok
            tot["slot_wrong"] += not ok
            tot["free_on_slot"] += 1
            tot["free_right_on_slot"] += fr
        if tot["n"] % 10 == 0:
            print(tot, flush=True)
    n, a = tot["n"], max(tot["slot_applies"], 1)
    print(f"\n{n} clauses on {args.model}")
    print(f"slot arm applies to {tot['slot_applies']}/{n}; right {tot['slot_right']}/{tot['slot_applies']} "
          f"= {tot['slot_right'] / a:.2f}; wrong-but-accepted {tot['slot_wrong']}; {t_slot / n:.1f} s per clause (incl. declines)")
    print(f"free-form arm on those same clauses: right {tot['free_right_on_slot']}/{tot['free_on_slot']} "
          f"= {tot['free_right_on_slot'] / a:.2f}; on all {n}: {tot['free_right_all']}/{n}; {t_free / n:.1f} s per clause")
    combined = tot["free_right_all"] - tot["free_right_on_slot"] + tot["slot_right"]
    print(f"slots first, free-form for the rest: right {combined}/{n} = {combined / n:.2f} (free-form alone {tot['free_right_all'] / n:.2f})")


if __name__ == "__main__":
    main()
