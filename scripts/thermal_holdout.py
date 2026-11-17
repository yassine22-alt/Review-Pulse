"""Run live drafting and a separate human-interpreted execution ceiling."""
import argparse
import json
import time
from collections import Counter
from pathlib import Path

from real_interpreter_holdout import bundle, read
from score_interpreter_holdout import approve, totals

from reviewpulse.interpreter.checked import checked_draft
from reviewpulse.interpreter.evidence import EvidenceEntry, apply_evidence
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Inputs
from reviewpulse.interpreter.units import UnitError, convert
from reviewpulse.xeval.drafters import BoundedOllama


def contexts(source):
    cases = {}
    for zone, band, *cells in source["rows"]:
        for header, cell in zip(source["headers"], cells, strict=True):
            key = f"T{len(cases) + 1:02}"
            scope = f"{source['caption']} | Zone climatique | TGBV"
            text = f"| {scope} | {header} |\n| — | {zone} | {band} | {cell} |"
            cases[key] = bundle(source["document"], key, text, {})
    return cases


def catalogue(labels):
    return Inputs.model_validate({
        "bindings": {name: {"kind": "number", "unit": data[1], "description": data[0]}
                     for name, data in labels["facts"].items()},
        "facts": {"building": {name: {"source": "Declared evidence field"} for name in labels["facts"]}},
        "evidence_locations": {name: data[2] for name, data in labels["facts"].items()},
    })


def evidence(labels, base, plan):
    inputs = apply_evidence(base, [
        EvidenceEntry(entity="building", fact=name, value=value, unit=labels["facts"][name][1],
                      origin="computed", source=f"Synthetic observed worksheet, {name}", trusted=True)
        for name, value in plan["observed"].items()
    ])
    entries = [
        EvidenceEntry(entity="building", fact=name, value=value, unit=labels["facts"][name][1],
                      origin="reviewer-attested", source=source, reviewer=reviewer, trusted=True)
        for name, value, source, reviewer in [
            *((name, value, plan["source"], "Synthetic envelope reviewer")
              for name, value in plan["attested"].items()),
            *((name, value, f"Synthetic conflicting certificate {index}", f"Synthetic reviewer {index}")
              for name, values in plan.get("conflict", {}).items()
              for index, value in enumerate(values, 1)),
        ]
    ]
    return inputs, apply_evidence(inputs, entries)


def reference(context, name, operator, threshold, unit):
    text = context.text
    return {
        "status": "DRAFTED",
        "program": {
            "id": context.target, "title": name, "document": context.document,
            "sources": [{"clause": context.target, "start": 0, "end": len(text), "quote": text}],
            "requirement": {"node": operator, "left": {"node": "fact", "entity": "building", "name": name},
                            "right": {"node": "literal", "value": threshold, "unit": unit}},
        },
    }


def match(program, name, operator, threshold, unit):
    rule = program.model_dump()
    req = rule["requirement"]
    left, right = req.get("left", {}), req.get("right", {})
    op = req["node"]
    if left.get("node") == "literal":
        left, right = right, left
        op = {"ge": "le", "le": "ge"}.get(op, op)
    if (left.get("node"), left.get("entity"), left.get("name"), op) != ("fact", "building", name, operator):
        return False
    if (rule["unresolved"] or rule["not_checked"] or right.get("node") != "literal"
            or rule["applicability"].get("value") is not True or rule["exemption"].get("value") is not False):
        return False
    try:
        return type(right["value"]) in (int, float) and abs(convert(right["value"], right["unit"], unit) - threshold) < 1e-9
    except UnitError:
        return False


def run(program, inputs):
    if program is None:
        return {"outcome": "UNRESOLVED", "blocker": "interpretation"}
    result = run_program(program, inputs)
    return {"outcome": result["outcome"], "evidence_requests": result.get("evidence_requests", []),
            "fact_provenance": result.get("fact_provenance", []),
            "blocker": "missing evidence" if result["outcome"] == "UNRESOLVED" else None}


def score(labels, cases, base, drafts):
    rows = []
    plans = {zone: evidence(labels, base, plan) for zone, plan in labels["plans"].items()}
    for key, zone, name, op, threshold, truth in labels["clauses"]:
        unit = labels["facts"][name][1]
        context, draft = cases[key], drafts[key]
        require, issue = approve(reference(context, name, op, threshold, unit), context, base)
        if require is None:
            raise ValueError(f"{key}: {issue}")
        program, why = approve(draft, context, base)
        correct = program is not None and match(program, name, op, threshold, unit)
        initial, reviewed = plans[zone]
        rows.append({
            "id": key, "zone": zone, "gold": truth, "draft_correct": correct,
            "draft_approvable": program is not None, "draft_reason": why,
            "reference": f"{name} {op} {threshold} {unit}", "draft": draft.get("readback"),
            "automatic": run(program if correct else None, initial),
            "reviewed": run(program if correct else None, reviewed),
            "as_is_automatic": run(program, initial), "as_is_reviewed": run(program, reviewed),
            "ceiling_automatic": run(require, initial), "ceiling_reviewed": run(require, reviewed),
        })
    metrics = {stage: totals([{"gold": row["gold"], "outcome": row[stage]["outcome"]} for row in rows])
               for stage in ("automatic", "reviewed", "as_is_automatic", "as_is_reviewed",
                             "ceiling_automatic", "ceiling_reviewed")}
    metrics["reviewed_blockers"] = dict(Counter(row["reviewed"]["blocker"] for row in rows if row["reviewed"]["blocker"]))
    metrics["drafted_correct"] = sum(row["draft_correct"] for row in rows)
    metrics["executable_with_declared_numeric_facts_and_selected_scope"] = len(rows)
    return {"metrics": metrics, "obligations": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("draft", "score"))
    parser.add_argument("drafts", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--model", default="qwen2.5:1.5b")
    args = parser.parse_args()
    reports = Path(__file__).resolve().parents[1] / "reports"
    labels = read(reports / "thermal-holdout-labels.json")
    cases = contexts(read(reports / "thermal-holdout-source.json"))
    base = catalogue(labels)
    if args.mode == "score":
        drafts = {row["id"]: row for row in map(json.loads, args.drafts.read_text(encoding="utf-8").splitlines())}
        args.report.write_text(json.dumps(score(labels, cases, base, drafts), ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        return
    client = BoundedOllama(model=args.model, num_predict=384, timeout_s=90)
    if not client.available():
        raise SystemExit(f"Local model unavailable: {args.model}")
    with args.drafts.open("x", encoding="utf-8") as stream:
        for key, context in cases.items():
            start = time.perf_counter()
            try:
                result = checked_draft(context, base, None, client, triage=True)
            except Exception as error:
                result = {"status": "ERROR", "reason": f"{type(error).__name__}: {error}"}
            record = {"id": key, "seconds": round(time.perf_counter() - start, 1), **result}
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            print(key, record["status"], record["seconds"], flush=True)


if __name__ == "__main__":
    main()
