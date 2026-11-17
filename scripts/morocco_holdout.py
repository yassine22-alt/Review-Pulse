"""Run the same frozen, manually interpreted obligations with either checker checkout."""
import argparse
import json
from collections import Counter
from pathlib import Path

from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Inputs, Program

LABELS = Path(__file__).resolve().parents[1] / "reports/morocco-holdout-labels.json"
METRICS = {"travel", "connector", "door_width", "dead_end", "discharge"}


def fact(name, entity="building"):
    return {"node": "fact", "name": name, "entity": entity}


def comparison(left, op, limit, unit):
    return {"node": op, "left": left, "right": {"node": "literal", "value": limit, "unit": unit}}


def count():
    return {"node": "count", "collection": "exits", "variable": "$e", "where": fact("eligible", "$e")}


def requirement(check):
    mode, *args = check
    if mode == "fact":
        name, *predicate = args
        return comparison(fact(name), *predicate)
    if mode == "both":
        return {"node": "all", "args": [fact(name) for name in args]}
    if mode == "count":
        return comparison(count(), *args, "count")
    if mode != "travel":
        raise ValueError(f"unsupported fixture expression: {mode}")
    return {"node": "any", "args": [
        {"node": "all", "args": [
            comparison(count(), "eq", 1, "count"), comparison(fact("travel"), "le", 30, "m")]},
        {"node": "all", "args": [
            comparison(count(), "ge", 2, "count"), comparison(fact("travel"), "le", 50, "m")]},
    ]}


def inputs(plan, reviewed):
    values = dict(plan["observed"])
    if reviewed:
        values.update(plan["reviewed"])
    exits = values.pop("exits")

    def annotation(value, source):
        return {"value": value, "source": source, "trusted": value is not None}

    facts = {"building": {
        name: annotation(value, "reviewed reference evidence" if reviewed and name in plan["reviewed"]
                         else "fixture plan observation") for name, value in values.items()
    }}
    for index, value in enumerate(exits):
        facts[f"e{index + 1}"] = {
            "eligible": annotation(value, "reviewed exit survey" if reviewed else "fixture exit observation")
        }
    bindings = {name: {"kind": "number", "unit": "m"} for name in METRICS}
    bindings.update({name: {"kind": "boolean"} for name in ("normal", "accessory", "two_way", "eligible")})
    return Inputs.model_validate({
        "bindings": bindings, "facts": facts,
        "collections": {"exits": {"items": [k for k in facts if k != "building"],
                                  "complete": reviewed, "trusted": True}},
    })


def check(clause, evidence):
    text = clause["meaning"]
    expression = clause.get("check")
    program = Program.model_validate({
        "id": clause["id"], "title": clause["meaning"], "document": "Morocco 2-14-499",
        "sources": [{"clause": clause["ref"], "start": 0, "end": len(text), "quote": text}],
        "requirement": requirement(expression) if expression else {"node": "literal", "value": True},
        "unresolved": [] if expression else [clause["gap"]],
    })
    result = run_program(program, evidence, include_drafts=True)
    return {"outcome": result["outcome"], "missing": result["trace"]["missing"]}


def metrics(results, stage):
    verdicts = Counter(row[stage]["outcome"] for row in results)
    violations = [row for row in results if row[stage]["outcome"] == "VIOLATED"]
    true_violations = sum(row["gold"] == "VIOLATED" for row in violations)
    return {
        "applicable": len(results), "pass": verdicts["SATISFIED"], "violated": verdicts["VIOLATED"],
        "unresolved": verdicts["UNRESOLVED"],
        "false_passes": sum(row[stage]["outcome"] == "SATISFIED" and row["gold"] == "VIOLATED" for row in results),
        "violation_precision": true_violations / len(violations) if violations else None,
        "violation_precision_numerator": true_violations,
        "violation_precision_denominator": len(violations),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    suite = json.loads(LABELS.read_text(encoding="utf-8"))
    results = []
    for index, (key, plan) in enumerate(suite["plans"].items()):
        automatic, reviewed = inputs(plan, False), inputs(plan, True)
        for clause in suite["clauses"]:
            before_review, after_review = check(clause, automatic), check(clause, reviewed)
            results.append({
                "plan": key, "clause": clause["id"],
                "gold": {"PASS": "SATISFIED", "FAIL": "VIOLATED"}[clause["truth"][index]],
                "automatic": before_review, "reviewed": after_review,
                "automatic_blocker": clause["blocker"] if before_review["outcome"] == "UNRESOLVED" else None,
                "blocker": clause["blocker"] if after_review["outcome"] == "UNRESOLVED" else None,
                "gap": clause["gap"] if after_review["outcome"] == "UNRESOLVED" else None,
            })
    report = {
        "automatic": metrics(results, "automatic"), "after_review": metrics(results, "reviewed"),
        "newly_decided_by_review": dict(Counter(
            row["reviewed"]["outcome"] for row in results if row["automatic"]["outcome"] == "UNRESOLVED"
            and row["reviewed"]["outcome"] != "UNRESOLVED"
        )),
        "blockers_after_review": dict(Counter(row["blocker"] for row in results if row["blocker"])),
        "potential_unlocks_unique_clauses": {
            gap: len({row["clause"] for row in results if row["gap"] == gap})
            for gap in sorted({row["gap"] for row in results if row["gap"]})
        },
        "cases": results,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
