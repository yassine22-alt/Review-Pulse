"""Explicitly assisted source-to-verdict slice; never uploads drawings or calls an LLM."""
import argparse
import json
from pathlib import Path

import networkx as nx
import pymupdf
from real_interpreter_holdout import bundle
from recovery_drawing_demo import write_report

from reviewpulse.factgraph.convert import to_graph, to_inputs
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.checked import catalogue_from
from reviewpulse.interpreter.deterministic import extract_quantities
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Inputs, Program
from reviewpulse.interpreter.structured import SlotDraft, compile_slots, slots_from_program
from reviewpulse.schema import BuildingModel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("building", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", type=Path, default=Path("reports/plan-answerable-profile.json"))
    parser.add_argument("--drafts", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    drafts = {row["id"]: row for row in json.loads(args.drafts.read_text(encoding="utf-8"))["rows"]} if args.drafts else {}
    model = BuildingModel.model_validate_json(args.building.read_text(encoding="utf-8"))
    automatic = from_building(model, complete=False)
    initial = to_inputs(automatic).model_dump(mode="json")
    reviewed = Inputs.model_validate(profile["reviewed_inputs"])
    initial["bindings"].update(profile["reviewed_inputs"]["bindings"])
    initial["collections"].update({name: {"items": [], "complete": False, "trusted": False}
                                   for name in reviewed.collections})
    detected = model.model_dump(mode="json")
    for name, selector in profile.get("automatic_scope_selectors", {}).items():
        allowed = {" ".join(value.casefold().split()) for value in selector["allowed"]}
        selected = [entity["id"] for entity in detected.get(selector["entity_list"], [])
                    if " ".join(str(entity.get(selector["field"]) or "").casefold().split()) in allowed
                    and (not selector.get("class_field") or entity.get(selector["class_field"]) == selector["class_value"])]
        initial["collections"][name]["items"] = selected
    initial = Inputs.model_validate(initial)
    graph = nx.MultiGraph()
    for node in profile["reviewed_nodes"]:
        graph.add_node(node["id"], **{key: value for key, value in node.items() if key != "id"})
    for edge in profile["reviewed_edges"]:
        graph.add_edge(edge["a"], edge["b"], **{key: value for key, value in edge.items() if key not in ("a", "b")})
    with pymupdf.open(args.pdf) as pdf:
        page = pdf[profile["source_page"]]
        source_text = page.get_text()
        page.get_pixmap(matrix=pymupdf.Matrix(0.65, 0.65)).save(args.output / "drawing.png")
    if any(quote not in source_text for quote in profile["native_dimension_citations"]):
        raise ValueError("dimension citation absent from drawing")
    catalogue = catalogue_from(reviewed, None)
    rows = []
    for row in profile["requirements"]:
        context = bundle(profile["source_kind"], row["id"], row["text"], row.get("context", {}))
        clause = next(c for c in context.clauses if c.id == row["id"])
        reference = Program.model_validate({"id": row["id"], "title": row["text"], "document": context.document,
            "requirement": row["requirement"], "sources": [{"clause": clause.id, "start": clause.start,
                                                          "end": clause.end, "quote": clause.text}]})
        frame = slots_from_program(reference, row["subject"])
        result = {"id": row["id"], "source": clause.text, "manual_slots": frame,
                  "quantity_extraction": extract_quantities(row["text"]), "outcome": "UNRESOLVED",
                  "approval_scope": profile["scope"]}
        if args.drafts:
            draft = drafts.get(row["id"], {})
            result["llm_draft"] = draft
            if "raw" not in draft:
                result.update(stage="draft_unavailable", blocker="No completed model draft; not counted as a semantic failure")
                rows.append(result)
                continue
            result["review_edits"] = [{"operation": "rewrite", "site": "formal_rule", "before": draft["raw"],
                "after": frame, "reviewer": profile["reviewer"],
                "reason": "Semantic reading requires complete reviewer-authored executable formalization; not zero edit burden"}]
        try:
            program = compile_slots(SlotDraft.model_validate(frame), context, catalogue)
            program = program.model_copy(update={"status": "approved", "approved_by": profile["reviewer"]})
            before = run_program(program, initial, graph=to_graph(automatic))
            after = run_program(program, reviewed, graph=graph)
            result.update(before=before, after=after, outcome=after["outcome"], trace=after["trace"],
                          rule=program.model_dump(mode="json"), stage="checked")
        except ValueError as error:
            result.update(stage=getattr(error, "stage", "compile"), blocker=str(error))
        rows.append(result)
    report = {"source": profile["source"],
              "counted_units": "Reviewer-selected target obligations",
              "limits": profile["limits"], "requirements": rows,
              "automatic_facts": initial.model_dump(mode="json"), "reviewed_facts": reviewed.model_dump(mode="json"),
              "inventory_attestation": profile["inventory_attestation"],
              "automatic_decisions": sum(r.get("before", {}).get("outcome") in ("SATISFIED", "VIOLATED") for r in rows),
              "reviewed_decisions": sum(r["outcome"] in ("SATISFIED", "VIOLATED") for r in rows)}
    report["needs_review"] = sum(r["stage"] not in ("checked", "draft_unavailable") for r in rows)
    report["unavailable"] = sum(r["stage"] == "draft_unavailable" for r in rows)
    report["unresolved_evaluated"] = sum(r["stage"] == "checked" and r["outcome"] == "UNRESOLVED" for r in rows)
    report["reviewer_rewrites"] = sum(len(r.get("review_edits", [])) for r in rows)
    if "expected_outcomes" in profile:
        report["ground_truth_limits"] = profile["truth_limits"]
        report["false_passes"] = [sum(r["outcome"] == "SATISFIED" and profile["expected_outcomes"].get(r["id"]) == "VIOLATED" for r in rows),
                                  sum(profile["expected_outcomes"].get(r["id"]) == "VIOLATED" for r in rows)]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "findings.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_report(report, args.output)
    # No partial component is added to these whole-clause counts.
    print(json.dumps({"automatic_decisions": [report["automatic_decisions"], len(rows)],
                      "reviewed_decisions": [report["reviewed_decisions"], len(rows)],
                      "outcomes": {r["id"]: [r["stage"], r["outcome"]] for r in rows}}))


if __name__ == "__main__":
    main()
