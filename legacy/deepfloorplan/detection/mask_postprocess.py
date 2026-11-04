"""Mask cleanup utilities."""

from typing import Dict

import cv2
import numpy as np


def clean_binary_mask(mask: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """Apply opening/closing to reduce noise in binary masks."""
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel)
    return closed


def _clean_room_mask(room_mask: np.ndarray, wall_mask: np.ndarray | None) -> np.ndarray:
    """Clean room mask while preserving separation between adjacent rooms.

    We avoid aggressive closing for rooms because it can bridge thin wall gaps and
    merge many rooms into one giant component.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(room_mask, cv2.MORPH_OPEN, kernel)

    if wall_mask is not None:
        wall_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        wall_band = cv2.dilate(wall_mask, wall_kernel, iterations=1)
        cleaned = cv2.bitwise_and(cleaned, cv2.bitwise_not(wall_band))

    return cleaned


def postprocess_masks(masks: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Clean masks with class-specific morphology to preserve openings."""
    processed: Dict[str, np.ndarray] = {}

    for name, mask in masks.items():
        if name == "rooms":
            # Room-specific cleanup is handled below.
            continue
        if name == "walls":
            # Walls benefit from closing to bridge small gaps.
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            processed[name] = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        elif name in {"doors", "windows"}:
            # Openings are often thin/small; avoid aggressive opening.
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            processed[name] = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        else:
            processed[name] = clean_binary_mask(mask)

    if "rooms" in masks:
        processed["rooms"] = _clean_room_mask(
            room_mask=masks["rooms"],
            wall_mask=processed.get("walls"),
        )

    return processed
