"""Inference wrapper around DeepFloorPlan outputs."""

from typing import Any, Dict

import cv2
import numpy as np
import tensorflow as tf

from model.model_loader import load_deepfloorplan_model
from preprocessing.image_preprocess import preprocess_image
from utils.config import CONFIG


def _to_numpy(value: Any) -> np.ndarray:
    """Convert TensorFlow values to NumPy arrays."""
    if isinstance(value, tf.Tensor):
        return value.numpy()
    return np.asarray(value)


def _extract_mask_channels(prediction: Any) -> Dict[str, np.ndarray]:
    """Normalize various model output formats into named masks.

    Supports:
    - dict outputs containing room/wall/door/window-like keys
    - list/tuple outputs where first tensor contains channels
    - single tensor output with channels on last axis
    """
    if isinstance(prediction, dict):
        lowered = {k.lower(): _to_numpy(v) for k, v in prediction.items()}

        # First, try semantic keys directly if present.
        def _pick(substring: str) -> np.ndarray | None:
            for key, value in lowered.items():
                if substring in key:
                    return value
            return None

        room = _pick("room")
        wall = _pick("wall")
        door = _pick("door")
        window = _pick("window")

        # Fallback for common DeepFloorPlan exported models where outputs are named
        # generically (e.g., output_1 and output_2).
        if room is None or wall is None or door is None:
            tensors = []
            for value in lowered.values():
                arr = value
                if arr.ndim == 4:
                    arr = arr[0]
                if arr.ndim != 3:
                    continue
                tensors.append(arr)

            if len(tensors) < 1:
                raise ValueError("Model output dictionary did not contain 3D/4D tensors")

            # The tensor with more channels is typically room classes
            # (e.g., 9 channels), while the smaller tensor is boundary classes
            # (e.g., background, wall, opening).
            tensors = sorted(tensors, key=lambda t: t.shape[-1], reverse=True)
            room_head = tensors[0]
            boundary_head = tensors[1] if len(tensors) > 1 else None

            if room_head.shape[-1] > 1:
                room = (np.argmax(room_head, axis=-1) != 0).astype(np.float32)
            else:
                room = np.squeeze(room_head[..., 0]).astype(np.float32)

            if boundary_head is not None and boundary_head.shape[-1] >= 3:
                # Decode mutually-exclusive boundary classes with argmax to avoid
                # overlapping wall/door masks from per-channel thresholding.
                boundary_class = np.argmax(boundary_head, axis=-1)

                # Non-background classes are typically wall/opening. We map the
                # larger class to wall and the smaller class to door to handle
                # exported models where channel semantics can appear swapped.
                candidate_classes = list(range(1, boundary_head.shape[-1]))
                class_sizes = {
                    cls: int(np.sum(boundary_class == cls)) for cls in candidate_classes
                }
                sorted_classes = sorted(class_sizes.items(), key=lambda x: x[1], reverse=True)

                wall_class = sorted_classes[0][0] if sorted_classes else 1
                opening_classes = [cls for cls, _ in sorted_classes[1:]]

                wall = (boundary_class == wall_class).astype(np.float32)

                if len(opening_classes) >= 2:
                    # If two opening-like classes exist, treat one as door and one as window.
                    door = (boundary_class == opening_classes[0]).astype(np.float32)
                    window = (boundary_class == opening_classes[1]).astype(np.float32)
                elif len(opening_classes) == 1:
                    opening_mask = (boundary_class == opening_classes[0]).astype(np.float32)
                    door = opening_mask
                    # Many DeepFloorPlan exports merge door/window as one opening class.
                    # Reusing openings for windows gives a visible window mask for debugging.
                    if CONFIG.infer_windows_from_openings:
                        window = opening_mask.copy()
                    else:
                        window = np.zeros_like(opening_mask, dtype=np.float32)
                else:
                    door = np.zeros_like(wall, dtype=np.float32)
                    window = np.zeros_like(wall, dtype=np.float32)
            elif boundary_head is not None and boundary_head.shape[-1] == 2:
                boundary_class = np.argmax(boundary_head, axis=-1)
                wall = (boundary_class == 1).astype(np.float32)
                door = np.zeros_like(wall, dtype=np.float32)
                window = np.zeros_like(door, dtype=np.float32)
            else:
                wall = np.zeros_like(room, dtype=np.float32)
                door = np.zeros_like(room, dtype=np.float32)
                window = np.zeros_like(room, dtype=np.float32)

        if window is None:
            window = np.zeros_like(np.squeeze(door), dtype=np.float32)
    else:
        if isinstance(prediction, (list, tuple)):
            prediction = prediction[0]

        tensor = _to_numpy(prediction)
        if tensor.ndim == 4:
            tensor = tensor[0]
        if tensor.ndim != 3 or tensor.shape[-1] < 4:
            raise ValueError(
                "Unexpected model output shape. Expected [..., H, W, >=4 channels] "
                f"but received {tensor.shape}."
            )

        room = tensor[..., CONFIG.room_channel]
        wall = tensor[..., CONFIG.wall_channel]
        door = tensor[..., CONFIG.door_channel]
        window = tensor[..., CONFIG.window_channel]

    return {
        "rooms": np.squeeze(room),
        "walls": np.squeeze(wall),
        "doors": np.squeeze(door),
        "windows": np.squeeze(window),
    }


def _resize_mask(mask: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize probability mask to original image size."""
    return cv2.resize(mask.astype(np.float32), (width, height), interpolation=cv2.INTER_LINEAR)


def run_deepfloorplan(image: np.ndarray) -> Dict[str, np.ndarray]:
    """Run DeepFloorPlan inference and return binary masks.

    Args:
        image: RGB floor plan image.

    Returns:
        Dictionary with binary masks for rooms, walls, doors, windows.

    Raises:
        RuntimeError: If inference fails.
    """
    prep = preprocess_image(image, CONFIG.model_input_width, CONFIG.model_input_height)
    input_tensor = prep["input_tensor"]
    original_width, original_height = prep["original_size"]

    try:
        model = load_deepfloorplan_model(CONFIG.model_path)

        # Handle SavedModel signatures, Keras models, and TFLite wrappers uniformly.
        if hasattr(model, "signatures") and "serving_default" in model.signatures:
            infer_fn = model.signatures["serving_default"]
            raw_prediction = infer_fn(tf.convert_to_tensor(input_tensor))
        elif hasattr(model, "signatures") and len(model.signatures) > 0:
            first_signature = next(iter(model.signatures.values()))
            raw_prediction = first_signature(tf.convert_to_tensor(input_tensor))
        elif callable(model):
            try:
                raw_prediction = model(input_tensor, training=False)
            except TypeError:
                raw_prediction = model(input_tensor)
        else:
            raise TypeError("Loaded model object is not callable")

        channel_masks = _extract_mask_channels(raw_prediction)

        resized = {
            key: _resize_mask(mask, int(original_width), int(original_height))
            for key, mask in channel_masks.items()
        }

        if CONFIG.swap_wall_door_masks:
            resized["walls"], resized["doors"] = resized["doors"], resized["walls"]

        # Binarize mask values for deterministic contour extraction.
        binary = {
            key: (mask >= CONFIG.mask_threshold).astype(np.uint8) * 255
            for key, mask in resized.items()
        }
        return binary
    except Exception as exc:
        raise RuntimeError(f"DeepFloorPlan inference failed: {exc}") from exc
