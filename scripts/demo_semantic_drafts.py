"""Actual text-only semantic drafts for an explicitly assisted walkthrough."""
import argparse
import json
from pathlib import Path

from real_interpreter_holdout import bundle

from reviewpulse.interpreter.decomposed import reading_request
from reviewpulse.llm.openai_compat import APIUnavailable, LLMError, OpenAICompatClient
from reviewpulse.llm.result_cache import ResultCache, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    requests = []
    for row in profile["requirements"]:
        context = bundle(profile["source_kind"], row["id"], row["text"], row.get("context", {}))
        system, payload, schema = reading_request(context)
        size = len(json.dumps({"system": system, "payload": payload, "schema": schema}, ensure_ascii=False).encode())
        requests.append((row["id"], system, payload, schema, size))
    report = {"source": profile["source"], "contract": "Source-only neutral semantic reading, not executable slots",
        "model": "openai/gpt-oss-120b", "rows": [], "http_events": [],
        "estimated_input_tokens": [sum(r[4] // 4 for r in requests), sum((r[4] + 1) // 2 for r in requests)],
        "output_cap_total": 768 * len(requests), "status": "OFFLINE_PLAN"}
    if args.dry_run:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        return
    client = OpenAICompatClient.from_env("https://api.groq.com/openai/v1", "GROQ_API_KEY_Reviewpulse", report["model"],
        provider="groq", structured="json_schema", seed=None, max_tokens=768, max_retries=2, rpm=10, tpm=8000)
    cache = ResultCache(Path("data/llm_cache/eight-rule-semantic"))
    for key, system, payload, schema, _ in requests:
        row = {"id": key}
        try:
            cache_key = fingerprint({"model": client.model, "system": system, "payload": payload, "schema": schema, "max_tokens": 768})
            saved = cache.get(cache_key)
            if saved is None:
                raw = client.complete(system, json.dumps(payload, ensure_ascii=False), schema)
                saved = {"status": "COMPLETE", "raw": raw, "usage": {k: v for k, v in client.last.items() if k != "text"}}
                cache.put(cache_key, saved)
            row.update(status="DRAFTED", **{k: v for k, v in saved.items() if k != "status"})
        except APIUnavailable as error:
            row.update(status="REQUEST_REJECTED" if error.http_status in (400, 422) else "API_UNAVAILABLE", reason=error.reason)
        except LLMError as error:
            row.update(status="GENERATION_FAILURE", reason=type(error).__name__)
        report["rows"].append(row)
        report["http_events"] = client.events
        report["status"] = "COMPLETE" if len(report["rows"]) == len(requests) else "PARTIAL"
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(key, row["status"], flush=True)
        if row["status"] == "API_UNAVAILABLE":
            break


if __name__ == "__main__":
    main()
