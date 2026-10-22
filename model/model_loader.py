"""TensorFlow model loading for DeepFloorPlan."""

from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf


class ModelLoadError(RuntimeError):
    """Raised when DeepFloorPlan model cannot be loaded."""


class TFLiteModelWrapper:
    """Callable wrapper around a TensorFlow Lite interpreter."""

    def __init__(self, model_path: Path) -> None:
        self.interpreter = tf.lite.Interpreter(model_path=str(model_path))
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    def __call__(self, input_tensor: np.ndarray) -> Any:
        """Run TFLite inference and return raw output tensor or list."""
        input_detail = self.input_details[0]
        input_data = input_tensor.astype(input_detail["dtype"])
        self.interpreter.set_tensor(input_detail["index"], input_data)
        self.interpreter.invoke()

        outputs = [self.interpreter.get_tensor(detail["index"]) for detail in self.output_details]
        if len(outputs) == 1:
            return outputs[0]
        return outputs


def load_deepfloorplan_model(model_path: Path) -> Any:
    """Load DeepFloorPlan weights from a SavedModel or Keras file.

    Args:
        model_path: Path to model folder or file.

    Returns:
        Loaded TensorFlow model object.

    Raises:
        ModelLoadError: If loading fails.
    """
    if not model_path.exists():
        raise ModelLoadError(
            f"DeepFloorPlan model path does not exist: {model_path}. "
            "Please download pretrained weights and update utils/config.py."
        )

    try:
        if model_path.suffix.lower() == ".tflite":
            return TFLiteModelWrapper(model_path)
        if model_path.is_dir():
            return tf.saved_model.load(str(model_path))
        return tf.keras.models.load_model(str(model_path), compile=False)
    except Exception as exc:  # pragma: no cover - defensive guard.
        raise ModelLoadError(f"Failed to load model from {model_path}: {exc}") from exc
