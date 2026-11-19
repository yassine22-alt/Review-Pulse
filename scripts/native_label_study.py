"""Four frozen drawing references; native labels name regions, trained primitives supply geometry."""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ["REVIEWPULSE_LABEL_LLM"] = "0"
os.environ["REVIEWPULSE_SHEET_KIND"] = "text"

from shapely.geometry import Point, box
from trained_drawing import score_model

from reviewpulse.annotate.text_classify import classify_items, normalise
from reviewpulse.ingest.pdf_backend import PyMuPdfBackend
from reviewpulse.perception.native_labels import anchor_native_labels
from reviewpulse.pipeline import build_model
from reviewpulse.schema import save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"labels_sha256": hashlib.sha256(args.labels.read_bytes()).hexdigest(),
              "method": "Native text contained in existing regions; original trained LightGBM supplies primitive geometry. No hosted calls, no LLM or new weights.",
              "fallback_limit": "No trained room-use classifier is available; unknown or conflicting names stay unknown. Existing room construction already uses native labels; this pass adds conservative containment/conflict provenance, not a new enclosure algorithm.",
              "limitations": ["Assistant annotations have no independent review.",
                  "Selected visible label points/opening boxes, not complete inventories or polygon-IoU accuracy.",
                  "Review scopes are supplied explicitly, not discovered automatically.",
                  "Inferred label-split boundaries are not confirmed geometry or a basis for confirmed completeness."],
              "drawings": []}
    for reference in labels["drawings"]:
        path = Path(reference["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference["source_sha256"]:
            raise ValueError("drawing differs from frozen reference")
        output = args.output / reference["id"]
        output.mkdir(parents=True, exist_ok=True)
        sheet = PyMuPdfBackend().extract(path, reference["source_page"], reference["id"])
        if reference["scope_bbox_mm"]:
            roi = box(*reference["scope_bbox_mm"])
            sheet.texts = [text for text in sheet.texts if roi.covers(Point(
                (text.bbox[0] + text.bbox[2]) / 2, (text.bbox[1] + text.bbox[3]) / 2))]
            sheet.primitives = [primitive for primitive in sheet.primitives if any(
                roi.covers(Point(point)) for point in primitive.pts) or (
                    primitive.center is not None and roi.covers(Point(primitive.center)))]
        classify_items(sheet.texts)
        model = build_model(sheet, learned=True)
        geometry = "Original trained-vector inference on explicitly reviewed scope"
        trace = anchor_native_labels(model.rooms, model.sheet.texts)
        save(model, output / "building.json")
        score = score_model(model, reference)
        score["rooms_named_correctly"] = [sum(bool(room["matched_id"]) and room["predicted_label"] is not None
            and normalise(room["predicted_label"]) == normalise(room["label"]) for room in score["rooms"]), len(reference["rooms"])]
        score.update(id=reference["id"], geometry=geometry, native_anchor_trace=trace,
                     source_sha256=reference["source_sha256"], style=reference["style"],
                     detected_room_label_texts=sum(text.kind == "room_label" for text in model.sheet.texts),
                     scale=model.sheet.scale.model_dump(), complete_inventory=False)
        report["drawings"].append(score)
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(reference["id"], json.dumps({key: score[key] for key in (
            "rooms_named_correctly", "bedrooms_found_and_classified", "raw_elements", "annotated_opening_hits", "schedules_found")}), flush=True)


if __name__ == "__main__":
    main()
