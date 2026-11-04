"""R4 - Raster preparation (scans, photos, raster PDF pages).

render (<= ~10,000 px per side) -> grey -> Sauvola binarisation -> deskew from the
dominant direction of long line segments (0.3-15 deg) -> pixel-to-sheet affine
so detections map back to paper millimetres (y up). Rotations by 90 deg multiples
come from text direction (OCR, R13) and are applied with ``rotate90``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAUVOLA_WINDOW = 25
DESKEW_MIN, DESKEW_MAX = 0.3, 15.0
MAX_SIDE_PX = 10000


@dataclass
class RasterPage:
    gray: np.ndarray          # uint8, 0 = ink
    binary: np.ndarray        # bool, True = ink
    dpi: float
    skew_deg: float
    affine: list[float]       # [a, b, c, d, e, f]: x_mm = a*px + b*py + c ; y_mm = d*px + e*py + f

    def px_to_sheet(self, px: float, py: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.affine
        return (a * px + b * py + c, d * px + e * py + f)


def render_pdf_page(path: Path, page_no: int) -> tuple[np.ndarray, float]:
    import pymupdf

    page = pymupdf.open(path)[page_no]
    longest_in = max(page.rect.width, page.rect.height) / 72
    dpi = min(300, math.floor(MAX_SIDE_PX / longest_in))
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
    return arr, float(dpi)


def load_image(path: Path, default_dpi: float = 300) -> tuple[np.ndarray, float]:
    from PIL import Image

    with Image.open(path) as im:
        dpi = float(im.info.get("dpi", (default_dpi,))[0] or default_dpi)
        return np.asarray(im.convert("L")).copy(), dpi


def binarise(gray: np.ndarray, window: int = SAUVOLA_WINDOW) -> np.ndarray:
    from skimage.filters import threshold_sauvola

    w = window if window % 2 else window + 1
    return gray < threshold_sauvola(gray, window_size=w)


def estimate_skew(binary: np.ndarray) -> float:
    """Dominant line angle modulo 90 deg, from segments longer than 5% of the width."""
    import cv2

    h, w = binary.shape
    img = (binary.astype(np.uint8)) * 255
    lines = cv2.HoughLinesP(img, 1, np.pi / 720, threshold=80, minLineLength=int(0.05 * w), maxLineGap=4)
    if lines is None:
        return 0.0
    angs, wts = [], []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        a = math.degrees(math.atan2(-(y2 - y1), x2 - x1))       # y up
        a = ((a + 45) % 90) - 45                                 # fold to (-45, 45]
        angs.append(a)
        wts.append(math.hypot(x2 - x1, y2 - y1))
    hist, edges = np.histogram(angs, bins=360, range=(-45, 45), weights=wts)
    k = int(np.argmax(hist))
    sel = [(a, wt) for a, wt in zip(angs, wts) if edges[max(k - 1, 0)] <= a <= edges[min(k + 2, 360)]]
    return float(sum(a * wt for a, wt in sel) / sum(wt for _, wt in sel)) if sel else 0.0


def rotate(gray: np.ndarray, deg: float) -> np.ndarray:
    """Rotate counter-clockwise by ``deg`` keeping the whole page (white fill)."""
    from PIL import Image

    return np.asarray(Image.fromarray(gray).rotate(deg, expand=True, fillcolor=255, resample=Image.BICUBIC))


def rotate90(page: RasterPage, k: int) -> RasterPage:
    g = np.rot90(page.gray, k).copy()
    return _finish(g, page.dpi, page.skew_deg)


def _finish(gray: np.ndarray, dpi: float, skew: float) -> RasterPage:
    mm = 25.4 / dpi
    h = gray.shape[0]
    return RasterPage(gray=gray, binary=binarise(gray), dpi=dpi, skew_deg=skew,
                      affine=[mm, 0.0, 0.0, 0.0, -mm, h * mm])


def prepare(gray: np.ndarray, dpi: float) -> RasterPage:
    b = binarise(gray)
    skew = estimate_skew(b)
    if DESKEW_MIN <= abs(skew) <= DESKEW_MAX:
        gray = rotate(gray, -skew)
    else:
        skew = 0.0 if abs(skew) < DESKEW_MIN else skew
    return _finish(gray, dpi, skew)


def save_debug(page: RasterPage, out_dir: Path, index: int = 0) -> None:
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(page.gray).save(out_dir / f"page_gray_{index}.png")
    Image.fromarray((~page.binary).astype(np.uint8) * 255).save(out_dir / f"page_bin_{index}.png")
