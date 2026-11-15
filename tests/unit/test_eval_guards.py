"""Evaluation and training fail loudly instead of reporting numbers that mean nothing.

Measured cases (28 Oct 2026): v6 training stopped on Windows because a stale feature chunk was still
open when its recompute replaced it, and the next evaluation, pointed at the missing model, wrote a
report of zeros (every drawing crashed)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _train_script():
    spec = importlib.util.spec_from_file_location("train_primitive_classifier",
                                                  ROOT / "scripts" / "train_primitive_classifier.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stale_feature_chunk_is_replaced(tmp_path, monkeypatch):
    from reviewpulse.perception.learned.features import FEATURES

    tr = _train_script()
    monkeypatch.setattr(tr, "CACHE", tmp_path)
    (tmp_path / "set").mkdir()
    np.savez_compressed(tmp_path / "set" / "000000.npz", X=np.zeros((1, 2)), y=np.zeros(1),
                        features=np.array(["an_older_feature", "another"]))
    fresh = np.ones((3, len(FEATURES)))
    monkeypatch.setattr(tr, "collect", lambda fn, items, workers, tag: (fresh, np.ones(3)))
    X, _ = tr.cached("set", None, [0, 1, 2], workers=1)
    assert X.shape == fresh.shape
    with np.load(tmp_path / "set" / "000000.npz") as z:
        assert list(z["features"]) == list(FEATURES)


def test_a_run_where_every_drawing_crashed_is_not_a_result():
    from reviewpulse.eval.adapters.primitive_scoring import aggregate

    with pytest.raises(RuntimeError, match="all 2 drawings crashed"):
        aggregate([("a", FileNotFoundError("meta.json")), ("b", FileNotFoundError("meta.json"))], True)


def test_learned_method_needs_a_model(tmp_path, monkeypatch):
    from reviewpulse.eval.cli import run_eval

    monkeypatch.setenv("REVIEWPULSE_PRIMITIVE_MODEL", str(tmp_path / "missing"))
    with pytest.raises(SystemExit, match="no primitive model"):
        run_eval("findings", "synth", n=1, method="learned", out_dir=tmp_path)
