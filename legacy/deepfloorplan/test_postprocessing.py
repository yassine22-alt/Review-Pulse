"""Quick test harness for postprocessing.graph_correction.

Usage:
    python test_postprocessing.py <input_floorplan>
"""

import json
from pathlib import Path
import sys

import cv2

from detection.contour_extraction import extract_polygons
from detection.mask_postprocess import postprocess_masks
from geometry.polygon_builder import build_geometries
from model.deepfloorplan_inference import run_deepfloorplan
from postprocessing.graph_correction import run_postprocessing
from preprocessing.input_loader import load_input
from utils.config import CONFIG
from visualization.overlay_renderer import render_overlay


def _extract_all_contours(masks):
    return {name: extract_polygons(mask) for name, mask in masks.items()}


def _convert_violations_for_overlay(violations):
    """Convert postprocessing violations into overlay-compatible ids."""
    converted = []
    room_types = {"MIN_ROOM_AREA", "ROOM_WITHOUT_DOOR"}
    door_types = {"DOOR_NOT_ON_WALL", "DOOR_NOT_CONNECTING_TWO_ROOMS"}

    for violation in violations:
        item = {
            "type": violation.get("type", "VIOLATION"),
            "message": violation.get("message", ""),
        }
        obj_id = int(violation.get("object_id", -1))

        if item["type"] in room_types and obj_id >= 0:
            item["room_id"] = obj_id
        elif item["type"] in door_types and obj_id >= 0:
            item["door_id"] = obj_id

        converted.append(item)

    return converted


def _save_rgb_image(image_rgb, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(output_path), bgr):
        raise RuntimeError(f"Failed to save image at {output_path}")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python test_postprocessing.py <input_floorplan>")
        return 1

    input_path = sys.argv[1]
    output_dir = CONFIG.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    image, _ = load_input(input_path)
    raw_masks = run_deepfloorplan(image)
    masks = postprocess_masks(raw_masks)

    contours_by_type = _extract_all_contours(masks)
    geometries = build_geometries(contours_by_type)

    rooms_before = geometries["rooms"]
    doors_before = geometries["doors"]
    walls = geometries["walls"]

    rooms_after, doors_after, graph, violations = run_postprocessing(
        rooms_before,
        doors_before,
        walls,
    )

    overlay_violations = _convert_violations_for_overlay(violations)
    annotated = render_overlay(
        image=image,
        rooms=rooms_after,
        doors=doors_after,
        walls=walls,
        windows=[],
        violations=overlay_violations,
    )
    annotated_path = output_dir / "postprocessing_annotated_plan.png"
    _save_rgb_image(annotated, annotated_path)

    summary = {
        "before": {
            "rooms": len(rooms_before),
            "doors": len(doors_before),
            "walls": len(walls),
        },
        "after": {
            "rooms": len(rooms_after),
            "doors": len(doors_after),
            "graph_nodes": graph.number_of_nodes(),
            "graph_edges": graph.number_of_edges(),
            "violations": len(violations),
        },
        "sample_violations": violations[:10],
        "artifacts": {
            "postprocessing_annotated_plan": str(annotated_path),
        },
    }

    summary_path = output_dir / "postprocessing_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("Postprocessing test finished")
    print(f"Summary: {summary_path}")
    print(f"Annotated: {annotated_path}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
