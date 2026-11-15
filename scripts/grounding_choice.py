"""Measure the multiple choice grounding check (src/reviewpulse/interpreter/grounding.py).

    python scripts/grounding_choice.py [--n 100] [--model qwen2.5:7b]

Three conditions, all annotation free, on the synthetic corpus (English and French, several domains):
  right     the sentence's true measured fact is among the choices: the check should agree with the rule (accept)
  swapped   the rule's fact is replaced by another numeric fact of the same unit: the check should disagree (reject)
  missing   the true fact is removed from the choices, as when the plan does not provide what the sentence limits (the
            sockets case): the check should answer "none" or another fact, never the removed one (reject)
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from reviewpulse.interpreter.grounding import NONE, agrees, choices, measured_facts, pick
from reviewpulse.xeval.drafters import BoundedOllama

NO_PLAN_FACT = [  # sentences whose quantity no plan fact provides, in several languages
    ("fr", "Les prises de courant, d'antenne et de téléphone doivent être à moins de 1,30 mètre du sol."),
    ("fr", "Les poignées de porte doivent être situées à une hauteur comprise entre 0,90 et 1,30 mètre du sol."),
    ("fr", "La hauteur du seuil de la menuiserie doit être inférieure ou égale à 2 cm."),
    ("en", "Socket outlets shall be installed at a height of at least 0.45 m above the finished floor."),
    ("en", "The thickness of the insulation layer shall not be less than 120 mm."),
    ("en", "Handrails shall be mounted between 0.85 m and 0.95 m above the stair nosing."),
    ("de", "Steckdosen müssen in einer Höhe von mindestens 0,40 m über dem Fußboden angebracht werden."),
    ("es", "Los interruptores deberán instalarse a una altura máxima de 1,20 m sobre el suelo."),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--model", default="qwen2.5:7b")
    args = ap.parse_args()
    items = [json.loads(line) for line in Path("reports/extractor_eval/corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    random.Random(5).shuffle(items)
    client = BoundedOllama(model=args.model, num_predict=60)
    stats = {"right": [0, 0], "swapped": [0, 0], "missing": [0, 0]}      # [as the check should answer, asked]
    by_lang: dict[str, list[int]] = {}
    rng = random.Random(9)
    for it in items:
        facts = measured_facts(it["program"]["requirement"])
        if not facts:
            continue
        cat = it["catalogue"]["bindings"]
        true = facts[0]
        opts = choices(cat)
        if true not in opts or len(opts) < 3:
            continue
        if sum(s[1] for s in stats.values()) >= 3 * args.n:
            break
        ok, _ = agrees(client, it["text"], opts, true)                     # what the product does, with the order retry
        stats["right"][1] += 1
        stats["right"][0] += ok
        by_lang.setdefault(it["lang"], []).append(ok)
        same = [n for n in opts if n != true and cat[n].get("unit") == cat[true].get("unit")]
        if same:                                                           # the rule is wrong: does the check notice?
            stats["swapped"][1] += 1
            stats["swapped"][0] += not agrees(client, it["text"], opts, rng.choice(same))[0]
        reduced = {k: v for k, v in opts.items() if k != true}
        got2 = pick(client, it["text"], reduced)
        stats["missing"][1] += 1
        stats["missing"][0] += got2 is not None and got2 != true
        if stats["missing"][1] % 10 == 0:
            print({k: f"{a}/{b}" for k, (a, b) in stats.items()}, flush=True)
    print("\nchoice check on", args.model)
    print(f"  right fact present: agrees with the true rule {stats['right'][0]}/{stats['right'][1]}"
          f" = {stats['right'][0] / max(stats['right'][1], 1):.2f}   "
          + ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(by_lang.items())))
    print(f"  swapped rule: rejected {stats['swapped'][0]}/{stats['swapped'][1]} = "
          f"{stats['swapped'][0] / max(stats['swapped'][1], 1):.2f}")
    print(f"  true fact missing: does not pick it {stats['missing'][0]}/{stats['missing'][1]} = "
          f"{stats['missing'][0] / max(stats['missing'][1], 1):.2f}")
    cat = items[0]["catalogue"]["bindings"]
    opts = {n: b.get("description") or n for n, b in cat.items() if b.get("kind") == "number"}
    for lang, text in NO_PLAN_FACT:
        print(f"  no plan fact [{lang}] -> {pick(client, text, opts)}   {text[:70]}")
    print(f"(options for the last block: {len(opts)} facts; the right answer is none)  NONE={NONE}")


if __name__ == "__main__":
    main()
