"""E2 - FloorPlanCAD adapter and per-primitive / per-instance scoring.

Ground truth comes from the SVG annotations (``semanticId`` / ``instanceId``) that the SVG reader
keeps in ``prov.evidence['gt']``; the pipeline itself never reads them. Scoring is shared with the
other primitive-labelled datasets (primitive_scoring.py).
Scale: ``oracle`` uses the dataset's 0.1 m per unit (verified from door radii: median 8.78 units);
``estimated`` lets the pipeline recover it (door-symbol prior, tier T3).
"""

from __future__ import annotations

import json
from pathlib import Path

from ...schema import Scale
from .primitive_scoring import aggregate, score_model

CLASSES = {1: "single door", 2: "double door", 3: "sliding door", 4: "folding door", 5: "revolving door",
           6: "rolling door", 7: "window", 8: "bay window", 9: "blind window", 10: "opening symbol",
           11: "sofa", 12: "bed", 13: "chair", 14: "table", 15: "TV cabinet", 16: "wardrobe", 17: "cabinet",
           18: "gas stove", 19: "sink", 20: "refrigerator", 21: "air conditioner", 22: "bath", 23: "bath tub",
           24: "washing machine", 25: "squat toilet", 26: "urinal", 27: "toilet", 28: "stairs", 29: "elevator",
           30: "escalator", 31: "row chairs", 32: "parking spot", 33: "wall", 34: "curtain wall", 35: "railing"}
GROUPS = {"wall": {33}, "door": {1, 2, 3, 4, 5, 6}, "window": {7, 8, 9}}
UNIT_M = 0.1


def write_mapping(root: Path) -> Path:
    p = root / "data" / "mappings" / "floorplancad_classes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"classes": CLASSES, "groups": {k: sorted(v) for k, v in GROUPS.items()},
                             "unit_m": UNIT_M, "note": "class ids checked against geometry: ids 1-2 arc-heavy "
                             "(doors), 33 straight lines (walls); unit from median door radius 8.78 -> 0.88 m"},
                            indent=1), encoding="utf-8")
    return p


def score_file(svg: Path, scale_mode: str = "oracle", learned: bool = False) -> dict:
    from ...annotate.text_classify import classify_items
    from ...ingest.svg_reader import extract_svg
    from ...pipeline import build_model

    sheet = extract_svg(svg, svg.stem)
    classify_items(sheet.texts)
    if scale_mode == "oracle":
        sheet.scale = Scale(metres_per_unit=UNIT_M, method="user", confidence=1.0)
    return score_model(build_model(sheet, learned=learned), GROUPS, learned)


def run(n: int, split: str, data_dir: Path, scale_mode: str = "oracle", learned: bool = False) -> tuple[dict, list]:
    files = sorted((data_dir / "raw" / "floorplancad" / "FloorPlanCAD" / split).glob("*.svg"))
    if not files:
        raise NotImplementedError("FloorPlanCAD not found: python scripts/fetch_datasets.py floorplancad")
    step = max(1, len(files) // n)
    files = files[::step][:n]                      # spread over the split, deterministic
    results = []
    for f in files:
        try:
            results.append((f.name, score_file(f, scale_mode, learned)))
        except Exception as e:  # noqa: BLE001 - a crash is a result
            results.append((f.name, e))
    out, worst = aggregate(results, learned)
    scaled = out.pop("_scaled")
    out = {"split": split, "scale_mode": scale_mode, **out}
    if scale_mode != "oracle":
        out["scale_estimated_on"] = f"{scaled}/{len(files)} tiles"
    return out, worst
