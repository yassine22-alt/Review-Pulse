"""Resumable development-only hosted comparison. Never accepts drawing input."""
import argparse
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from development_cases import load_cases
from run_slot_pilot import compile_response, request_for

from reviewpulse.interpreter.checked import catalogue_from
from reviewpulse.interpreter.decomposed import (
    ExpressionFrame,
    formal_request,
    reading_request,
    schema_contract,
)
from reviewpulse.interpreter.deterministic import compile_links, link_request
from reviewpulse.interpreter.structured import SlotDraft
from reviewpulse.llm.openai_compat import APIUnavailable, OpenAICompatClient
from reviewpulse.llm.result_cache import ResultCache, fingerprint
from reviewpulse.xeval.slot_scoring import score_slots, totals


def compact(value):
    if isinstance(value, dict):
        return {key: ({name: compact(spec) for name, spec in item.items()} if key == "properties" else compact(item))
                for key, item in value.items() if key not in ("title", "description", "default", "examples")}
    return [compact(item) for item in value] if isinstance(value, list) else value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--arms", nargs="+", default=["monolithic", "decomposed"])
    parser.add_argument("--budget", type=int, default=200)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    protocol = json.loads((args.protocol or repo / "reports/free-drafting-protocol.json").read_text(encoding="utf-8"))
    if args.model not in protocol["models"]:
        raise ValueError("model not approved in frozen protocol")
    client = OpenAICompatClient.from_env("https://api.groq.com/openai/v1", "GROQ_API_KEY_Reviewpulse",
        args.model, provider="groq", structured="json_schema" if args.arms == ["deterministic"] else "json_object", max_retries=2, rpm=15,
        max_tokens=protocol["formal_tokens"], seed=None, reasoning_effort="low", concurrency=1, tpm=protocol["console_limits"]["tpm"])
    cache = ResultCache(repo / "data/llm_cache/free-drafting")
    report = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else {
        "protocol": protocol, "model": args.model, "rows": [], "requests": [], "daily_tokens": {}}
    if report["protocol"] != protocol or report["model"] != args.model:
        raise ValueError("changed protocol; use a new report")
    cases = load_cases(repo, args.access_text)
    gold = {row["id"]: row for row in json.loads((repo / "reports/development-oracle-slots.json").read_text(encoding="utf-8"))["cases"]}
    scopes = {row["id"]: row for row in json.loads((repo / "reports/development-metadata-labels.json").read_text(encoding="utf-8"))["cases"]}
    day = datetime.now(UTC).date().isoformat()
    remaining = args.budget
    prior_tokens = 0
    for other in (repo / "reports").glob("free-*.json"):
        if other.resolve() == args.output.resolve():
            continue
        try:
            previous = json.loads(other.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise RuntimeError("Cannot establish shared model budget; wait for the other report write") from None
        if previous.get("model") == args.model:
            if previous.get("status") == "RUNNING":
                raise RuntimeError("Another run of this model is active; do not spend its quota concurrently")
            prior_tokens += previous.get("daily_tokens", {}).get(day, 0)

    def save(status):
        report["status"] = status
        report["summary"] = {}
        for arm in args.arms:
            rows = [row for row in report["rows"] if row["arm"] == arm]
            completed = [row for row in rows if row["status"] == "EVALUATED"]
            report["summary"][arm] = {"complete": [len(completed), len(cases)],
                "api_unavailable": len([row for row in rows if row["status"] == "API_UNAVAILABLE"]),
                "retained": [sum(row.get("retained", False) for row in completed), len(completed)],
                "stages": dict(Counter(row["stage"] for row in rows)),
                "slots": totals([row["slots"] for row in completed])}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, args.output)

    def call(system, payload, schema, tokens):
        nonlocal remaining
        key = fingerprint({"model": args.model, "system": system, "payload": payload,
                           "schema": schema, "max_tokens": tokens, "temperature": 0, "reasoning": "low"})
        cached = cache.get(key)
        if cached is not None:
            return cached["raw"]
        if remaining <= 0 or prior_tokens + report["daily_tokens"].get(day, 0) >= protocol["daily_token_budget"]:
            raise APIUnavailable("INVOCATION_OR_DAILY_BUDGET", None, 0)
        remaining -= 1
        client.max_tokens = tokens
        before = len(client.events)
        try:
            raw = client.complete(system, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), schema)
            cache.put(key, {"status": "COMPLETE", "raw": raw, "usage": client.last})
            return raw
        finally:
            report["requests"].extend(client.events[before:])
            report["daily_tokens"][day] = report["daily_tokens"].get(day, 0) + sum(
                client.last.get(name) or 0 for name in ("prompt_tokens", "completion_tokens"))
            save("RUNNING")

    cases.sort(key=lambda case: protocol["order"].index(case["id"]))
    rejected_in_row = 0
    for case in cases:
        for arm in args.arms:
            if any(row["id"] == case["id"] and row["arm"] == arm and row["status"] not in ("API_UNAVAILABLE", "BUDGET_DEFERRED")
                   for row in report["rows"]):
                continue
            row = {"id": case["id"], "arm": arm, "retained": False}
            try:
                if arm == "deterministic":
                    catalogue = catalogue_from(case["inputs"], case["graph"])
                    system, payload, schema = link_request(case["context"], catalogue)
                    row["evidence_frame"] = payload
                    closed = call(system, payload, schema, protocol["formal_tokens"])
                    row.update(closed_proposal=closed, status="EVALUATED", raw={})
                    try:
                        program, slots = compile_links(closed, payload, case["context"], catalogue)
                        row.update(raw=slots, retained=True, stage="retained", program=program.model_dump(mode="json"))
                    except ValueError as error:
                        row.update(stage=getattr(error, "stage", "schema_or_compile"), detail=str(error))
                    row["slots"] = score_slots(row["raw"], gold[case["id"]], scopes[case["id"]], subject_requested=False)
                    report["rows"] = [old for old in report["rows"] if (old["id"], old["arm"]) != (case["id"], arm)] + [row]
                    save("RUNNING")
                    print(case["id"], arm, row["stage"], flush=True)
                    continue
                contract = protocol.get("contract", "original_expression")
                row["representation"] = contract
                system, payload, schema, catalogue = request_for(case, contract)
                schema = compact(schema_contract(schema))
                reading = None
                if arm == "decomposed":
                    read_system, read_payload, read_schema = reading_request(case["context"])
                    reading = call(read_system, read_payload, read_schema, protocol["reading_tokens"])
                    row["reading"] = reading
                elif arm != "monolithic":
                    raise ValueError("unsupported arm")
                raw = call(system, formal_request(case["context"], payload, reading), schema, protocol["formal_tokens"])
                row.update(raw=raw, call={key: value for key, value in client.last.items() if key != "text"}, status="EVALUATED", slots=score_slots(raw, gold[case["id"]], scopes[case["id"]]))
                try:
                    (SlotDraft if contract == "structured" else ExpressionFrame).model_validate(raw)
                    program = compile_response(raw, case, catalogue, contract)
                    row.update(stage="retained", retained=True, program=program.model_dump(mode="json"))
                except ValueError as error:
                    row.update(stage=getattr(error, "stage", "schema_or_compile"), detail=str(error))
            except APIUnavailable as error:
                row.update(status=("BUDGET_DEFERRED" if error.reason == "INVOCATION_OR_DAILY_BUDGET" else
                                   "REQUEST_REJECTED" if error.http_status in (400, 422) else "API_UNAVAILABLE"),
                           stage="budget" if error.reason == "INVOCATION_OR_DAILY_BUDGET" else "transport",
                           reason=error.reason, http_status=error.http_status)
            except (ValueError, RuntimeError) as error:
                row.update(status="GENERATION_FAILURE", stage="generation", reason=type(error).__name__,
                           raw_text=client.last.get("text", ""))
            report["rows"] = [old for old in report["rows"] if (old["id"], old["arm"]) != (case["id"], arm)] + [row]
            rejected_in_row = rejected_in_row + 1 if row["status"] == "REQUEST_REJECTED" else 0
            save("RUNNING")
            print(case["id"], arm, row["status"], row["stage"], flush=True)
            if row["status"] in ("API_UNAVAILABLE", "BUDGET_DEFERRED") or rejected_in_row >= 3:
                save(row["status"])
                return
    save("COMPLETE")


if __name__ == "__main__":
    main()
