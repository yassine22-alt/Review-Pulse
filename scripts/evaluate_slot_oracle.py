"""Evaluate frozen development slots without calling a drafting model."""
import argparse
import copy
import json
from collections import Counter
from pathlib import Path

from development_cases import load_cases

from reviewpulse.interpreter.checked import catalogue_from
from reviewpulse.interpreter.schema import Program
from reviewpulse.interpreter.structured import SlotDraft, SlotFailure, compile_slots
from reviewpulse.interpreter.validate import validate_program
from reviewpulse.xeval.behavior import compare
from reviewpulse.xeval.world import bindings_of


def oracle_catalogue(active, row):
    catalogue = copy.deepcopy(active)
    catalogue["bindings"].update(row["proposed_bindings"])
    owners = {}
    for node in row["slots"]["nodes"]:
        if node.get("collection") and node.get("variable"):
            owners[node["variable"]] = node["collection"]
            catalogue["collections"].setdefault(node["collection"], {"facts": []})
    for node in row["slots"]["nodes"]:
        if node["op"] != "fact":
            continue
        if node["entity"] == "building":
            catalogue["building"] = sorted(set(catalogue["building"]) | {node["name"]})
        elif node["entity"] in owners:
            member = catalogue["collections"][owners[node["entity"]]]
            member["facts"] = sorted(set(member["facts"]) | {node["name"]})
    return catalogue


def evaluate(row, case, catalogue):
    context = case["context"]
    reference = Program.model_validate({
        "id": row["id"], "title": row["frozen_reading"], "document": context.document,
        "requirement": row["reference_expression"],
        "sources": [{"clause": clause.id, "start": clause.start, "end": clause.end, "quote": clause.text}
                    for clause in context.clauses],
    })
    try:
        candidate = compile_slots(SlotDraft.model_validate(row["slots"]), context, catalogue)
        validate_program(reference, bindings_of(catalogue), list(catalogue["collections"]))
        behavioral = compare(reference, candidate, catalogue, n_worlds=64, seed=93)
        roots_equal = candidate.requirement == reference.requirement
        return {"stage": "retained", "exact_reference_tree": roots_equal,
                "behavioral_equivalent": behavioral["equivalent"], "worlds": 64,
                "correct_unresolved": False}
    except SlotFailure as error:
        return {"stage": error.stage, "detail": str(error), "exact_reference_tree": False,
                "behavioral_equivalent": False, "correct_unresolved": bool(row["specialist_or_context_gap"])}
    except ValueError as error:
        return {"stage": "reference_validation", "detail": str(error),
                "exact_reference_tree": False, "behavioral_equivalent": False, "correct_unresolved": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    frozen = json.loads((repo / "reports/development-oracle-slots.json").read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in load_cases(repo, args.access_text)}
    rows = []
    for row in frozen["cases"]:
        case = cases[row["id"]]
        active = catalogue_from(case["inputs"], case["graph"])
        rows.append({"id": row["id"], "frozen_reading": row["frozen_reading"],
                     "active_catalogue": evaluate(row, case, active),
                     "oracle_declared_facts": evaluate(row, case, oracle_catalogue(active, row))})
    totals = {
        mode: {"denominator": len(rows),
               "exact_reference_tree": sum(row[mode]["exact_reference_tree"] for row in rows),
               "behavioral_equivalent": sum(row[mode]["behavioral_equivalent"] for row in rows),
               "correct_unresolved": sum(row[mode]["correct_unresolved"] for row in rows),
               "stages": dict(Counter(row[mode]["stage"] for row in rows))}
        for mode in ("active_catalogue", "oracle_declared_facts")
    }
    args.output.write_text(json.dumps({
        "totals": totals, "cases": rows,
        "limitations": [
            "Development data only. No drafting model is called.",
            "The author translated frozen readings to slots; no independent review.",
            "Oracle-declared facts are proposed data. They are not new plan computations or approved production bindings.",
            "64 generated fact worlds test compiled behavior; they do not establish natural-language correctness.",
            "The pre-existing fixture scope remains assumed. Broader applicability discovery is unmeasured.",
        ]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
