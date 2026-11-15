import random

import numpy as np
import pytest
from PIL import Image

from reviewpulse.ingest.raster_prep import estimate_skew, load_image, prepare, rotate


@pytest.fixture(scope="module")
def plan_png(tmp_path_factory):
    from reviewpulse.synth.make_plan import make_plan

    d = tmp_path_factory.mktemp("r4")
    return make_plan(d, seed=2)["png"]


@pytest.mark.parametrize("angle", [random.Random(i).uniform(-5, 5) for i in range(5)])
def test_deskew_within_0_3_deg(plan_png, angle):
    gray, dpi = load_image(plan_png)
    tilted = rotate(gray, angle)
    page = prepare(tilted, dpi)
    residual = estimate_skew(page.binary)
    assert abs(residual) <= 0.3, (angle, page.skew_deg, residual)


def test_affine_maps_pixels_to_paper_mm(plan_png):
    gray, dpi = load_image(plan_png)
    page = prepare(gray, dpi)
    h = page.gray.shape[0]
    x, y = page.px_to_sheet(0, h)
    assert x == pytest.approx(0) and y == pytest.approx(0)
    x, y = page.px_to_sheet(dpi, h - dpi)      # one inch right and up
    assert x == pytest.approx(25.4) and y == pytest.approx(25.4)


def test_binary_has_ink(plan_png):
    gray, dpi = load_image(plan_png)
    page = prepare(gray, dpi)
    assert 0.005 < page.binary.mean() < 0.3
    assert isinstance(Image.fromarray(np.uint8(page.binary) * 255), Image.Image)
