"""Evaluate frozen wall-line faces on vector PDFs and an explicit CAD control."""
import argparse
import hashlib
import json
from pathlib import Path

from trained_drawing import score_model

from reviewpulse.annotate.text_classify import classify_items
from reviewpulse.ingest.dxf_reader import extract_dxf
from reviewpulse.perception.native_labels import anchor_native_labels
from reviewpulse.perception.polygonized import polygonized_regions
from reviewpulse.schema import BuildingModel, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    references = json.loads(args.labels.read_text(encoding="utf-8"))
    report = {"reference_labels_sha256": hashlib.sha256(args.labels.read_bytes()).hexdigest(),
              "limits": ["PDF wall/opening geometry is fixed from the prior trained-vector runs; no tuning.",
                  "DXF is a synthetic control, not a real permit drawing; no real DXF was found locally.",
                  "Only explicit detected opening jambs close gaps. No artificial snap/closing tolerance.",
                  "Centerline faces are not net-area measurements, and no inventory is declared complete.",
                  "Opening subset annotations are incomplete; raw counts are not precision/recall."], "rows": []}
    for reference in references["drawings"]:
        if hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest() != reference["source_sha256"]:
            raise ValueError("source differs from frozen labels")
        if reference["line_source"] == "dxf_layer":
            sheet = extract_dxf(Path(reference["path"]), reference["id"])
            classify_items(sheet.texts)
            lines = [primitive.pts + ([primitive.pts[0]] if primitive.kind == "polygon" else [])
                     for primitive in sheet.primitives if primitive.layer == reference["wall_layer"] and primitive.pts]
            model = BuildingModel(sheet=sheet)
            closures = []
        else:
            model = load(BuildingModel, reference["geometry_model"])
            lines = [element.geom for element in model.elements if element.cls == "wall"]
            closures = [element.attrs["jambs"] for element in model.elements if element.cls in ("door", "window", "opening")
                        and isinstance(element.attrs.get("jambs"), list) and len(element.attrs["jambs"]) == 2]
        model.rooms, diagnostics = polygonized_regions([*lines, *closures], model.sheet.id)
        model.edges = []
        naming = anchor_native_labels(model.rooms, model.sheet.texts)
        result = score_model(model, reference)
        result.update(id=reference["id"], style=reference["style"], polygonize=diagnostics,
                      explicit_opening_closures=len(closures), native_naming=naming,
                      complete_inventory=False, areas_used_for_compliance=False,
                      is_synthetic=reference["line_source"] == "dxf_layer")
        report["rows"].append(result)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(reference["id"], result["reference_label_points_covered"], result["bedrooms_found_and_classified"], flush=True)


if __name__ == "__main__":
    main()
