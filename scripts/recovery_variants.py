"""Run compact and decomposed local controls on the preselected development cases."""
import argparse
import json
import time
import urllib.request
from pathlib import Path

from development_cases import load_cases
from run_slot_pilot import compile_response, request_for

from reviewpulse.interpreter.decomposed import (
    ExpressionFrame,
    formal_request,
    reading_request,
    repair_field,
    repair_request,
    schema_contract,
)
from reviewpulse.rules.draft import OllamaClient


class MeasuredClient(OllamaClient):
    def __init__(self, protocol):
        super().__init__(model=protocol["model"], timeout_s=protocol["timeout_seconds"],
                         seed=protocol["seed"], num_ctx=protocol["context_tokens"])
        self.protocol = protocol
        self.last = {}

    def generate(self, system, payload, schema, tokens, constrained=True):
        self.last = {"text": "", "max_tokens": tokens, "constrained": constrained}
        body = {"model": self.model, "stream": True,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": payload}],
                "options": {"temperature": 0, "seed": self.seed, "num_ctx": self.num_ctx, "num_predict": tokens}}
        if constrained:
            body["format"] = schema
        else:
            body["messages"][0]["content"] += " Return a JSON object with these fields: " + ", ".join(schema["properties"])
        request = urllib.request.Request(self.host + "/api/chat", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                for line in response:
                    if not line.strip():
                        continue
                    part = json.loads(line)
                    self.last["text"] += part.get("message", {}).get("content", "")
                    if time.monotonic() - start > self.timeout_s:
                        raise TimeoutError("local generation wall-time budget exhausted")
                    if part.get("done"):
                        self.last.update({key: part.get(key) for key in ("done_reason", "eval_count", "eval_duration", "prompt_eval_count")})
            if self.last.get("done_reason") == "length":
                raise ValueError("generation token budget exhausted")
            text = self.last["text"].strip()
            if text.startswith("```json") and text.endswith("```"):
                text = text[7:-3].strip()
            return json.loads(text)
        finally:
            self.last["seconds"] = round(time.monotonic() - start, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    protocol = json.loads((args.protocol or repo / "reports/recovery-protocol.json").read_text())
    cases = {case["id"]: case for case in load_cases(repo, args.access_text)}
    report = {"protocol": protocol, "status": "RUNNING", "cases": []}

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save()
    for key in protocol["development_ids"]:
        case, client = cases[key], MeasuredClient(protocol)
        row = {"id": key, "arms": {}, "reading": None, "reading_call": None}
        report["cases"].append(row)
        save()
        system, payload, schema, catalogue = request_for(case, "original_expression")
        payload["output_contract"] = schema_contract(schema)
        base_payload = formal_request(case["context"], payload)
        terse_system = system + " Use short exact quotations, not complete paragraphs, wherever a unique source span suffices."

        def attempt(arm, reading=None, constrained=True, *, client=client, case=case,
                    payload=payload, schema=schema, catalogue=catalogue, terse_system=terse_system, row=row):
            result = {"retained": False, "schema_valid": False}
            try:
                raw = client.generate(terse_system, json.dumps(formal_request(case["context"], payload, reading), ensure_ascii=False),
                                      schema, protocol["baseline_tokens"] if arm == "expression_control" else protocol["formalization_tokens"], constrained)
                result["raw"] = raw
                ExpressionFrame.model_validate(raw)
                result["schema_valid"] = True
                program = compile_response(raw, case, catalogue, "original_expression")
                result.update(stage="retained", retained=True, program=program.model_dump(mode="json"))
            except Exception as error:
                result.update(stage=getattr(error, "stage", "generation_or_schema"), detail=str(error))
                if isinstance(error, TimeoutError):
                    result["stage"] = "runtime_budget"
            result["call"] = dict(client.last)
            row["arms"][arm] = result
            save()
            if args.output.with_suffix(".STOP").exists():
                report["status"] = "STOPPED_RESOURCE_LIMIT"
                save()
                raise SystemExit(0)
            return result

        attempt("expression_control")
        r_system, r_payload, r_schema = reading_request(case["context"])
        try:
            row["reading"] = client.generate(r_system, json.dumps(r_payload, ensure_ascii=False), r_schema,
                                              protocol["reading_tokens"])
        except Exception as error:
            row["reading_error"] = str(error)
        row["reading_call"] = dict(client.last)
        save()
        attempt("decomposed", row["reading"], False)
        candidate = attempt("decomposed_constrained", row["reading"])
        repaired = json.loads(json.dumps(candidate))
        repaired["repair_attempted"] = False
        if not candidate["retained"] and candidate.get("raw") and candidate["schema_valid"]:
            try:
                compile_response(candidate["raw"], case, catalogue, "original_expression")
            except Exception as error:
                field = repair_field(candidate["raw"], case["context"], error, row["reading"])
                repair_system, repair_payload, repair_schema = repair_request(candidate["raw"], field, schema,
                    {**base_payload, "semantic_reading": row["reading"]}, error)
                repaired.update(repair_attempted=True, repair_field=field)
                try:
                    patch = client.generate(repair_system, repair_payload, repair_schema, protocol["repair_tokens"])
                    corrected = {**candidate["raw"], field: patch[field]}
                    repaired["raw"] = corrected
                    ExpressionFrame.model_validate(corrected)
                    program = compile_response(corrected, case, catalogue, "original_expression")
                    repaired.update(stage="retained", retained=True, program=program.model_dump(mode="json"))
                except Exception as failure:
                    repaired.update(stage=getattr(failure, "stage", "repair_failed"), detail=str(failure))
                    if isinstance(failure, TimeoutError):
                        repaired["stage"] = "runtime_budget"
                repaired["repair_call"] = dict(client.last)
        row["arms"]["targeted_repair"] = repaired
        save()
        print(key, {arm: data["stage"] for arm, data in row["arms"].items()}, flush=True)
    report["status"] = "COMPLETE"
    save()


if __name__ == "__main__":
    main()
