# FloorPlan AI Compliance Checker

> Archived original prototype. The maintained application is installed from the repository root
> using `pyproject.toml`; see [the main README](../../README.md). This directory is retained for
> reference and baseline comparisons, not as a second active application.
>
> To run this prototype with existing root-level `store/` weights, stay at the repository root,
> install `legacy/deepfloorplan/requirements.txt` in a separate environment, and run
> `python legacy/deepfloorplan/main.py path/to/plan.png`. The historical instructions below refer
> to the prototype's original layout. `scripts/baseline_run.py` is the evaluation harness.

Minimal, modular Python system that analyzes architectural floor plans with a DeepFloorPlan pretrained model and reports compliance violations.

## Features

- Input formats: PNG, JPG, PDF
- DeepFloorPlan inference (CPU-compatible TensorFlow)
- Detection outputs:
  - rooms
  - walls
  - doors
  - windows
- Compliance checks:
  - minimum room size
  - door not touching wall
  - room without door
  - door not connecting two rooms
- Outputs:
  - `outputs/report.json`
  - `outputs/segmentation_raw.png` (immediately after DeepFloorPlan segmentation)
  - `outputs/annotated_plan.png`
  - `outputs/mask_rooms.png`, `outputs/mask_walls.png`, `outputs/mask_doors.png`, `outputs/mask_windows.png`
  - `outputs/spatial_graph.json`, `outputs/spatial_graph.png`

## Project Structure

```text
floorplan_ai/
  main.py
  model/
    deepfloorplan_inference.py
    model_loader.py
  preprocessing/
    input_loader.py
    image_preprocess.py
  detection/
    mask_postprocess.py
    contour_extraction.py
  geometry/
    polygon_builder.py
    spatial_graph.py
  rules/
    compliance_rules.py
    violation_report.py
  visualization/
    overlay_renderer.py
  utils/
    config.py
  outputs/
```

## Installation

1. Create and activate a virtual environment.

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. If using PDF input, install Poppler and ensure `poppler/bin` is in your PATH.

## DeepFloorPlan Weights Setup

The pretrained weights are **not** in the Git repository (they exceed GitHub's file size limit). Get the `store/` folder from the team's shared drive and unzip it at the project root so you have:

- `store/model` (TensorFlow SavedModel)
- `store/tflite/model.tflite` (TensorFlow Lite)

By default, the code uses `store/model` via `model_path` in `utils/config.py`.

If you want to run TFLite instead, set:

- `model_path = Path("store/tflite/model.tflite")`

Steps:

1. Clone the official repository:

```bash
git clone https://github.com/zlzeng/DeepFloorplan.git
```

2. Follow that repository's instructions to obtain/export pretrained weights.

3. Place/export the model into this project and update `utils/config.py` as needed.

## Usage

```bash
python main.py input/floorplan.png
```

or

```bash
python main.py input/floorplan.pdf
```

Outputs are written to `outputs/`:

- `report.json`
- `segmentation_raw.png`
- `annotated_plan.png`
- `mask_rooms.png`, `mask_walls.png`, `mask_doors.png`, `mask_windows.png`
- `spatial_graph.json`, `spatial_graph.png`

## Report Format

```json
{
  "rooms": [{"room_id": 0, "area": 12345.0, "bbox": {...}}],
  "doors": [{"door_id": 0, "area": 120.0, "bbox": {...}}],
  "windows": [{"window_id": 0, "area": 90.0, "bbox": {...}}],
  "violations": [
    {
      "type": "MIN_ROOM_AREA",
      "room_id": 4,
      "value": 1800.0,
      "threshold": 2500.0,
      "message": "Room area is below minimum threshold"
    }
  ]
}
```

## Extending Rules

Add new rules in `rules/compliance_rules.py`:

1. Implement a private function returning violation dictionaries.
2. Call it from `check_compliance(...)`.
3. Include IDs (`room_id`, `door_id`, etc.) so visualization can mark targets.

## Notes

- The pipeline is CPU-ready by default.
- Thresholds and model channels are configurable in `utils/config.py`.
- If model output channel order differs, adjust `room_channel`, `wall_channel`, `door_channel`, `window_channel`.
- If wall and door masks appear inverted for your checkpoint export, set `swap_wall_door_masks = True` in `utils/config.py`.
- If the model exports only one opening class, `infer_windows_from_openings = True` reuses it for the window mask so windows are visible in intermediate outputs.
- If raw segmentation of doors/windows is good but downstream geometry is weak, keep `use_raw_openings_for_geometry = True`.
- `door_wall_touch_tolerance_px` controls how much geometric tolerance is used for door-wall contact in rules.
- `allow_exterior_doors = True` allows doors on the exterior envelope (one-room + outside) without raising `DOOR_NOT_CONNECTING_TWO_ROOMS`.
