"""Rule-based raster walls (R13 step 2) - the baseline the learned model is compared against.

Ink = local (Sauvola) OR global (Otsu) darkness, so solid or grey wall fills count as ink, not
just their outlines -> text boxes masked out -> small components removed -> wall thickness t from
the stroke-width mode of thick strokes -> opening with a square kernel of max(3, 0.6 t) removes
thin lines (dimensions, furniture, hatch), closing with the same kernel heals small gaps.
"""

from __future__ import annotations

import numpy as np

from .segment import estimate_wall_thickness_px, wall_thickness_modes

DOOR_IN_WALL_THICKNESSES = 4.5     # a door leaf is ~0.9 m, a wall ~0.2 m


def ink(gray: np.ndarray, sauvola: np.ndarray) -> np.ndarray:
    from skimage.filters import threshold_otsu

    t = threshold_otsu(gray) if gray.min() < gray.max() else 128
    return sauvola | (gray < t)


def wall_mask_rules(binary: np.ndarray, text_boxes_px: list | None = None, min_component_px: int = 60,
                    gray: np.ndarray | None = None):
    import cv2
    from skimage import morphology

    b = ink(gray, binary) if gray is not None else binary.copy()
    for box in text_boxes_px or []:
        x0, y0 = np.floor(box.min(0)).astype(int) - 4
        x1, y1 = np.ceil(box.max(0)).astype(int) + 4
        b[max(y0, 0):y1, max(x0, 0):x1] = False
    b = morphology.remove_small_objects(b, max_size=min_component_px)
    t = estimate_wall_thickness_px(b) or 6.0
    # the opening must spare the thinnest wall class (partitions), not just the dominant one
    modes = wall_thickness_modes(b)
    t_min = min([t] + modes)
    k = max(3, int(round(0.6 * t_min)))
    ker = np.ones((k, k), np.uint8)
    m = cv2.morphologyEx(b.astype(np.uint8), cv2.MORPH_OPEN, ker)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, ker)
    return m.astype(bool), t


def close_doorways(wall: np.ndarray, t_px: float) -> np.ndarray:
    """Barrier for rooms when doors were not recognised: close gaps up to about one door width
    (connectivity is then unknown and rooms are reported without door edges)."""
    import cv2

    k = max(3, int(round(DOOR_IN_WALL_THICKNESSES * t_px)))
    horiz = cv2.morphologyEx(wall.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((1, k), np.uint8))
    vert = cv2.morphologyEx(wall.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((k, 1), np.uint8))
    return (horiz | vert).astype(bool)
