import json
from pathlib import Path

import numpy as np
import pytest

from reviewpulse.perception.learned import features
from reviewpulse.schema import BuildingModel


@pytest.mark.parametrize("batch_size", [1, 2, 128])
def test_batched_features_match_frozen_pre_change_values(monkeypatch, batch_size):
    reference = json.loads((Path(__file__).parents[1] / "fixtures/feature_batch_reference.json").read_text())
    monkeypatch.setattr(features, "FEATURE_BATCH_SIZE", batch_size)
    ids, matrix = features.sheet_features(BuildingModel.model_validate(reference["model"]))
    assert ids == reference["ids"] and features.FEATURES == reference["features"]
    np.testing.assert_array_equal(matrix, np.asarray(reference["values"], dtype=np.float32))
