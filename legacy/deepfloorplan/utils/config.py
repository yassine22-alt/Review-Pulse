"""Central configuration values for the floor plan compliance pipeline."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration.

    The defaults are intentionally conservative so the system can run on CPU-only
    environments and small/medium floor plan images.
    """

    # Default points to the unzipped pretrained model provided in this workspace.
    model_path: Path = Path("store/model")
    output_dir: Path = Path("outputs")

    # DeepFloorPlan commonly uses square inference sizes.
    model_input_width: int = 512
    model_input_height: int = 512

    # Channel indices used if model output is a single tensor.
    room_channel: int = 0
    wall_channel: int = 1
    door_channel: int = 2
    window_channel: int = 3

    # Binary threshold after sigmoid/softmax-like scores.
    # Slightly lower threshold helps recover weak room regions in this plan.
    mask_threshold: float = 0.35

    # Force swap between wall and door masks when boundary classes appear inverted.
    swap_wall_door_masks: bool = False

    # If the model provides only one opening-like class, reuse it for windows.
    infer_windows_from_openings: bool = True

    # Geometry cleanup thresholds (pixel units).
    # Lower room area filter to avoid dropping small but valid rooms.
    min_room_area: float = 900.0
    min_door_area: float = 25.0
    min_window_area: float = 25.0
    min_wall_area: float = 40.0

    # Preserve fine opening structures by optionally extracting openings from raw masks.
    use_raw_openings_for_geometry: bool = True

    # Rule threshold (same unit as extracted room polygon area).
    min_room_area_rule: float = 2500.0

    # Spatial tolerance to associate doors with room boundaries.
    room_door_buffer_px: float = 10.0
    room_door_max_distance_px: float = 18.0
    room_door_adaptive_distance_scale: float = 0.08

    # Tolerance when checking door-to-wall contact in geometry space.
    door_wall_touch_tolerance_px: float = 6.0

    # Exterior doors are valid even if they connect one room and the outside.
    allow_exterior_doors: bool = True
    exterior_door_boundary_tolerance_px: float = 12.0

    # Visualization seed for deterministic graph layout.
    graph_layout_seed: int = 42


CONFIG = Config()
