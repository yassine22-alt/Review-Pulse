"""Paired development rerun; cached table model choices, closed-menu-only new calls."""
import argparse
import json
from collections import Counter
from pathlib import Path

from development_cases import load_cases
from run_slot_pilot import request_for

from reviewpulse.interpreter.assisted import classify_scope, compile_assisted
from reviewpulse.interpreter.table_rows import fact_request
from reviewpulse.llm.openai_compat import APIUnavailable, OpenAICompatClient
from reviewpulse.llm.result_cache import ResultCache, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--hosted", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    def read(name):
        return json.loads((repo / name).read_text(encoding="utf-8"))
    baseline = {r["id"]: r for r in read("reports/assisted-numeric-minimal-results.json")["rows"]}
    labels = read("reports/assisted-product-scope-labels.json")["labels"]
    numeric = set(read("reports/assisted-numeric-selection.json")["ids"])
    rows = []
    client = None
    cache = ResultCache(repo / "data/llm_cache/assisted-product")
    for case in load_cases(repo, args.access_text):
        key = case["id"]
        cat = request_for(case, "structured")[3]
        scope = classify_scope(case["context"], cat)
        row = {"id": key, "source": case["context"].text, "numeric": key in numeric, "scope": scope,
               "reference_scope": labels[key], "status": "REVIEWER_FORMALIZATION", "retained": False,
               "edit_bucket": "rewrite"}
        if (scope["frame"] and len(scope["frame"]["measurements"]) == 1
                and scope["frame"]["measurements"][0]["operator"] is not None
                and scope["frame"]["metadata_applicability"] and scope["frame"]["blockers"]
                and all(b["reason"] in ("missing_comparator_or_header_unit", "unparsed_value_or_qualifier") for b in scope["frame"]["blockers"])):
            row["edit_bucket"] = "missing_context"
        if scope["in_scope"]:
            system, payload, schema = fact_request(scope["frame"], cat)
            available = any(h["candidates"] for h in payload["headers"])
            raw = baseline[key].get("linker_proposal") if scope["family"] == "table-row" else None
            if raw is not None:
                row["selection_origin"] = "Previously measured identical table-header closed choice"
            elif not available:
                row["blocker"] = "vocabulary_gap"
            elif args.hosted:
                if client is None:
                    client = OpenAICompatClient.from_env("https://api.groq.com/openai/v1", "GROQ_API_KEY_Reviewpulse",
                        "openai/gpt-oss-120b", provider="groq", structured="json_schema", seed=None, max_tokens=256, rpm=10, tpm=8000)
                request_key = fingerprint({"model": client.model, "system": system, "payload": payload, "schema": schema})
                saved = cache.get(request_key)
                try:
                    raw = saved["raw"] if saved else client.complete(system, json.dumps(payload, ensure_ascii=False), schema)
                    if not saved:
                        cache.put(request_key, {"raw": raw, "status": "COMPLETE"})
                except APIUnavailable as error:
                    row.update(status="API_UNAVAILABLE", blocker=error.reason)
            else:
                row["blocker"] = "closed_fact_choice_not_run"
            if raw is not None:
                row["raw"] = raw
                try:
                    program, slots = compile_assisted(scope, raw, case["context"], cat)
                    row.update(status="CANDIDATE", retained=True, program=program.model_dump(mode="json"), slots=slots,
                               edit_bucket="0" if baseline[key].get("matches_reference") and scope["family"] == "table-row" else "needs_source_adjudication")
                    row["source_review"] = "Unchanged table frame/source and validated fact choice; reuse previous assistant adjudication" if row["edit_bucket"] == "0" else "Pending direct assistant source review"
                except ValueError as error:
                    row.update(blocker=str(error), stage=getattr(error, "stage", "validation"))
        rows.append(row)
    numeric_rows = [r for r in rows if r["numeric"]]
    outscope = [r for r in rows if not r["reference_scope"]["in_scope"]]
    report = {"development_only": True, "baseline_commit": "3f6ada20", "unchanged_baseline": {"fully_correct": [12,36],"one_edit":[0,36],"more_edits":[0,36],"rewrite":[21,36],"missing_context":[3,36]},
        "after": {bucket: [sum(r["edit_bucket"] == bucket for r in numeric_rows),36] for bucket in ("0","1","2+","rewrite","missing_context","needs_source_adjudication")},
        "scope": {"out_of_scope_wrongly_drafted": [sum(r["retained"] for r in outscope),len(outscope)],
                  "out_of_scope_predicted_in_scope": [sum(r["scope"]["in_scope"] for r in outscope),len(outscope)],
                  "out_of_scope_sent_to_queue": [sum(not r["retained"] for r in outscope),len(outscope)],
                  "families": dict(Counter(r["scope"]["family"] for r in rows))},
        "source_wrong_approvable": [sum(r["retained"] and r["edit_bucket"] != "0" for r in rows), sum(r["retained"] for r in rows)],
        "new_hosted_calls": len(client.events) if client else 0, "rows": rows,
        "limits": ["Assistant labels and source reviews, no independent review.","No accuracy gain if whole source correctness has not been reviewed.","No test of plan verdict accuracy; missing evidence remains unresolved."]}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))


if __name__ == "__main__":
    main()
