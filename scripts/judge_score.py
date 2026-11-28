"""The larger model's answers against the pass marks of docs/progress/M36.

    python scripts/judge_score.py pending <candidates.jsonl> <parts_eval run> <answers.jsonl> <to_judge.json>
    python scripts/judge_score.py score   <candidates.jsonl> <parts_eval run> <answers.jsonl> [--new new_judgements.json]

``pending`` lists the pieces the new layouts would show that nobody has judged. ``score`` stops while any is left. Mark A uses
only the judgements made before this run; the new ones are kept in their own file and count for the layouts.

Layouts, per part. app: what the app shows today. reader: the model's first three yes answers, in search order, then the app's.
names: the reader's, then the drawing texts matching the model's names (M32's cleaning and matching).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from expand_eval import drawing_names, matches  # noqa: E402
from parts_eval import fingerprint  # noqa: E402

EARLIER = ROOT / "benchmarks" / "austin_stpete_parts_judgements.json"
FIRST_YES = 3


class _Answered:
    """The model's saved list of names, handed to the same cleaning M32 used."""

    def __init__(self, names):
        self.names = names

    def complete(self, *_):
        return {"names": self.names}


def load(args):
    parts = [json.loads(x) for x in args.candidates.read_text(encoding="utf-8").splitlines()]
    pieces = [(p["key"].split("|", 1)[0], p["text"], 1) for p in
              json.loads(args.candidates.with_suffix(".pieces.json").read_text(encoding="utf-8"))]
    answers = {}
    for r in map(json.loads, args.answers.read_text(encoding="utf-8").splitlines()):
        if "error" not in r:
            answers[(r["task"], r["part"], r["key"])] = r
    lost = [(p["part"], c["key"]) for p in parts for c in p["candidates"] if ("judge", p["part"], c["key"]) not in answers]
    lost += [(p["part"], None) for p in parts if ("names", p["part"], None) not in answers]
    if lost:
        sys.exit(f"{len(lost)} questions have no answer, e.g. {lost[:3]}: run the model again, it goes on where it was")
    rows = json.loads((args.run / "rows.json").read_text(encoding="utf-8"))
    app = {part["id"]: [*row["today"], *part["notes"], *part["written"]] for row in rows for part in row["parts"]}
    if set(app) != {p["part"] for p in parts}:
        sys.exit("the candidates and the run do not speak of the same parts")
    out = []
    for p in parts:
        said_yes = [c["key"] for c in p["candidates"] if answers[("judge", p["part"], c["key"])]["useful"] == "yes"]
        shown = list(dict.fromkeys([*said_yes[:FIRST_YES], *app[p["part"]]]))
        names = drawing_names(_Answered(answers[("names", p["part"], None)]["names"]), p["asks"], p["line"])
        found = [f"{sheet}|{text}" for sheet, text, _ in matches(names, pieces)]
        out.append({**p, "app": list(dict.fromkeys(app[p["part"]])), "yes": said_yes, "reader": shown,
                    "names_add": [k for k in found if k not in shown]})
    return out


def judgements(*files: Path) -> dict:
    got: dict = {"yes": {}, "no": {}}
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for side in got:
            for part, marks in data.get(side, {}).items():
                got[side].setdefault(part, set()).update(marks)
    return got


def known(judged: dict, part: str, piece: str) -> bool | None:
    mark = fingerprint(piece)
    if mark in judged["yes"].get(part, ()):
        return True
    return False if mark in judged["no"].get(part, ()) else None


def score(parts: list[dict], earlier: dict, both: dict) -> dict:
    said = [known(earlier, p["part"], k) for p in parts for k in p["yes"]]
    useful_candidates = [(p, c["key"]) for p in parts for c in p["candidates"] if known(earlier, p["part"], c["key"])]
    right = sum(v is True for v in said)
    judged_yes_answers = sum(v is not None for v in said)
    has = lambda p, pieces: any(known(both, p["part"], k) for k in pieces)  # noqa: E731
    app = {p["part"] for p in parts if has(p, p["app"])}
    reader = {p["part"] for p in parts if has(p, p["reader"])}
    by_names = sorted(p["part"] for p in parts if p["part"] not in app | reader and has(p, p["names_add"]))
    precision = right / judged_yes_answers if judged_yes_answers else 0.0
    added = sum(len(p["names_add"]) for p in parts) / len(parts)
    return {
        "parts": len(parts), "candidates": sum(len(p["candidates"]) for p in parts),
        "model_yes": len(said), "model_yes_judged_before": judged_yes_answers, "of_those_useful": right,
        "useful_candidates_judged_before": len(useful_candidates),
        "recall_on_them": round(sum(k in p["yes"] for p, k in useful_candidates) / len(useful_candidates), 3)
        if useful_candidates else None,
        "parts_with_a_useful_piece": {"app": len(app), "reader": len(reader), "reader_and_names": len(reader) + len(by_names)},
        "reader_gains": sorted(reader - app), "reader_loses": sorted(app - reader), "names_reach_further": by_names,
        "names_add_pieces_per_part": round(added, 2),
        "mean_pieces_shown": {"app": round(sum(len(p["app"]) for p in parts) / len(parts), 2),
                              "reader": round(sum(len(p["reader"]) for p in parts) / len(parts), 2)},
        "marks_reader": {"A precision at least 0.60": {"got": round(precision, 3), "met": precision >= 0.60},
                         "B parts at least 30": {"got": len(reader), "met": len(reader) >= 30},
                         "C no part loses": {"got": len(app - reader), "met": not app - reader}},
        "marks_names": {"at least 3 more parts": {"got": len(by_names), "met": len(by_names) >= 3},
                        "at most 3 pieces a part on average": {"got": round(added, 2), "met": added <= 3}},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("pending", "score"))
    ap.add_argument("candidates", type=Path)
    ap.add_argument("run", type=Path)
    ap.add_argument("answers", type=Path)
    ap.add_argument("to_judge", type=Path, nargs="?")
    ap.add_argument("--new", type=Path)
    args = ap.parse_args()
    parts = load(args)
    earlier = judgements(EARLIER)
    both = judgements(EARLIER, *([args.new] if args.new and args.new.exists() else []))
    waiting = [{"part": p["part"], "asks": p["asks"], "line": p["line"], "piece": k, "mark": fingerprint(k)}
               for p in parts for k in dict.fromkeys([*p["reader"], *p["names_add"]]) if known(both, p["part"], k) is None]
    if args.mode == "pending":
        if args.to_judge is None:
            sys.exit("say where to write the pieces to judge")
        args.to_judge.write_text(json.dumps(waiting, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(waiting)} pieces to judge, over {len({w['part'] for w in waiting})} parts -> {args.to_judge}")
        return
    if waiting:
        sys.exit(f"{len(waiting)} shown pieces are not judged yet: run 'pending' and judge them")
    print(json.dumps(score(parts, earlier, both), indent=1))


if __name__ == "__main__":
    main()
