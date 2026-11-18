"""Small controlled local experiments; source data and model outcomes stay separate."""
import argparse
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path, required=True, help="Frozen package source directory")
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source))
    from development_cases import load_cases
    from run_slot_pilot import compile_response, request_for

    from reviewpulse.xeval.drafters import BoundedOllama

    repo = Path(__file__).resolve().parents[1]
    protocol = json.loads((args.protocol or repo / "reports/recovery-protocol.json").read_text())
    cases = {case["id"]: case for case in load_cases(repo, args.access_text)}
    report = {"arm": "monolithic", "source": str(args.source), "protocol": protocol,
              "status": "RUNNING", "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save()
    for key in protocol["development_ids"]:
        case = cases[key]
        system, payload, schema, catalogue = request_for(case, "structured")
        client = BoundedOllama(model=protocol["model"], num_predict=protocol["baseline_tokens"],
                               timeout_s=protocol["timeout_seconds"])
        start = time.monotonic()
        row = {"id": key, "retained": False, "schema_valid": False}
        try:
            raw = client.complete(system, json.dumps(payload, ensure_ascii=False), schema)
            row["raw"] = raw
            from reviewpulse.interpreter.structured import SlotDraft

            SlotDraft.model_validate(raw)
            row["schema_valid"] = True
            program = compile_response(raw, case, catalogue, "structured")
            row.update(stage="retained", retained=True, program=program.model_dump(mode="json"))
        except Exception as error:
            row.update(stage=getattr(error, "stage", "generation_or_schema"), detail=str(error))
            if isinstance(error, TimeoutError):
                row["stage"] = "runtime_budget"
            if client.last.get("done") == "length":
                row["stage"] = "generation_cap"
        row.update(seconds=round(time.monotonic() - start, 3), response=client.last)
        report["cases"].append(row)
        save()
        print(key, row["stage"], row["seconds"], flush=True)
    report["status"] = "COMPLETE"
    save()


if __name__ == "__main__":
    main()
