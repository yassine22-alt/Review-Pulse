"""Main entrypoint for floor plan compliance analysis."""

import json
from pathlib import Path
import sys
from typing import Dict, List

import cv2
import numpy as np

from detection.contour_extraction import extract_polygons
from detection.mask_postprocess import postprocess_masks
from geometry.polygon_builder import build_geometries
from geometry.spatial_graph import build_spatial_graph, compute_room_door_map
from model.deepfloorplan_inference import run_deepfloorplan
from preprocessing.input_loader import load_input
from rules.compliance_rules import check_compliance
from rules.violation_report import generate_report, save_report
from utils.config import CONFIG
from visualization.overlay_renderer import render_overlay


def _extract_all_contours(masks: Dict[str, object]) -> Dict[str, List]:
    """Extract contour sets for each semantic class mask."""
    return {name: extract_polygons(mask) for name, mask in masks.items()}


def _prepare_masks_for_contour_extraction(
    processed_masks: Dict[str, np.ndarray],
    raw_masks: Dict[str, np.ndarray],
) -> Dict[str, np.ndarray]:
    """Select the most stable mask source per class for geometry extraction."""
    selected = dict(processed_masks)

    if CONFIG.use_raw_openings_for_geometry:
        if "doors" in raw_masks:
            selected["doors"] = raw_masks["doors"]
        if "windows" in raw_masks:
            selected["windows"] = raw_masks["windows"]

    return selected


def _save_annotated_image(image_rgb, output_path: Path) -> None:
    """Persist annotated RGB image as PNG via OpenCV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(output_path), bgr):
        raise RuntimeError(f"Failed to save annotated output to {output_path}")


def _render_segmentation_overlay(image_rgb: np.ndarray, masks: Dict[str, np.ndarray]) -> np.ndarray:
    """Render raw DeepFloorPlan segmentation masks as a colored overlay.

    This output is intentionally generated immediately after model inference,
    before morphological cleanup and contour extraction.
    """
    color_layer = np.zeros_like(image_rgb)
    color_map = {
        "rooms": (255, 0, 0),
        "walls": (0, 0, 0),
        "doors": (0, 255, 0),
        "windows": (0, 255, 255),
    }

    for name, color in color_map.items():
        mask = masks.get(name)
        if mask is None:
            continue
        active = mask > 0
        color_layer[active] = color

    return cv2.addWeighted(image_rgb, 0.7, color_layer, 0.3, 0.0)


def _save_segmentation_outputs(image_rgb: np.ndarray, masks: Dict[str, np.ndarray], output_dir: Path) -> Path:
    """Save intermediate segmentation outputs (overlay + per-class masks)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    segmentation_overlay_path = output_dir / "segmentation_raw.png"
    segmentation_overlay = _render_segmentation_overlay(image_rgb, masks)
    _save_annotated_image(segmentation_overlay, segmentation_overlay_path)

    for name, mask in masks.items():
        mask_path = output_dir / f"mask_{name}.png"
        if not cv2.imwrite(str(mask_path), mask):
            raise RuntimeError(f"Failed to save segmentation mask to {mask_path}")

    return segmentation_overlay_path


def _save_graph_outputs(graph, output_dir: Path) -> Dict[str, Path]:
    """Save graph artifacts for debugging room connectivity."""
    output_dir.mkdir(parents=True, exist_ok=True)

    graph_json_path = output_dir / "spatial_graph.json"
    graph_png_path = output_dir / "spatial_graph.png"

    graph_data = {
        "nodes": [{"room_id": int(node_id)} for node_id in graph.nodes()],
        "edges": [
            {
                "source": int(src),
                "target": int(dst),
                "door_id": int(data.get("door_id", -1)),
            }
            for src, dst, data in graph.edges(data=True)
        ],
    }

    with graph_json_path.open("w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)

    # Local imports keep startup fast when graph visualization is not needed.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import networkx as nx

    plt.figure(figsize=(8, 6))
    if graph.number_of_nodes() == 0:
        plt.text(0.5, 0.5, "No room nodes detected", ha="center", va="center")
        plt.axis("off")
    else:
        pos = nx.spring_layout(graph, seed=CONFIG.graph_layout_seed)
        nx.draw_networkx_nodes(graph, pos, node_color="#4C78A8", node_size=700)
        nx.draw_networkx_edges(graph, pos, edge_color="#2F2F2F", width=2)
        nx.draw_networkx_labels(graph, pos, font_color="white")

        edge_labels = {
            (src, dst): f"d{data.get('door_id', '?')}" for src, dst, data in graph.edges(data=True)
        }
        if edge_labels:
            nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=8)

        plt.title("Room Connectivity Graph")
        plt.axis("off")

    plt.tight_layout()
    plt.savefig(graph_png_path, dpi=150)
    plt.close()

    return {"graph_json": graph_json_path, "graph_png": graph_png_path}


def main() -> int:
    """Execute the end-to-end compliance pipeline."""
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_floorplan.(png|jpg|pdf)>")
        return 1

    input_path = sys.argv[1]
    try:
        image, _ = load_input(input_path)
        raw_masks = run_deepfloorplan(image)

        output_dir = CONFIG.output_dir
        segmentation_path = _save_segmentation_outputs(image, raw_masks, output_dir)

        masks = postprocess_masks(raw_masks)

        contour_masks = _prepare_masks_for_contour_extraction(masks, raw_masks)
        contours_by_type = _extract_all_contours(contour_masks)
        geometries = build_geometries(contours_by_type)

        rooms = geometries["rooms"]
        walls = geometries["walls"]
        doors = geometries["doors"]
        windows = geometries["windows"]

        graph = build_spatial_graph(rooms, doors)
        graph_artifacts = _save_graph_outputs(graph, output_dir)
        violations = check_compliance(rooms, doors, walls)

        room_door_map = compute_room_door_map(
            rooms,
            doors,
            buffer_px=CONFIG.room_door_buffer_px,
            max_distance_px=CONFIG.room_door_max_distance_px,
            adaptive_distance_scale=CONFIG.room_door_adaptive_distance_scale,
        )

        report = generate_report(rooms, doors, windows, violations)
        report["graph"] = {
            "num_rooms": graph.number_of_nodes(),
            "num_connections": graph.number_of_edges(),
            "edges": [
                {
                    "source": int(src),
                    "target": int(dst),
                    "door_id": int(data.get("door_id", -1)),
                }
                for src, dst, data in graph.edges(data=True)
            ],
        }
        report["diagnostics"] = {
            "rooms_with_doors": sum(1 for door_ids in room_door_map.values() if len(door_ids) > 0),
            "rooms_without_doors": sum(1 for door_ids in room_door_map.values() if len(door_ids) == 0),
            "room_door_buffer_px": CONFIG.room_door_buffer_px,
            "room_door_max_distance_px": CONFIG.room_door_max_distance_px,
            "room_door_adaptive_distance_scale": CONFIG.room_door_adaptive_distance_scale,
        }

        report_path = output_dir / "report.json"
        image_path = output_dir / "annotated_plan.png"

        save_report(report, report_path)

        annotated = render_overlay(
            image=image,
            rooms=rooms,
            doors=doors,
            walls=walls,
            windows=windows,
            violations=violations,
        )
        _save_annotated_image(annotated, image_path)

        print(f"Analysis completed: {input_path}")
        print(f"Segmentation: {segmentation_path}")
        print(f"Report: {report_path}")
        print(f"Overlay: {image_path}")
        print(f"Graph JSON: {graph_artifacts['graph_json']}")
        print(f"Graph PNG: {graph_artifacts['graph_png']}")
        return 0
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
