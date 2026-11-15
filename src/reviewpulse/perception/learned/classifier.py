"""Apply the learned primitive classifier: annotate each primitive with class probabilities.

The model (LightGBM, trained by scripts/train_primitive_classifier.py) reads the features of
``features.sheet_features`` - including what the rule pipeline concluded - and writes
``evidence['p_wall']`` / ``['p_door']`` / ``['p_window']`` on every primitive, plus
``['learned_wall']``: the wall call at the threshold tuned on val (meta.json). The wall pool
(perception/walls.py) then leaves out lines the classifier does not call walls.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from ...schema import BuildingModel
from .features import CLASSES, FEATURES, sheet_features

DEFAULT_DIR = Path(__file__).resolve().parents[4] / "data" / "models" / "primitive_lgbm"
WALL_PROB_MIN = 0.5             # used when the model's meta.json carries no tuned threshold


def model_dir() -> Path:
    return Path(os.environ.get("REVIEWPULSE_PRIMITIVE_MODEL", DEFAULT_DIR))


def available() -> bool:
    return (model_dir() / "model.txt").exists()


@lru_cache(maxsize=2)
def _load(path: str):
    import lightgbm as lgb

    meta = json.loads((Path(path).parent / "meta.json").read_text(encoding="utf-8"))
    missing = [f for f in meta["features"] if f not in FEATURES]
    if missing:
        raise RuntimeError(f"primitive model needs features this code does not compute ({missing}); retrain it")
    # a model trained before features were added reads its own columns, in its own order
    cols = [list(FEATURES).index(f) for f in meta["features"]]
    return lgb.Booster(model_file=path), float(meta.get("wall_threshold", WALL_PROB_MIN)), cols


def wall_threshold() -> float:
    """The installed model's wall threshold (tuned on val)."""
    return _load(str(model_dir() / "model.txt"))[1]


def annotate_primitives(model: BuildingModel) -> int:
    """Write class probabilities on the sheet's primitives; returns how many were scored."""
    booster, t_wall, cols = _load(str(model_dir() / "model.txt"))
    ids, X = sheet_features(model)
    if not ids:
        return 0
    prob = booster.predict(X[:, cols])
    by_id = {p.id: p for p in model.sheet.primitives}
    for pid, row in zip(ids, prob):
        ev = by_id[pid].prov.evidence
        for c, name in enumerate(CLASSES):
            if name != "other":
                ev[f"p_{name}"] = round(float(row[c]), 4)
        ev["learned_wall"] = bool(row[CLASSES.index("wall")] >= t_wall)     # tuned on val
        ev["learned_class"] = CLASSES[int(row.argmax())]
    return len(ids)
