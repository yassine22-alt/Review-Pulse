"""Reproduce an assisted real-drawing trace; never present manual rules as LLM outputs."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pymupdf

from reviewpulse.ingest.pdf_backend import PyMuPdfBackend
from reviewpulse.interpreter.checked import catalogue_from
from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Inputs, Program
from reviewpulse.interpreter.structured import SlotDraft, compile_slots, slots_from_program
from reviewpulse.interpreter.units import convert
from reviewpulse.pipeline import build_model
from reviewpulse.rules.clauses import Clause, split_text
from reviewpulse.schema import save


def evaluate(row, text, document, inputs, whole="building"):
    start = text.index(row["quote"])
    clause = Clause(row["id"], row["id"], row["quote"], 1, start, start + len(row["quote"]))
    context = ContextBundle(document=document, text=text, clauses=[clause], target=clause.id)
    result = {"id": row["id"], "source": row["quote"], "interpretation_origin": "benchmark author",
              "approval_scope": row.get("scope", row.get("review_note")), "outcome": "UNRESOLVED"}
    if row["requirement"] is None:
        return result | {"stage": "NEEDS_REVIEW", "blocker": row["review_note"]}
    reference = Program.model_validate({
        "id": row["id"], "title": row["id"], "document": document, "requirement": row["requirement"],
        "sources": [{"clause": clause.id, "start": clause.start, "end": clause.end, "quote": clause.text}],
    })
    slots = slots_from_program(reference, row["subject"])
    result["manual_slots"] = slots
    catalogue = catalogue_from(inputs, None) | {"whole": whole, "building": sorted(inputs.facts.get(whole, {}))}
    try:
        program = compile_slots(SlotDraft.model_validate(slots), context, catalogue)
    except ValueError as error:
        return result | {"stage": getattr(error, "stage", "validation"), "blocker": str(error)}
    program = program.model_copy(update={"status": "approved", "approved_by": "benchmark author (no independent review)"})
    return result | {"stage": "checked", "approved_rule": program.model_dump(mode="json"),
                     **run_program(program, inputs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--labels", type=Path, default=Path("reports/recovery-drawing-labels.json"))
    args = parser.parse_args()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest() != labels["source"]["sha256"]:
        raise ValueError("drawing changed; source-backed annotations must be reviewed")
    args.output.mkdir(parents=True, exist_ok=True)
    page_index = labels["source"]["page_index"]
    with pymupdf.open(args.pdf) as pdf:
        text = pdf[page_index].get_text()
    clauses = split_text(text)
    sheet = PyMuPdfBackend().extract(args.pdf, page_index, args.pdf.stem)
    save(sheet, args.output / "sheet.json")
    # Explicitly a vector-only baseline, not a benchmark of the teammate's trained segmentation.
    model = build_model(sheet, learned=False)
    save(model, args.output / "building.json")
    rows = []
    for row in labels["requirements"]:
        facts = {entity: {name: {"source": "Not established by the supplied sheet", "trusted": False}
                                  for name in row["bindings"]}
                 for collection in row["collections"].values() for entity in collection["items"]}
        inputs = Inputs(bindings=row["bindings"], collections=row["collections"], facts=facts)
        result = evaluate(row, text, labels["source"]["title"], inputs)
        result["automatic_clause_containers"] = [c.id for c in clauses if row["quote"] in c.text]
        result["plan_inputs"] = inputs.model_dump(mode="json")
        rows.append(result)
    component = labels["component"]
    observations = {}
    for observation in labels["observations"]:
        binding = component["bindings"][observation["fact"]]
        observations.setdefault(observation["entity"], {})[observation["fact"]] = {
            "value": convert(observation["value"], observation["unit"], binding["unit"]),
            "source": observation["source"], "trusted": True,
            "origin": observation["origin"], "reviewer": observation["reviewer"],
        }
    inputs = Inputs(bindings=component["bindings"], facts=observations)
    fragment = evaluate(component, text, labels["source"]["title"], inputs, component["entity"])
    fragment["plan_inputs"] = inputs.model_dump(mode="json")
    report = {"source": labels["source"], "limitations": [labels["status"], labels["interpretation"],
              "Only one sheet is processed; no complete building inventory is claimed.",
              "No LLM is called. Nominal-width component is excluded from whole-clause decision counts.",
              "Reviewer observations cite the real drawing; previous benchmark attestations remain synthetic."],
              "vector_baseline": {"primitives": len(sheet.primitives), "text_items": len(sheet.texts),
                  "rooms": len(model.rooms), "elements": len(model.elements),
                  "scale": model.sheet.scale.model_dump(mode="json"), "warnings": model.sheet.warnings},
              "whole_clause_outcomes": dict(Counter(row["outcome"] for row in rows)),
              "requirements": rows, "partial_component_only": fragment}
    (args.output / "findings.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"whole_clauses": report["whole_clause_outcomes"],
                      "component_only": fragment["outcome"], "vector_rooms": len(model.rooms)}))


if __name__ == "__main__":
    main()
