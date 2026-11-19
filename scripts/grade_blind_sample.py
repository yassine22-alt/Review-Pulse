"""Compare returned independent grades; blanks are pending, never inferred agreement."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

SLOTS = ("subject", "fact", "operator", "value", "unit", "scope")
GRADES = {"correct", "partly_correct", "wrong", "not_applicable", "cannot_grade"}


def agreement(pairs):
    if not pairs:
        return {"exact": [0, 0], "kappa": None}
    left, right = (Counter(row[i] for row in pairs) for i in (0, 1))
    observed = sum(a == b for a, b in pairs) / len(pairs)
    chance = sum(left[value] * right[value] for value in set(left) | set(right)) / len(pairs) ** 2
    return {"exact": [sum(a == b for a, b in pairs), len(pairs)],
            "kappa": (observed - chance) / (1 - chance) if chance < 1 else None}


def grade_sheet(path, key):
    expected = {row["blind_id"]: row for row in key["rows"]}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(expected) or {row["blind_id"] for row in rows} != set(expected):
        raise ValueError("returned sheet must contain each frozen blind ID exactly once")
    pairs, whole, pending, disagreements = [], [], [], []
    for row in rows:
        reference = expected[row["blind_id"]]
        if row["source_clause"] != reference["source"] or row["model_output"] != reference["model_output"]:
            raise ValueError("source or draft changed; review the sheet identity before grading")
        for slot in (*SLOTS, "whole_rule"):
            value = row[slot + "_grade"].strip().lower()
            if not value:
                pending.append([row["blind_id"], slot])
                continue
            if value not in GRADES:
                raise ValueError("grade must be correct, partly_correct, wrong, not_applicable or cannot_grade")
            assistant = reference["whole_rule_grade"] if slot == "whole_rule" else reference["assistant"][slot]
            if value == "cannot_grade" or assistant == value == "not_applicable":
                continue
            (whole if slot == "whole_rule" else pairs).append((assistant, value))
            if assistant != value:
                disagreements.append({"blind_id": row["blind_id"], "slot": slot, "assistant": assistant,
                                      "teammate": value, "notes": row.get("notes", "")})
    return {"status": "PENDING_INDEPENDENT_GRADES" if pending else "RETURNED_GRADES_COMPARED",
            "completed_cells": [len(rows) * 7 - len(pending), len(rows) * 7], "slot_agreement": agreement(pairs),
            "whole_rule_agreement": agreement(whole), "pending": pending, "disagreements": disagreements,
            "limits": "Small purposeful sample. Both not_applicable and cannot_grade excluded. Nominal kappa, no independence or accuracy claim."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheet", type=Path)
    parser.add_argument("key", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = grade_sheet(args.sheet, json.loads(args.key.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("pending", "disagreements")}))


if __name__ == "__main__":
    main()
