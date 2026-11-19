"""Probe source-grounded missing meanings. A declaration is never observed evidence."""
import argparse
import json
from pathlib import Path

from development_cases import load_cases
from run_slot_pilot import request_for

from reviewpulse.interpreter.declarations import apply_declarations, declaration_catalogue
from reviewpulse.interpreter.schema import FactDeclaration
from reviewpulse.interpreter.structured import ProposedFact, ground_span
from reviewpulse.interpreter.table_rows import declaration_request
from reviewpulse.interpreter.units import compatible
from reviewpulse.llm.openai_compat import APIUnavailable, OpenAICompatClient
from reviewpulse.llm.result_cache import ResultCache, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("access_text", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(Path("reports/relational-declaration-probes.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in load_cases(Path.cwd(), args.access_text)}
    client = OpenAICompatClient.from_env("https://api.groq.com/openai/v1", "GROQ_API_KEY_Reviewpulse", "openai/gpt-oss-120b",
        provider="groq", structured="json_schema", seed=None, max_tokens=1024, max_retries=2, rpm=10, tpm=8000)
    cache = ResultCache(Path("data/llm_cache/relational-declarations"))
    result = {"manifest": manifest, "model": client.model, "rows": [], "http_events": []}
    for key in manifest["cases"]:
        case = cases[key]
        catalogue = request_for(case, "structured")[3]
        target = next(c for c in case["context"].clauses if c.id == key)
        frame = {"measurements": [{"id": "m0", "unit": manifest["requested_unit"],
                                  "header": {"quote": target.text}}]}
        system, payload, schema = declaration_request(frame, catalogue)
        payload["context"] = [{"id": c.id, "text": c.text} for c in case["context"].clauses if c.id != key]
        fingerprint_key = fingerprint({"system": system, "payload": payload, "schema": schema, "model": client.model, "max_tokens": 1024})
        row = {"id": key, "source": case["context"].text, "status": "NEEDS_REVIEW", "regulatory_verdict": "UNRESOLVED",
               "normative_rule_complete": False, "evidence_requests": [], "approved": False}
        try:
            saved = cache.get(fingerprint_key)
            if saved is None:
                raw = client.complete(system, json.dumps(payload, ensure_ascii=False), schema)
                saved = {"status": "COMPLETE", "raw": raw, "usage": {k: v for k, v in client.last.items() if k != "text"}}
                cache.put(fingerprint_key, saved)
            row.update(raw=saved["raw"], usage=saved["usage"])
            proposal = ProposedFact.model_validate(saved["raw"])
            if proposal.source.clause != "m0" or not compatible(proposal.unit, manifest["requested_unit"]):
                raise ValueError("declaration must preserve the requested source header and physical dimension")
            source = ground_span(proposal.source.model_copy(update={"clause": key}), case["context"])
            declaration = FactDeclaration.model_validate(proposal.model_dump(exclude={"source", "status"}) | {"source": source})
            declaration_catalogue(catalogue, [declaration])
            ledger = apply_declarations(case["inputs"], [declaration])
            targets = ["building"] if declaration.entity == "building" else ledger.collections[declaration.entity].items
            row.update(status="TYPED_DECLARATION_VALIDATED_AWAITING_REVIEW", declaration=declaration.model_dump(mode="json"),
                ledger_missing_values=all(ledger.facts[entity][declaration.name].value is None for entity in targets),
                evidence_requests=[{"fact": declaration.name, "entity": declaration.entity, "unit": declaration.unit,
                    "reason": "missing", "why": declaration.definition, "source": source.model_dump()}])
        except APIUnavailable as error:
            row.update(status="REQUEST_REJECTED" if error.http_status in (400, 422) else "API_UNAVAILABLE", reason=error.reason, http_status=error.http_status)
        except ValueError as error:
            row.update(status="NEEDS_REVIEW", reason=str(error))
        result["rows"].append(row)
        result["http_events"] = client.events
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(key, row["status"], flush=True)
        if row["status"] == "API_UNAVAILABLE":
            break


if __name__ == "__main__":
    main()
