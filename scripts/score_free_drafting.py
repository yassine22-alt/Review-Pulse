"""Revalidate saved outputs under one final gate and compare to frozen development IR."""
import argparse
import json
from collections import Counter
from pathlib import Path

from development_cases import load_cases
from run_slot_pilot import compile_response, request_for

from reviewpulse.interpreter.agreement import agreement_gate, semantic_key
from reviewpulse.interpreter.decomposed import ExpressionFrame
from reviewpulse.interpreter.schema import MetadataCondition, Program, Span
from reviewpulse.interpreter.structured import SlotDraft
from reviewpulse.xeval.expr_ir import SYMBOL, ExprError, tokenize
from reviewpulse.xeval.flat import FlatProgram, compile_flat
from reviewpulse.xeval.slot_scoring import flat_nodes, quantity, score_slots, totals


def meaning(program, target, annotation):
    data = program.model_dump()
    data.update(sources=[{"clause": target, "start": 0, "end": 1, "quote": "x"}], fact_declarations=[])
    if not annotation["annotated"]:
        data["metadata_applicability"] = []
    for condition in data["metadata_applicability"]:
        condition["source"] = data["sources"][0]
    return semantic_key(Program.model_validate(data))


def lexical_diagnostics(raw, gold, catalogue):
    """Lexing is independent of expression parsing; these are mentions, not bound-slot accuracy."""
    if isinstance(raw.get("nodes"), list):
        return {"lexable": None, "note": "Node-slot outputs are scored directly before compilation; expression lexing does not apply."}
    try:
        tokens = [token for field in ("require", "applies_when", "unless")
                  for token in tokenize(raw.get(field) or "true")]
    except ValueError:
        return {"lexable": False}
    expected = flat_nodes(gold["slots"])
    facts = {node["name"] for node in expected if node.get("op") == "fact"}
    predicted_facts = {value for kind, value, _ in tokens if kind == "id" and value in catalogue["bindings"]}
    numbers = {quantity(node)[0] for node in expected if node.get("op") == "literal" and type(node.get("value")) in (int, float)}
    predicted_numbers = {quantity({"value": float(value), "unit": unit or "1"})[0]
                         for kind, value, unit in tokens if kind == "num"}
    expected_ops = {node["op"] for node in expected if node.get("op") in ("ge", "gt", "le", "lt", "eq", "ne")}
    operator_for = {symbol: name for name, symbol in SYMBOL.items() if name in ("ge", "gt", "le", "lt", "eq", "ne")}
    predicted_ops = {operator_for[value] for _, value, _ in tokens if value in operator_for}
    return {"lexable": True, "fact_names": [predicted_facts == facts, bool(facts)],
            "number_values": [predicted_numbers == numbers, bool(numbers)],
            "comparators": [predicted_ops == expected_ops, bool(expected_ops)],
            "units_explicit": sum(kind == "num" and unit is not None for kind, _, unit in tokens),
            "note": "No ownership, association or applicability correctness is established by these lexical matches."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    cases = {case["id"]: case for case in load_cases(repo, args.access_text)}
    gold = {row["id"]: row for row in json.loads((repo / "reports/development-oracle-slots.json").read_text(encoding="utf-8"))["cases"]}
    annotations = {row["id"]: row for row in json.loads((repo / "reports/development-metadata-labels.json").read_text(encoding="utf-8"))["cases"]}
    output = {"limits": ["Development data only; labels have no independent review.",
        "Matches mean normalized frozen fixture IR, not a claim about legal meaning outside its assumed scope.",
        "31/46 scopes have no supplemental gold annotation and cannot be scored as correct.",
        "Expression field scores require parseable structure. Bare fact mentions do not prove correct ownership or binding.",
        "Field mismatch counts below are an edit-family proxy, not observed reviewer edit effort or time.",
        "Subject and clause-span exact agreement can undercredit a correct noun phrase or shorter grounded citation; they are annotation agreement, not independent semantic accuracy.",
        "All retained nonmatches require explicit author adjudication; they are not automatically called wrong or correct.",
        "Saved drafts were revalidated with final UTF-8 cue data after tests caught and corrected a temporary encoding error; no responses were regenerated."],
        "models": {}, "agreement": {}}
    pairs = {}
    for path in args.inputs:
        run = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for original in run["rows"]:
            row = {**original, "model": run["model"]}
            key = row["id"]
            row.update(frozen_interpretation=gold[key]["frozen_reading"], frozen_requirement=gold[key]["reference_expression"],
                       scope_annotated=annotations[key]["annotated"])
            if "raw" not in row:
                row["grade"] = "NOT_SCORED_API_OR_BUDGET" if row["status"] != "GENERATION_FAILURE" else "INCOMPLETE_OUTPUT"
                rows.append(row)
                continue
            row["slots"] = score_slots(row["raw"], gold[key], annotations[key])
            _, _, _, catalogue = request_for(cases[key], "original_expression")
            row["lexical_diagnostics"] = lexical_diagnostics(row["raw"], gold[key], catalogue)
            row["edit_family_proxy"] = [name for name, score in row["slots"].items() if score["eligible"] and not score["exact"]]
            row["retained"] = False
            case = cases[key]
            contract = row.get("representation", "original_expression")
            try:
                (SlotDraft if contract == "structured" else ExpressionFrame).model_validate(row["raw"])
                _, _, _, catalogue = request_for(case, contract)
                program = compile_response(row["raw"], case, catalogue, contract)
                row.update(retained=True, stage="retained", program=program.model_dump(mode="json"))
                reference = Program.model_validate(compile_flat(FlatProgram.model_validate({
                    name: value for name, value in gold[key]["slots"].items() if name in FlatProgram.model_fields}), case["context"].document))
                reference.metadata_applicability = [MetadataCondition.model_validate({**condition,
                    "source": Span(clause=key, start=0, end=1, quote="x")}) for condition in annotations[key]["conditions"]]
                matched = meaning(program, key, annotations[key]) == meaning(reference, key, annotations[key])
                row["grade"] = "MATCHES_FROZEN_IR" if matched else "APPROVABLE_REQUIRES_AUTHOR_ADJUDICATION"
            except ValueError as error:
                row.update(stage=getattr(error, "stage", "expression_parse" if isinstance(error, ExprError) else "schema_or_compile"), detail=str(error))
                row["grade"] = ("CORRECTLY_NEEDS_REVIEW" if gold[key]["specialist_or_context_gap"] and row["raw"].get("unresolved")
                                else "PARTLY_MATCHES" if any(score["exact"] for name, score in row["slots"].items() if name not in ("subject", "clause_span")) else "NOT_MATCHED")
                row.pop("program", None)
            pairs[(run["model"], row["arm"], key)] = row
            rows.append(row)
        for key in cases:
            for arm in run["protocol"]["arms"]:
                if not any(row["id"] == key and row["arm"] == arm for row in rows):
                    rows.append({"id": key, "arm": arm, "model": run["model"], "status": "NOT_ATTEMPTED", "stage": "pending",
                                 "grade": "NOT_SCORED_PENDING", "frozen_interpretation": gold[key]["frozen_reading"]})
        summary = {}
        for arm in sorted({row["arm"] for row in rows}):
            selected = [row for row in rows if row["arm"] == arm]
            complete = [row for row in selected if "raw" in row]
            retained = [row for row in complete if row["retained"]]
            matches = [row for row in retained if row["grade"] == "MATCHES_FROZEN_IR"]
            summary[arm] = {"complete_json_outputs": [len(complete), 46], "retained": [len(retained), len(complete)],
                "matched_frozen_ir": [len(matches), len(complete)], "approvable_total": len(retained),
                "wrong_approvable_reviewed": [0, len(matches)], "unadjudicated_approvable": len(retained) - len(matches),
                "grades": dict(Counter(row["grade"] for row in selected)), "stages": dict(Counter(row["stage"] for row in selected)),
                "slots": totals([row["slots"] for row in complete]),
                "raw_lexical_agreement": {name: [sum(row["lexical_diagnostics"].get(name, [False, False])[0]
                    for row in complete if row["lexical_diagnostics"].get(name, [False, False])[1]),
                    sum(row["lexical_diagnostics"].get(name, [False, False])[1] for row in complete)]
                    for name in ("fact_names", "number_values", "comparators")},
                "api_failures": sum(row["status"] in ("API_UNAVAILABLE", "REQUEST_REJECTED") for row in selected),
                "budget_deferred": sum(row["status"] == "BUDGET_DEFERRED" for row in selected),
                "not_attempted": sum(row["status"] == "NOT_ATTEMPTED" for row in selected)}
        output["models"][run["model"]] = {"summary": summary, "rows": rows, "tokens": run["daily_tokens"],
            "http_attempts": dict(Counter(str(event["http_status"]) for event in run["requests"])),
            "batches_of_ten_http_attempts": [{"attempts": len(run["requests"][start:start+10]),
                "non_200": sum(event["http_status"] != 200 for event in run["requests"][start:start+10])}
                for start in range(0, len(run["requests"]), 10)]}
    models = list(output["models"])
    if len(models) == 2:
        for arm in ("monolithic", "decomposed"):
            records = []
            for key in cases:
                left, right = (pairs.get((model, arm, key)) for model in models)
                if left is None or right is None:
                    records.append({"id": key, "status": "PENDING_PAIRED_OUTPUT"})
                else:
                    result = agreement_gate(left, right)
                    records.append({"id": key, "status": result["status"], "reason": result["reason"],
                                    "left_grade": left["grade"], "right_grade": right["grade"],
                                    "proposals": [left["raw"], right["raw"]]})
            paired = [row for row in records if row["status"] != "PENDING_PAIRED_OUTPUT"]
            candidates = [row for row in paired if row["status"] == "CANDIDATE"]
            matched = [row for row in candidates if row["left_grade"] == row["right_grade"] == "MATCHES_FROZEN_IR"]
            output["agreement"][arm] = {"paired_outputs": [len(paired), 46], "candidates": [len(candidates), len(paired)],
                "abstentions": [len(paired) - len(candidates), len(paired)], "pending": 46 - len(paired),
                "wrong_candidates_reviewed": [0, len(matched)], "unadjudicated_candidates": len(candidates) - len(matched),
                "rows": records}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({model: {arm: {name: value for name, value in summary.items() if name not in ("slots", "raw_lexical_agreement")}
                              for arm, summary in data["summary"].items()} for model, data in output["models"].items()}))


if __name__ == "__main__":
    main()
