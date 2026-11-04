"""Input loading utilities for images and PDF floor plans."""

from pathlib import Path
from typing import Tuple

import cv2
import numpy as np
from pdf2image import convert_from_path


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}


def _load_image_file(file_path: Path) -> np.ndarray:
    """Load an image file with OpenCV in RGB format.

    Args:
        file_path: Path to image file.

    Returns:
        RGB image as a NumPy array.

    Raises:
        ValueError: If OpenCV cannot decode the image.
    """
    bgr = cv2.imread(str(file_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"Unable to load image file: {file_path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _load_pdf_file(file_path: Path, dpi: int = 300) -> np.ndarray:
    """Convert the first page of a PDF into an RGB image.

    Args:
        file_path: Path to PDF file.
        dpi: Conversion resolution to preserve detail.

    Returns:
        RGB image as a NumPy array.

    Raises:
        ValueError: If conversion fails or no pages are found.
    """
    pages = convert_from_path(str(file_path), dpi=dpi)
    if not pages:
        raise ValueError(f"No pages found in PDF: {file_path}")
    first_page = pages[0]
    return np.array(first_page.convert("RGB"))


def load_input(file_path: str) -> Tuple[np.ndarray, Path]:
    """Load a floor plan from image or PDF.

    Args:
        file_path: Path string to floor plan file.

    Returns:
        Tuple of RGB image and normalized Path object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If file extension is unsupported or decoding fails.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix in SUPPORTED_IMAGE_EXTENSIONS:
        return _load_image_file(path), path
    if suffix in SUPPORTED_PDF_EXTENSIONS:
        return _load_pdf_file(path), path

    supported = sorted(SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS)
    raise ValueError(f"Unsupported file extension '{suffix}'. Supported: {supported}")
