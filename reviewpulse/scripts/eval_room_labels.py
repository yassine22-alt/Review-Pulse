"""Label -> room type accuracy on CubiCasa5K test spaces (lexicon never built from test).

    python scripts/eval_room_labels.py [--llm]

Reads data/mappings/cubicasa_room_labels.json (scripts/mine_room_labels.py). Scored: test spaces
whose ground-truth class maps to a room type (not Undefined/UserDefined/Room). Variants:
  baseline_fr_en   the FR/EN keyword list used before the lexicon (kept here verbatim)
  curated          annotate/lexicon/curated.yaml alone
  curated+mined    the shipped lexicon
  +llm             unmatched labels sent to the local LLM fallback (--llm)
"recognised" = the text is read as a room label at all (what P-1 needs); "correct" = right type.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BASELINE = {
    "bedroom": ["chambre", "ch", "bedroom", "suite parentale", "bed"],
    "bathroom": ["salle de bain", "salle de bains", "sdb", "salle d'eau", "salle deau", "bath", "bathroom", "douche"],
    "wc": ["wc", "toilettes", "toilette", "w.c."],
    "kitchen": ["cuisine", "kitchen", "kitchenette"],
    "living": ["salon", "sejour", "living", "living room", "salle a manger", "dining"],
    "corridor": ["couloir", "degagement", "hall", "circulation", "corridor", "dgt"],
    "entry": ["entree", "entry", "hall d'entree"],
    "garage": ["garage", "parking"],
    "storage": ["cellier", "buanderie", "rangement", "storage", "placard", "dressing"],
    "stairs": ["escalier", "stairs", "stair"],
    "terrace": ["terrasse", "balcon", "loggia", "terrace", "balcony"],
    "office": ["bureau", "office"],
}
# a toilet labelled "WC" is drawn as Bath in CubiCasa; wc and bathroom count as the same wet room
SAME = {("wc", "bathroom"), ("bathroom", "wc")}


def main() -> None:
    from reviewpulse.annotate import text_classify as tc
    from reviewpulse.eval.adapters.cubicasa import room_type_of

    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "reports"))
    a = ap.parse_args()
    rows = json.loads((ROOT / "data" / "mappings" / "cubicasa_room_labels.json").read_text(encoding="utf-8"))
    test = [(r["label"], room_type_of(r["space_class"]), r["n"]) for r in rows if r["split"] == "test"]
    test = [(t, rt, n) for t, rt, n in test if rt != "other"]

    def lookup_from(words_by_type):
        lex = {tc.label_core(w): rt for rt, ws in words_by_type.items() for w in ws}

        def f(text):
            core = tc.label_core(text)
            if core in lex:
                return lex[core]
            head = core
            while " " in head:
                head = head.rsplit(" ", 1)[0]
                if head in lex and len(core) - len(head) <= 6:
                    return lex[head]
            return None
        return f

    import yaml
    cur = yaml.safe_load((tc.LEXICON_DIR / "curated.yaml").read_text(encoding="utf-8"))["types"]
    variants = {"baseline_fr_en": lookup_from(BASELINE),
                "curated": lookup_from({rt: [w for ws in langs.values() for w in ws] for rt, langs in cur.items()}),
                "curated+mined": tc.match_room}
    if a.llm:
        from reviewpulse.annotate.label_llm import classify_labels

        unknown = sorted({t for t, _rt, _n in test if tc.match_room(t) is None})
        llm = classify_labels(unknown)

        def with_llm(text):
            return tc.match_room(text) or (llm.get(text) or (None, 0))[0]
        variants["curated+mined+llm"] = with_llm
        # the model alone on every test label: how it reads labels no lexicon lists
        alone = classify_labels(sorted({t for t, _rt, _n in test}))
        variants["llm_only"] = lambda text: (alone.get(text) or (None, 0))[0]
    total = sum(n for _t, _rt, n in test)
    res, misses = {}, {}
    for name, f in variants.items():
        rec = cor = 0
        miss: Counter = Counter()
        for t, rt, n in test:
            got = f(t)
            if got:
                rec += n
                if got == rt or (got, rt) in SAME:
                    cor += n
                else:
                    miss[f"{t} -> {got} (truth {rt})"] += n
            else:
                miss[f"{t} -> none (truth {rt})"] += n
        res[name] = {"recognised": round(rec / total, 4), "correct": round(cor / total, 4),
                     "precision_of_recognised": round(cor / rec, 4) if rec else 0.0}
        misses[name] = miss.most_common(15)
    out = Path(a.out) / "2026-10-25_room_labels_cubicasa.md"
    lines = ["# Evaluation: room labels -> room type", "", "- dataset: CubiCasa5K test split ground-truth labels "
             f"({total} labelled spaces with a room type; lexicon mined from train+val only)", "", "## Metrics", "",
             "| variant | recognised | correct | precision |", "|---|---|---|---|"]
    for k, v in res.items():
        lines.append(f"| {k} | {v['recognised']:.3f} | {v['correct']:.3f} | {v['precision_of_recognised']:.3f} |")
    lines += ["", "## Most frequent misses (shipped lexicon)", ""]
    last = "curated+mined"
    lines += [f"- {m} x{n}" for m, n in misses[last]]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))
    print("misses", {k: v[:10] for k, v in misses.items() if k in (last, "llm_only")})


if __name__ == "__main__":
    main()
