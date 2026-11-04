"""Every input type through `rp check` (reviewpulse.eval.acceptance). Vector cases run in the fast
suite; scans need the trained model and OCR (~minutes per page) and are marked slow."""

import pytest

from reviewpulse.eval.acceptance import CASES, run_case


@pytest.mark.parametrize("case", [pytest.param(c, id=c.name, marks=[pytest.mark.slow] if c.kind == "raster" else [])
                                  for c in CASES])
def test_acceptance(case, tmp_path):
    if case.kind == "raster":
        from reviewpulse.ingest.ocr import available_backends
        from reviewpulse.perception.raster.segment import model_available

        if not (model_available() and available_backends()):
            pytest.skip("raster model or OCR not installed")
    r = run_case(case, tmp_path, env={"REVIEWPULSE_LABEL_LLM": "0"})
    assert r["ok"], r["problems"]
