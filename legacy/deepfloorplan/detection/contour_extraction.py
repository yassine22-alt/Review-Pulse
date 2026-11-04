"""Contour extraction from segmentation masks."""

from typing import List

import cv2
import numpy as np


def extract_polygons(mask: np.ndarray) -> List[np.ndarray]:
    """Extract polygon-like contours from a binary mask.

    Args:
        mask: Binary image where foreground pixels are non-zero.

    Returns:
        List of contour arrays approximated as polygons.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    polygons: List[np.ndarray] = []
    for contour in contours:
        epsilon = 0.005 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if approx.shape[0] >= 3:
            polygons.append(approx)

    return polygons
