"""Explicitly assisted source-to-verdict slice; never uploads drawings or calls an LLM."""
import argparse
import json
from pathlib import Path

import networkx as nx
import pymupdf
from recovery_drawing_demo import write_report

from reviewpulse.factgraph.convert import to_graph, to_inputs
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.checked import catalogue_from
from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.interpreter.deterministic import extract_quantities
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Inputs, Program
from reviewpulse.interpreter.structured import SlotDraft, compile_slots, slots_from_program
from reviewpulse.rules.clauses import split_text
from reviewpulse.schema import BuildingModel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("building", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    profile = json.loads(Path("reports/plan-answerable-profile.json").read_text(encoding="utf-8"))
    model = BuildingModel.model_validate_json(args.building.read_text(encoding="utf-8"))
    automatic = from_building(model, complete=False)
    initial = to_inputs(automatic).model_dump(mode="json")
    bindings = {"area_m2": {"kind": "number", "unit": "m2", "description": "Internal floor area"},
                "min_width_m": {"kind": "number", "unit": "m", "description": "Minimum internal room width"},
                "clear_width_m": {"kind": "number", "unit": "m", "description": "Net clear opening, not nominal door size"},
                "room_type": {"kind": "string", "description": "Confirmed room classification"}}
    initial["bindings"].update(bindings)
    selected = {name: {"items": [], "complete": False, "trusted": False}
                for name in ("reviewed_bedrooms", "reviewed_halls", "reviewed_doors", "final_exits")}
    initial["collections"].update(selected)
    initial = Inputs.model_validate(initial)
    graph = nx.MultiGraph()
    facts = {}

    def attested(value, source):
        return {"value": value, "source": source, "trusted": value is not None,
                "origin": "reviewer-attested", "reviewer": "benchmark author; no independent review"}

    with pymupdf.open(args.pdf) as pdf:
        source_text = pdf[6].get_text()
        pdf[6].get_pixmap(matrix=pymupdf.Matrix(0.65, 0.65)).save(args.output / "drawing.png")
    for room in profile["reviewed_rooms"]:
        if room["dimension_quote"] not in source_text:
            raise ValueError("room dimension citation absent from drawing")
        facts[room["id"]] = {name: attested(room[name], room["source"] + "; " + room["review_note"])
                             for name in ("area_m2", "min_width_m")}
        facts[room["id"]]["room_type"] = attested("bedroom", room["source"])
        graph.add_node(room["id"], kind="room", role="member")
    facts["hall"] = {"room_type": attested("corridor", "Author identifies HALL circulation on A-7")}
    facts["D06"] = {"clear_width_m": {"value": None, "source": "A-7 D06 label 3076 is nominal; net clear opening is not specified"}}
    graph.add_node("hall", kind="room", role="member")
    for edge in profile["reviewed_paths"]:
        graph.add_edge(edge["a"], edge["b"], kind="door", trusted=True, via=edge["source"])
    collections = {**selected,
        "reviewed_bedrooms": {"items": [r["id"] for r in profile["reviewed_rooms"]], "complete": True, "trusted": True},
        "reviewed_halls": {"items": ["hall"], "complete": True, "trusted": True},
        "reviewed_doors": {"items": ["D06"], "complete": True, "trusted": True}}
    reviewed = Inputs(bindings=bindings, facts=facts, collections=collections, graph_complete=False,
        evidence_locations={"clear_width_m": "Manufacturer clear-opening data or a dimension explicitly labelled net clear",
                            "final_exits": "Ground-floor, staircase and site egress drawings"})
    text = "\n\n".join(f"{index}. {row['text']}" for index, row in enumerate(profile["requirements"], 1))
    clauses = split_text(text)
    catalogue = catalogue_from(reviewed, None)
    rows = []
    for row in profile["requirements"]:
        clause = next(c for c in clauses if row["text"] in c.text)
        context = ContextBundle(document=profile["source_kind"], text=text, clauses=[clause], target=clause.id)
        reference = Program.model_validate({"id": row["id"], "title": row["text"], "document": context.document,
            "requirement": row["requirement"], "sources": [{"clause": clause.id, "start": clause.start,
                                                          "end": clause.end, "quote": clause.text}]})
        frame = slots_from_program(reference, row["subject"])
        result = {"id": row["id"], "source": clause.text, "manual_slots": frame,
                  "quantity_extraction": extract_quantities(row["text"]), "outcome": "UNRESOLVED",
                  "approval_scope": profile["scope"]}
        try:
            program = compile_slots(SlotDraft.model_validate(frame), context, catalogue)
            program = program.model_copy(update={"status": "approved", "approved_by": "benchmark author; manual interpretation"})
            before = run_program(program, initial, graph=to_graph(automatic))
            after = run_program(program, reviewed, graph=graph)
            result.update(before=before, after=after, outcome=after["outcome"], trace=after["trace"],
                          rule=program.model_dump(mode="json"), stage="checked")
        except ValueError as error:
            result.update(stage=getattr(error, "stage", "compile"), blocker=str(error))
        rows.append(result)
    report = {"source": {"publisher": "Author demonstration profile applied to Chief Architect drawing",
                          "sheet": "A-7", "edition": "July 2024 drawing; November 2026 authored profile"},
              "limits": profile["limits"], "requirements": rows,
              "automatic_facts": initial.model_dump(mode="json"), "reviewed_facts": reviewed.model_dump(mode="json"),
              "inventory_attestation": {"reviewer": "benchmark author; no independent review", "scope": profile["scope"],
                    "building_inventory_complete": False, "final_exit_inventory_complete": False},
              "automatic_decisions": sum(r.get("before", {}).get("outcome") in ("SATISFIED", "VIOLATED") for r in rows),
              "reviewed_decisions": sum(r["outcome"] in ("SATISFIED", "VIOLATED") for r in rows)}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "findings.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_report(report, args.output)
    # No partial component is added to these whole-clause counts.
    print(json.dumps({"automatic_decisions": [report["automatic_decisions"], len(rows)],
                      "reviewed_decisions": [report["reviewed_decisions"], len(rows)],
                      "outcomes": {r["id"]: [r["stage"], r["outcome"]] for r in rows}}))


if __name__ == "__main__":
    main()
