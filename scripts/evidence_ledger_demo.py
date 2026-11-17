"""Exercise five development obligations using scoped, synthetic source evidence."""
import json
from pathlib import Path

from real_interpreter_holdout import read

from reviewpulse.interpreter.evidence import EvidenceEntry, apply_evidence
from reviewpulse.interpreter.findings import to_findings
from reviewpulse.interpreter.schema import Inputs, Program
from reviewpulse.xeval.expr_ir import parse_expression

# Bindings and meanings here are benchmark fixture data, never production prompts.
CASES = {
    "M12": ("building.transparent and not building.red and not building.orange", "Glazing schedule, tested door",
            {"building": {"transparent": True, "red": True, "orange": False}}),
    "M13": ("not (building.sliding and not building.motorized)", "Public evacuation exit door schedule",
            {"building": {"sliding": True, "motorized": False}}),
    "M16": ("building.opens_by_push or building.device_per_leaf", "Internal release test with public present",
            {"building": {"opens_by_push": False, "device_per_leaf": False}}),
    "A13": ("building.left_rail and building.right_rail", "Field survey of the relevant passage",
            {"building": {"left_rail": True, "right_rail": False}}),
    "A15": ("forall entrances e: e.accessible_phone", "Entrance-tagged accessible phone inventory",
            {"east": {"accessible_phone": True}, "west": {"accessible_phone": True}}),
}


def run():
    repo = Path(__file__).resolve().parents[1]
    labels = {row["id"]: row for name in ("morocco", "accessibility")
              for row in read(repo / f"reports/{name}-holdout-labels.json")["clauses"]}
    results = []
    for key, (expr, citation, observations) in CASES.items():
        label = labels[key]
        condition = parse_expression(expr, {"building"})
        meaning = label["meaning"]
        rule = Program.model_validate({
            "id": key, "title": meaning, "status": "approved", "approved_by": "Benchmark author",
            "document": "Morocco development fixture",
            "sources": [{"clause": label["ref"], "start": 0, "end": len(meaning), "quote": meaning}],
            "requirement": condition,
        })
        names = {name for facts in observations.values() for name in facts}
        inputs = Inputs.model_validate({
            "bindings": {name: {"kind": "boolean", "description": name.replace("_", " ")} for name in names},
            "evidence_locations": {name: citation for name in names},
            "collections": {"entrances": {"items": list(observations), "complete": True, "trusted": True}}
            if key == "A15" else {},
        })
        entries = [
            EvidenceEntry(entity=entity, fact=name, value=value, origin="reviewer-attested",
                          reviewer="Synthetic reviewer", source=f"{citation}, {entity}", trusted=True)
            for entity, facts in observations.items() for name, value in facts.items()
        ]
        base, initial = to_findings(rule, inputs, None)
        filled, reviewed = to_findings(rule, apply_evidence(inputs, entries), None)
        truth = label["truth"]
        if isinstance(truth, list):
            truth = {"PASS": "SATISFIED", "FAIL": "VIOLATED"}[truth[1]]
        assert initial.outcome == "UNRESOLVED" and reviewed.outcome == truth
        results.append({"id": key, "fixture_truth": truth, "initial": initial.outcome, "reviewed": reviewed.outcome,
                        "requests": base[0].evidence["evidence_requests"],
                        "provenance": filled[0].evidence["fact_provenance"]})
    return results


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
