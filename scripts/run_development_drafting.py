"""Resumable batches. Transport failures are excluded from semantic counts."""
import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path


class RequestGate:
    """Pace actual attempts and share one invocation's allowance across cycles."""

    def __init__(self, client, unavailable, budget=None, interval=0.0):
        self.client, self.unavailable = client, unavailable
        self.send = client._request
        self.remaining, self.interval, self.last = budget, interval, None

    def __call__(self, payload):
        if self.remaining == 0:
            self.client.unavailable = True
            raise self.unavailable("REQUEST_BUDGET_EXHAUSTED", None, 0)
        if self.last is not None:
            time.sleep(max(0.0, self.last + self.interval - time.monotonic()))
        self.last = time.monotonic()
        if self.remaining is not None:
            self.remaining -= 1
        return self.send(payload)


def module_from_current(repo, name):
    spec = importlib.util.spec_from_file_location(f"reviewpulse.llm.{name}", repo / f"src/reviewpulse/llm/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", choices=("gemini", "ollama"), default="gemini")
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--request-budget", type=int, help="Maximum hosted HTTP attempts in this invocation")
    parser.add_argument("--min-interval", type=float, default=0, help="Minimum seconds between hosted attempts")
    parser.add_argument("--original-src", type=Path)
    parser.add_argument("--cache", type=Path, default=Path("runs/drafting-result-cache"))
    args = parser.parse_args()
    if min(args.batch_size, args.cycles) < 1:
        parser.error("batch size and cycles must be positive")
    if args.min_interval < 0 or (args.request_budget is not None and args.request_budget < 1):
        parser.error("request budget must be positive and interval nonnegative")
    repo = Path(__file__).resolve().parents[1]
    source = args.original_src or repo / "src"
    sys.path.insert(0, str(source))
    from development_cases import load_cases

    from reviewpulse.interpreter.checked import catalogue_from, checked_draft
    from reviewpulse.xeval.drafters import BoundedOllama

    class TrackedOllama(BoundedOllama):
        def __init__(self):
            super().__init__(model=args.model, num_predict=args.max_tokens, timeout_s=args.timeout)
            self.unavailable = False
            self.events = []

        def complete(self, system, user, json_schema):
            if self.unavailable:
                raise RuntimeError("API_UNAVAILABLE: local circuit is open")
            try:
                result = super().complete(system, user, json_schema)
            except Exception as error:
                self.unavailable = isinstance(error, (OSError, TimeoutError, ConnectionError)) or bool(
                    re.search(r"not reachable|connection refused", str(error), re.I))
                self.events.append({"http_status": None if self.unavailable else 200,
                                    "reason": type(error).__name__})
                raise
            self.events.append({"http_status": 200})
            return result

    transport = module_from_current(repo, "gemini")
    caching = module_from_current(repo, "result_cache")
    cache = caching.ResultCache(args.cache)
    code = caching.fingerprint({
        str(path.relative_to(source)): path.read_text(encoding="utf-8")
        for package in ("interpreter", "xeval") for path in (source / "reviewpulse" / package).iterdir()
        if path.is_file() and path.suffix in {".py", ".yaml", ".json"}
    })
    transport_code = caching.fingerprint({"source": (repo / "src/reviewpulse/llm/gemini.py").read_text(encoding="utf-8")})
    cases = load_cases(repo, args.access_text)
    report = {"backend": args.backend, "model": args.model, "code_fingerprint": code, "batch_size": args.batch_size,
              "retry_cycles": args.cycles, "http_attempts_per_completion": 3, "concurrency": 1,
              "max_tokens": args.max_tokens, "timeout": args.timeout, "batches": [], "results": [],
              "request_budget": args.request_budget, "min_interval_s": args.min_interval,
              "configured_key_variables": [name for name in (
                  "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                  "REVIEWPULSE_LLM_API_KEY", "REVIEWPULSE_FALLBACK_API_KEY") if os.environ.get(name)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if any(previous.get(name) != report[name] for name in ("backend", "model", "code_fingerprint", "max_tokens", "timeout")):
            parser.error("output belongs to different code or settings; choose a new output path")
        report = previous
    report["invocation"] = report.get("invocation", 0) + 1
    report.setdefault("invocation_limits", []).append({
        "invocation": report["invocation"], "request_budget": args.request_budget,
        "min_interval_s": args.min_interval})

    def save():
        report["semantic_evaluated"] = sum(row["status"] != "API_UNAVAILABLE" for row in report["results"])
        report["pending"] = [case["id"] for case in cases if not any(
            row["id"] == case["id"] and row["status"] != "API_UNAVAILABLE" for row in report["results"])]
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.backend == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        report["status"], report["blocker"] = "API_UNAVAILABLE", "MISSING_ENV_CREDENTIAL"
        report["http_error_rate"] = [0, 0]
        save()
        print("API_UNAVAILABLE: GEMINI_API_KEY is absent. HTTP attempts 0/0. No semantic evaluations.", flush=True)
        return
    report["status"] = "RUNNING"
    save()
    hosted = gate = None
    if args.backend == "gemini":
        hosted = transport.GeminiClient(model=args.model, max_tokens=args.max_tokens, timeout_s=args.timeout)
        gate = RequestGate(hosted, transport.APIUnavailable, args.request_budget, args.min_interval)
        hosted._request = gate
    for start in range(0, len(cases), args.batch_size):
        pending = cases[start:start + args.batch_size]
        for cycle in range(args.cycles):
            if gate is not None and gate.remaining == 0:
                report["status"], report["blocker"] = "API_UNAVAILABLE", "REQUEST_BUDGET_EXHAUSTED"
                save()
                print("Stopped at the configured request budget.", flush=True)
                return
            client = hosted if hosted is not None else TrackedOllama()
            client.unavailable = False
            before = len(getattr(client, "events", []))
            unavailable = []
            batch = {"number": start // args.batch_size + 1, "cycle": cycle + 1, "ids": [], "cache_hits": 0}
            for case in pending:
                batch["ids"].append(case["id"])
                key = caching.fingerprint({
                    "code": code, "model": args.model, "backend": args.backend, "tokens": args.max_tokens,
                    "timeout": args.timeout, "transport_code": transport_code,
                    "context": case["context"].model_dump(mode="json"),
                    "catalogue": catalogue_from(case["inputs"], case["graph"]),
                })
                result = cache.get(key)
                if result is not None:
                    batch["cache_hits"] += 1
                else:
                    try:
                        result = checked_draft(case["context"], case["inputs"], case["graph"], client, triage=True)
                    except Exception as error:
                        result = {"status": "NEEDS_REVIEW", "reason": type(error).__name__, "stage": "generation"}
                    if getattr(client, "unavailable", False):
                        result = {"status": "API_UNAVAILABLE", "stage": "transport", "program": None}
                    else:
                        cache.put(key, result)
                row = {"id": case["id"], "batch": batch["number"], "cycle": cycle + 1, **result}
                report["results"] = [old for old in report["results"] if old["id"] != case["id"]] + [row]
                if result["status"] == "API_UNAVAILABLE":
                    unavailable.append(case)
            events = getattr(client, "events", [])[before:]
            batch["http_error_rate"] = [sum(event["http_status"] != 200 for event in events), len(events)]
            batch["invocation"] = report["invocation"]
            batch["unavailable_rate"] = [len(unavailable), len(pending)]
            batch["events"] = events
            report["batches"].append(batch)
            if gate is not None:
                report["request_budget_remaining"] = gate.remaining
            save()
            print("batch", batch["number"], "cycle", cycle + 1, "HTTP errors", batch["http_error_rate"],
                  "unavailable", batch["unavailable_rate"], flush=True)
            if gate is not None and gate.remaining == 0 and unavailable:
                report["status"], report["blocker"] = "API_UNAVAILABLE", "REQUEST_BUDGET_EXHAUSTED"
                save()
                print("Stopped at the configured request budget.", flush=True)
                return
            if not unavailable:
                break
            pending = unavailable
        if unavailable:
            report["status"] = "API_UNAVAILABLE"
            save()
            print("Stopped after the configured retry cycles.", flush=True)
            return
    report["status"] = "COMPLETE"
    save()


if __name__ == "__main__":
    main()
