"""Evaluate source-locked frames and header-only linking; no plan or gold is sent."""
import argparse
import json
from collections import Counter
from pathlib import Path

from development_cases import load_cases
from run_slot_pilot import request_for
from score_free_drafting import meaning

from reviewpulse.interpreter.schema import Program
from reviewpulse.interpreter.table_rows import compile_table, fact_request, parse_table_row
from reviewpulse.llm.openai_compat import APIUnavailable, OpenAICompatClient
from reviewpulse.llm.result_cache import ResultCache, exclusive_run, fingerprint
from reviewpulse.xeval.slot_scoring import fields


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--hosted", action="store_true")
    parser.add_argument("--max-calls", type=int, default=4)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    cases = load_cases(repo, args.access_text)
    numeric = set(json.loads((repo / "reports/assisted-numeric-selection.json").read_text(encoding="utf-8"))["ids"])
    gold = {r["id"]: r for r in json.loads((repo / "reports/development-oracle-slots.json").read_text(encoding="utf-8"))["cases"]}
    annotations = {r["id"]: r for r in json.loads((repo / "reports/development-metadata-labels.json").read_text(encoding="utf-8"))["cases"]}
    rows, requests = [], {}
    for case in cases:
        catalogue = request_for(case, "structured")[3]
        frame = parse_table_row(case["context"], catalogue)
        row = {"id": case["id"], "numeric": case["id"] in numeric, "suite": case["suite"],
               "source": case["context"].text, "frame": frame, "status": "NEEDS_REVIEW", "retained": False}
        if annotations[case["id"]]["annotated"]:
            row["scope_matches_frozen"] = fields({"metadata_applicability": frame["metadata_applicability"]})["applicability"] == fields(
                {"metadata_applicability": annotations[case["id"]]["conditions"]})["applicability"]
        if frame["kind"] == "table" and not frame["blockers"]:
            system, payload, schema = fact_request(frame, catalogue)
            key = fingerprint({"model": "openai/gpt-oss-120b", "system": system, "payload": payload,
                               "schema": schema, "mode": "json_schema", "max_tokens": 256, "temperature": 0})
            body_bytes = len(json.dumps({"system": system, "payload": payload, "schema": schema}, ensure_ascii=False).encode())
            requests.setdefault(key, {"system": system, "payload": payload, "schema": schema,
                "request_bytes": body_bytes, "input_token_estimate": [body_bytes // 4, (body_bytes + 1) // 2], "completion_cap": 256})
            row["request_key"] = key
            row["status"] = "AWAITING_FACT_SELECTION"
        if not row["numeric"]:
            row["status"] = "NOT_NUMERIC"
        rows.append(row)
    report = {"date": "2026-11-19", "model": "openai/gpt-oss-120b", "status": "OFFLINE_PLAN",
        "limits": ["Development only, author/assistant grades lack independent review.",
            "Frames parse table values and scope; prose remains an explicit manual-composition task.",
            "No gold, row threshold, plan value or drawing enters header-only linking.",
            "Header choices are cached across rows, without zone/threshold-specific prompts.",
            "Byte token estimates are not tokenizer measurements; provider usage is measured on successful calls."],
        "numeric_denominator": len(numeric), "all_obligations": len(rows), "unique_header_calls": len(requests),
        "cost": {"input_token_estimate": [sum(r["input_token_estimate"][i] for r in requests.values()) for i in (0, 1)],
                 "completion_cap_total": 256 * len(requests), "daily_limit": 200000},
        "requests": requests, "http_events": [], "rows": rows}
    cache = ResultCache(repo / "data/llm_cache/header-linking")
    client = None
    if args.hosted:
        try:
            client = OpenAICompatClient.from_env("https://api.groq.com/openai/v1", "GROQ_API_KEY_Reviewpulse", report["model"],
                provider="groq", structured="json_schema", seed=None, max_tokens=256, max_retries=2, rpm=10, tpm=8000)
        except APIUnavailable as error:
            report.update(status="API_UNAVAILABLE", api_reason=error.reason)
    remaining = args.max_calls
    stopped = False
    with exclusive_run(args.output):
        for key, request in requests.items():
            saved = cache.get(key)
            if saved:
                request["response"] = saved["raw"]
                request["usage"] = saved["usage"]
                request["cached"] = True
            elif client and not stopped and remaining:
                remaining -= 1
                try:
                    raw = client.complete(request["system"], json.dumps(request["payload"], ensure_ascii=False), request["schema"])
                    saved = {"status": "COMPLETE", "raw": raw, "usage": {k: v for k, v in client.last.items() if k != "text"}}
                    cache.put(key, saved)
                    request.update(response=raw, usage=saved["usage"], cached=False)
                except APIUnavailable as error:
                    request.update(status="REQUEST_REJECTED" if error.http_status in (400, 422) else "API_UNAVAILABLE", reason=error.reason, http_status=error.http_status)
                    if error.http_status not in (400, 422):
                        report["status"] = "API_UNAVAILABLE"
                        stopped = True
                except ValueError as error:
                    request.update(status="GENERATION_FAILURE", reason=type(error).__name__)
                print("header", len([r for r in requests.values() if "response" in r]), "/", len(requests), flush=True)
            for row in [r for r in rows if r.get("request_key") == key]:
                if "response" not in request:
                    continue
                row["linker_proposal"] = request["response"]
                case = next(c for c in cases if c["id"] == row["id"])
                catalogue = request_for(case, "structured")[3]
                try:
                    program, slots = compile_table(row["frame"], request["response"], case["context"], catalogue)
                    reference = Program(id=row["id"], title="reference", document=case["context"].document,
                        requirement=gold[row["id"]]["reference_expression"], sources=program.sources,
                        metadata_applicability=[{**condition, "source": program.sources[0]} for condition in annotations[row["id"]]["conditions"]])
                    matched = meaning(program, row["id"], annotations[row["id"]]) == meaning(reference, row["id"], annotations[row["id"]])
                    row.update(status="VALIDATED_CANDIDATE", retained=True, slots=slots,
                               matches_reference=matched, approved=False, program=program.model_dump(mode="json"))
                except ValueError as error:
                    row.update(status="NEEDS_REVIEW", stage=getattr(error, "stage", "validation"), reason=str(error))
            report["http_events"] = client.events if client else []
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["summary"] = {"statuses": dict(Counter(row["status"] for row in rows)),
            "scope_exact": [sum(r.get("scope_matches_frozen", False) for r in rows), 15],
            "retained": [sum(r["retained"] for r in rows), len(numeric)],
            "reference_matches": [sum(r.get("matches_reference", False) for r in rows), len(numeric)]}
        if args.hosted and report["status"] != "API_UNAVAILABLE":
            report["status"] = "HEADER_LINKING_COMPLETE" if all("response" in r for r in requests.values()) else "PARTIAL"
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "unique_header_calls", "cost", "summary")}))


if __name__ == "__main__":
    main()
