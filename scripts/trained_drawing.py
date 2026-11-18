"""Local-only trained perception on the frozen author-labelled drawing."""
import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

os.environ["REVIEWPULSE_LABEL_LLM"] = "0"
os.environ["REVIEWPULSE_SHEET_KIND"] = "text"
os.environ.setdefault("OMP_NUM_THREADS", "4")

import networkx as nx
import pymupdf
from shapely.geometry import Point, Polygon, box

from reviewpulse.annotate.schedules import find_schedules
from reviewpulse.annotate.text_classify import classify_items
from reviewpulse.ingest.pdf_backend import PyMuPdfBackend
from reviewpulse.pipeline import build_model
from reviewpulse.schema import save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=["vector", "raster"], required=True)
    args = parser.parse_args()
    labels = json.loads(Path("reports/chief-a7-perception-labels.json").read_text())
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest() != labels["source_sha256"]:
        raise ValueError("drawing differs from author labels")
    args.output.mkdir(parents=True, exist_ok=True)
    sheet = PyMuPdfBackend().extract(args.pdf, labels["source_page"], "chief_a7")
    classify_items(sheet.texts)
    if args.mode == "vector":
        model = build_model(sheet, learned=True)
        weight = Path("data/models/primitive_lgbm/model.txt")
        method = "Trained LightGBM vector fusion; no LLM labels"
    else:
        import torch

        from reviewpulse.perception.raster.build import build_raster_model

        torch.set_num_threads(4)
        rendered = args.output / "a7-150dpi.png"
        with pymupdf.open(args.pdf) as pdf:
            pdf[labels["source_page"]].get_pixmap(dpi=150).save(rendered)
        sheet.source_file = str(rendered.resolve())
        model = build_raster_model(sheet, method="model", ocr=False)
        model.schedules, _ = find_schedules(model.sheet)
        weight = Path("data/models/raster_seg/best.pt")
        method = "Trained U-Net raster segmentation at 150 dpi plus automatically extracted native PDF text; no OCR or LLM labels"
    save(model, args.output / "building.json")
    graph = nx.Graph()
    polygons = {room.id: Polygon(room.polygon, room.holes) for room in model.rooms}
    for truth in labels["rooms"]:
        graph.add_node(truth["id"], bipartite=0)
        for predicted, polygon in polygons.items():
            if polygon.covers(Point(truth["point_mm"])):
                graph.add_edge(truth["id"], predicted)
    matched = nx.algorithms.bipartite.maximum_matching(graph, top_nodes={r["id"] for r in labels["rooms"]})
    predicted_by_id = {r.id: r for r in model.rooms}
    rooms = [{**truth, "matched_id": matched.get(truth["id"]),
              "predicted_type": predicted_by_id[matched[truth["id"]]].type if truth["id"] in matched else None}
             for truth in labels["rooms"]]
    openings = []
    for truth in labels["openings"]:
        roi = box(*truth["bbox_mm"])
        ids = [element.id for element in model.elements if element.cls == truth["kind"]
               and len(element.geom) >= 3 and Polygon(element.geom).intersects(roi)]
        openings.append({**truth, "intersecting_predictions": ids})
    result = {"method": method, "model_sha256": hashlib.sha256(weight.read_bytes()).hexdigest(),
              "annotation_limits": labels["annotation"], "opening_scope": labels["opening_scope"],
              "rooms_found": [sum(bool(r["matched_id"]) for r in rooms), len(rooms)],
              "bedrooms_found_and_classified": [sum(bool(r["matched_id"]) and r["predicted_type"] == "bedroom"
                    for r in rooms if r["bedroom"]), sum(r["bedroom"] for r in rooms)],
              "raw_predicted_room_count": len(model.rooms),
              "raw_elements": dict(Counter(e.cls for e in model.elements)),
              "annotated_opening_hits": [sum(bool(o["intersecting_predictions"]) for o in openings), len(openings)],
              "schedules_found": [len(model.schedules), len(labels["schedules"])],
              "schedule_rows": [len(s.get("rows", [])) for s in model.schedules],
              "rooms": rooms, "openings": openings, "warnings": model.sheet.warnings}
    (args.output / "score.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key not in ("rooms", "openings", "warnings")}))


if __name__ == "__main__":
    main()
