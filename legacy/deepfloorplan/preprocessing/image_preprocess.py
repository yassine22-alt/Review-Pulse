"""Image preprocessing helpers for DeepFloorPlan inference."""

from typing import Dict

import cv2
import numpy as np


def preprocess_image(image: np.ndarray, target_width: int, target_height: int) -> Dict[str, np.ndarray]:
    """Resize and normalize input image for model inference.

    Args:
        image: RGB image array.
        target_width: Model input width.
        target_height: Model input height.

    Returns:
        Dictionary containing model input tensor and metadata.
    """
    original_height, original_width = image.shape[:2]

    resized = cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)
    normalized = resized.astype(np.float32) / 255.0

    # Batch dimension for TensorFlow model prediction.
    batched = np.expand_dims(normalized, axis=0)

    return {
        "input_tensor": batched,
        "original_size": np.array([original_width, original_height], dtype=np.int32),
        "model_size": np.array([target_width, target_height], dtype=np.int32),
    }
