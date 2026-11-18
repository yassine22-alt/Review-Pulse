"""Re-score saved development model responses without invoking a model or validator."""
import argparse
import json
from pathlib import Path

from reviewpulse.xeval.slot_scoring import partial_json, score_slots, totals


def responses(directory, known):
    if directory is None:
        return {}
    found = {}
    for path in sorted(directory.glob("*"), key=lambda p: p.stat().st_mtime):
        if path.suffix not in (".json", ".jsonl"):
            continue
        if path.suffix == ".jsonl":
            chunks = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            key = path.stem.rsplit("-", 1)[0]
            record = {"case": key, "text": "".join(chunk.get("message", {}).get("content", "") for chunk in chunks)}
        else:
            record = json.loads(path.read_text(encoding="utf-8"))
        key = record.get("case")
        if key not in known:
            continue
        raw = record.get("response")
        if not isinstance(raw, dict):
            raw = partial_json(record.get("text") or "")
        if not isinstance(raw, dict) or "checkable" in raw:
            continue
        if not (set(raw) & {"nodes", "require", "subject", "requirement", "id", "title", "metadata_applicability"}):
            continue
        found.setdefault(key, []).append({"raw": raw, "trace": str(path),
                                          "subject_requested": "require" not in raw})
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--run-report", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))
    gold = {row["id"]: row for row in read(repo / "reports/development-oracle-slots.json")["cases"]}
    annotations = {row["id"]: row for row in read(repo / "reports/development-metadata-labels.json")["cases"]}
    report = read(args.run_report) if args.run_report else {}
    selected = report.get("selected_ids", list(gold))
    pipeline = {row["id"]: row for row in report.get("results", [])}
    found = responses(args.raw_dir, gold)
    rows = []
    for key in selected:
        row = {"id": key, "pipeline_retained": bool(pipeline[key].get("program")) if key in pipeline else None}
        candidates = found.get(key, [])
        if candidates:
            row.update(status="RAW_AVAILABLE", captured_drafts=len(candidates))
            for label, candidate in (("initial", candidates[0]), ("final", candidates[-1])):
                row[label] = score_slots(candidate["raw"], gold[key], annotations[key],
                                         subject_requested=candidate["subject_requested"])
                row[f"{label}_trace"] = candidate["trace"]
        else:
            row["status"] = ("RAW_NOT_RECORDED" if key in pipeline and pipeline[key]["status"] != "API_UNAVAILABLE"
                             else pipeline.get(key, {}).get("status", "NOT_EVALUATED"))
        rows.append(row)
    output = {"development_only": True, "planned": len(rows),
              "raw_available": sum(row["status"] == "RAW_AVAILABLE" for row in rows),
              "initial": totals([row["initial"] for row in rows if "initial" in row]),
              "final": totals([row["final"] for row in rows if "final" in row]), "cases": rows,
              "limitations": [
                  "Exact normalized set agreement per slot, not semantic rule accuracy. Fact aliases are not inferred.",
                  "SI-normalized values and dimensional units are scored separately; associations between fields are not scored.",
                  "Subject accepts frozen source phrases; expression-only interfaces do not request this slot and are excluded.",
                  "Only 15 thermal metadata scopes are annotated. Other applicability denominators exclude unannotated scope.",
                  "Raw-not-recorded and API-unavailable responses are not scored as zero accuracy.",
                  "Truncated output contributes only completed fields; missing requested fields count incorrect.",
                  "Initial and final captured attempts are separate; no best-of selection. Retention is independent.",
                  "Gold labels have no independent review; the fourth document is not used."]}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"raw_available": output["raw_available"], "planned": output["planned"], "final": output["final"]}))


if __name__ == "__main__":
    main()
