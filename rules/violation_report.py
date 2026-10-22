"""Structured report generation for detections and violations."""

import json
from pathlib import Path
from typing import Dict, List, Sequence

from shapely.geometry import Polygon


def _bbox(poly: Polygon) -> Dict[str, float]:
    minx, miny, maxx, maxy = poly.bounds
    return {
        "min_x": float(minx),
        "min_y": float(miny),
        "max_x": float(maxx),
        "max_y": float(maxy),
    }


def _serialize_polygons(name: str, polygons: Sequence[Polygon]) -> List[Dict[str, object]]:
    serialized: List[Dict[str, object]] = []
    id_key = f"{name[:-1]}_id" if name.endswith("s") else "id"

    for idx, poly in enumerate(polygons):
        serialized.append(
            {
                id_key: idx,
                "area": float(poly.area),
                "bbox": _bbox(poly),
            }
        )

    return serialized


def generate_report(
    rooms: Sequence[Polygon],
    doors: Sequence[Polygon],
    windows: Sequence[Polygon],
    violations: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    """Build a JSON-serializable report dictionary."""
    return {
        "rooms": _serialize_polygons("rooms", rooms),
        "doors": _serialize_polygons("doors", doors),
        "windows": _serialize_polygons("windows", windows),
        "violations": list(violations),
    }


def save_report(report: Dict[str, object], output_path: Path) -> None:
    """Write report dictionary as formatted JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
