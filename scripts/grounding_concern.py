"""Measure the kind-of-requirement check (interpreter/grounding.py: check_concern), the companion of grounding_choice.py for
rules that state a route, a direct link, a count or a yes/no fact instead of a measured number.

    python scripts/grounding_concern.py [--n 120] [--model qwen2.5:7b]

Annotation free, on the synthetic corpus (English and French, several domains):
  right      the kind the true rule states: the check should agree (accept)
  other      a different kind than the rule's own is claimed: the check should disagree (reject)
  unrelated  sentences about things no plan shows (rides, fees, signs ...): no kind should be accepted (reject)
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from reviewpulse.interpreter.grounding import KIND_SYSTEM, agrees, concerns, kind_choices, measured_facts
from reviewpulse.xeval.drafters import BoundedOllama

UNRELATED = [
    "Where wheelchair spaces are entered only from the side, amusement rides shall be designed to permit sufficient maneuvering "
    "clearance for individuals using a wheelchair to enter and exit the ride.",
    "Les prises de courant doivent être situées à moins de 1,30 mètre du sol.",
    "The applicant shall pay the fee within thirty days of the date of the notice.",
    "Signage shall be written in a typeface that contrasts with its background.",
    "Les matériaux employés doivent être résistants à l'humidité.",
    "Der Bauherr muss die Genehmigung vor Beginn der Arbeiten einholen.",
    "Handrails shall be mounted at a height suitable for children.",
    "Les ascenseurs doivent être entretenus chaque année par un organisme agréé.",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--model", default="qwen2.5:7b")
    args = ap.parse_args()
    items = [json.loads(line) for line in Path("reports/extractor_eval/corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    random.Random(7).shuffle(items)
    client = BoundedOllama(model=args.model, num_predict=60)
    rng = random.Random(3)
    right, other = [0, 0], [0, 0]
    by_kind: dict[str, list[int]] = {}
    for it in items:
        req = it["program"]["requirement"]
        true = concerns(req)
        if measured_facts(req):
            true = true + ["measure"]
        if not true:
            continue
        menu = kind_choices(it["catalogue"]["bindings"])
        true = [t for t in true if t in menu]
        if not true or right[1] >= args.n:
            continue
        ok, _ = agrees(client, it["text"], menu, true[0], KIND_SYSTEM)
        right[1] += 1
        right[0] += ok
        by_kind.setdefault(true[0], []).append(ok)
        wrong = [k for k in menu if k not in true]
        if wrong:
            other[1] += 1
            other[0] += not agrees(client, it["text"], menu, rng.choice(wrong), KIND_SYSTEM)[0]
        if right[1] % 10 == 0:
            print(f"right {right[0]}/{right[1]}  other rejected {other[0]}/{other[1]}", flush=True)
    menu = kind_choices(items[0]["catalogue"]["bindings"])
    unrelated = [0, 0]
    for text in UNRELATED:
        for k in menu:
            unrelated[1] += 1
            unrelated[0] += not agrees(client, text, menu, k, KIND_SYSTEM)[0]
    print("\nkind check on", args.model)
    print(f"  right kind accepted: {right[0]}/{right[1]} = {right[0] / max(right[1], 1):.2f}   "
          + ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(by_kind.items())))
    print(f"  another kind claimed: rejected {other[0]}/{other[1]} = {other[0] / max(other[1], 1):.2f}")
    print(f"  sentences no plan shows, any kind claimed: rejected {unrelated[0]}/{unrelated[1]} = "
          f"{unrelated[0] / max(unrelated[1], 1):.2f}")


if __name__ == "__main__":
    main()
