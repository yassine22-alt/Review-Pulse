"""Score the frozen two model rule against a key, with the pass marks of docs/progress/M33.

    python scripts/vision_rule_eval.py <key.json> <small model rows folder> <large model rows folder> [--out score.json]

The rule: yes only when the small model, asked about the whole area, and the large model, asked on tiles, both say yes; the
place is the large model's. Every question of the key must have an answer from both runs, and an error counts as not answered,
which stops the scoring rather than counting as a no.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MARKS = {"false_yes_share_at_most": 0.02, "right_place_share_at_least": 0.85, "drawn_found_share_at_least": 0.50}
PLACE_AT_MOST = 0.35            # of the area: naming more than this points at nothing


def interval(k: int, n: int, level: float = 0.95) -> list[float] | None:
    """The exact (Clopper and Pearson) interval of a share of k in n."""
    if not n:
        return None
    from scipy.stats import beta

    tail = (1 - level) / 2
    low = 0.0 if k == 0 else float(beta.ppf(tail, k, n - k + 1))
    high = 1.0 if k == n else float(beta.ppf(1 - tail, k + 1, n - k))
    return [round(low, 4), round(high, 4)]


def share(k: int, n: int) -> dict:
    return {"count": k, "of": n, "share": round(k / n, 4) if n else None, "interval95": interval(k, n)}


def points(row: dict) -> bool:
    return row["pointing"]["touches"] and row["pointing"]["share_of_area_named"] <= PLACE_AT_MOST


def score(ids: list[str], truth: dict, said_yes, placed) -> dict:
    """truth: id -> the key's question; said_yes(id) -> bool; placed(id) -> bool, only asked for a yes."""
    there = [i for i in ids if truth[i]["present"]]
    gone = [i for i in ids if not truth[i]["present"]]
    found = [i for i in there if said_yes(i)]
    drawn = [i for i in there if truth[i].get("cue") == "drawn"]
    return {"A_false_yes": share(sum(map(said_yes, gone)), len(gone)),
            "B_right_place_of_its_yes": share(sum(map(placed, found)), len(found)),
            "C_drawn_only_found": share(sum(map(said_yes, drawn)), len(drawn)),
            "found_of_all_there": share(len(found), len(there))}


def passes(result: dict) -> dict:
    a, b, c = (result[k]["share"] for k in ("A_false_yes", "B_right_place_of_its_yes", "C_drawn_only_found"))
    got = {"A": a is not None and a <= MARKS["false_yes_share_at_most"],
           "B": b is not None and b >= MARKS["right_place_share_at_least"],
           "C": c is not None and c >= MARKS["drawn_found_share_at_least"]}
    return {**got, "all": all(got.values())}


def rows(folder: Path, mode: str) -> dict:
    text = (folder / f"rows_{mode}.jsonl").read_text(encoding="utf-8")
    return {r["id"]: r for r in map(json.loads, text.splitlines()) if r["answer"] != "error"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key", type=Path)
    ap.add_argument("small", type=Path)
    ap.add_argument("large", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    key = json.loads(args.key.read_text(encoding="utf-8"))
    truth, area_of = {}, {}
    for a in key["areas"]:
        for q in a["questions"]:
            truth[q["id"]], area_of[q["id"]] = q, a
    runs = {"small whole": rows(args.small, "whole"), "small tiles": rows(args.small, "tiles") if
            (args.small / "rows_tiles.jsonl").exists() else {}, "large whole": rows(args.large, "whole"),
            "large tiles": rows(args.large, "tiles")}
    runs = {k: v for k, v in runs.items() if v}
    for name in ("small whole", "large tiles"):
        missing = [i for i in truth if i not in runs[name] or runs[name][i]["what"] != truth[i]["what"]]
        if missing:
            sys.exit(f"{name}: no answer to {len(missing)} questions of this key, e.g. {missing[:5]}")
    small, large = runs["small whole"], runs["large tiles"]
    yes = lambda r, i: r[i]["answer"] == "yes"  # noqa: E731
    rule_yes = lambda i: yes(small, i) and yes(large, i)  # noqa: E731
    rule_place = lambda i: points(large[i])  # noqa: E731
    ids = list(truth)
    out = {"questions": len(ids), "unclear_left_out": len(key.get("unclear", [])), "marks": MARKS,
           "rule": score(ids, truth, rule_yes, rule_place)}
    out["passes"] = passes(out["rule"])
    out["alone"] = {name: score(ids, truth, lambda i, r=r: yes(r, i), lambda i, r=r: points(r[i]))
                    for name, r in runs.items() if all(i in r for i in ids)}
    for title, group in (("by_source", lambda i: area_of[i]["pdf"]), ("by_question", lambda i: truth[i]["what"])):
        out[title] = {g: score([i for i in ids if group(i) == g], truth, rule_yes, rule_place)
                      for g in sorted({group(i) for i in ids})}
    out["rule_wrong_yes"] = [{"id": i, "what": truth[i]["what"]} for i in ids if rule_yes(i) and not truth[i]["present"]]
    if args.out:
        args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("questions", "unclear_left_out", "rule", "passes", "alone", "rule_wrong_yes")}, indent=1))


if __name__ == "__main__":
    main()
