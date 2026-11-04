"""Raster path (R13) without a GPU: geometry helpers, rule baseline, adapters, optional model."""

import json
from pathlib import Path

import numpy as np
import pytest

from reviewpulse.perception.raster.vectorize import mask_polygons, skeleton_branches

DATA = Path(__file__).parents[2] / "data"


def test_skeleton_L_is_one_bent_branch_and_T_splits_at_the_junction():
    from shapely.geometry import LineString
    from skimage.morphology import skeletonize

    m = np.zeros((60, 60), bool)
    m[10:50, 10:14] = True       # vertical arm
    m[46:50, 10:50] = True       # horizontal arm
    br = skeleton_branches(skeletonize(m))
    assert len(br) == 1
    assert len(LineString(br[0]).simplify(1.5).coords) == 3      # two straight segments
    t = np.zeros((60, 60), bool)
    t[10:14, 5:55] = True        # bar
    t[10:55, 28:32] = True       # stem
    assert len(skeleton_branches(skeletonize(t))) == 3


def test_mask_polygon_keeps_holes():
    m = np.zeros((40, 40), bool)
    m[5:35, 5:35] = True
    m[15:25, 15:25] = False
    g = mask_polygons(m)
    assert abs(g.area - (900 - 100)) < 60


def test_rule_baseline_builds_rooms_on_a_solid_wall_scan(tmp_path):
    from reviewpulse.ingest.classify import inspect_file
    from reviewpulse.pipeline import build_model, extract_stub
    from reviewpulse.synth.random_plan import random_plan

    p = random_plan(tmp_path, seed=11, png=True, scheme="aia", wall_style="filled", door_style="arc_leaf",
                    angle=0.0, units="m", clutter=False)
    stub = inspect_file(p["png"])[0]
    assert stub.mode == "raster"
    from reviewpulse.perception.raster.build import build_raster_model

    sheet = extract_stub(stub, tmp_path, preview=False)
    m = build_raster_model(sheet, method="rules", ocr=False)
    truth = json.loads(Path(p["truth"]).read_text())
    assert m.tier in ("T2", "T3")                      # a scan is never T1
    assert len(m.rooms) >= 0.6 * len(truth["rooms"])
    assert any(e.cls == "wall" for e in m.elements)
    assert build_model is not None                     # the pipeline routes raster sheets here


def test_two_wall_classes_are_both_found():
    from reviewpulse.perception.raster.segment import wall_thickness_modes

    m = np.zeros((400, 400), bool)
    m[20:44, 20:380] = True       # exterior 24 px, long
    m[356:380, 20:380] = True
    m[20:380, 20:44] = True
    m[20:380, 356:380] = True
    m[44:356, 196:206] = True     # partition 10 px
    m[196:206, 44:196] = True
    for y in range(60, 340, 20):  # thin line work (1 px)
        m[y, 220:340] = True
    modes = wall_thickness_modes(m)
    assert len(modes) == 2 and abs(modes[0] - 10) <= 2 and abs(modes[1] - 24) <= 3


@pytest.mark.skipif(not (DATA / "raw" / "cubicasa5k" / "cubicasa5k" / "test.txt").exists(),
                    reason="CubiCasa5K not downloaded")
def test_cubicasa_adapter_parses_walls_doors_windows_rooms():
    from reviewpulse.eval.adapters.cubicasa import masks, parse, split_ids

    plan = parse(split_ids(DATA, "test")[0])
    assert plan.walls and plan.doors and plan.windows and plan.rooms
    m = masks(plan, 0.25)
    assert set(np.unique(m)) <= {0, 1, 2, 3} and (m == 1).sum() > 0


@pytest.mark.slow                       # loads the GPU model; on Windows that maps best.pt
def test_model_path_if_trained(tmp_path):
    from reviewpulse.perception.raster.segment import model_available

    if not model_available():
        pytest.skip("no trained raster model in data/models/raster_seg")
    pytest.importorskip("torch")
    from reviewpulse.perception.raster.segment import predict

    g = np.full((256, 256), 255, np.uint8)
    g[40:50, 20:230] = 0
    prob, cls, _ = predict(g, None)
    assert prob.shape[1:] == g.shape and cls.shape == g.shape
    from reviewpulse.perception.raster.segment import predict_refined

    _p, cls2, s, t = predict_refined(g, g < 128)
    assert cls2.shape == g.shape and s > 0


def test_ocr_dedupe_prefers_the_pass_where_text_was_upright():
    from reviewpulse.ingest.ocr import Word, _dedupe

    box = np.array([[10, 10], [60, 10], [60, 22], [10, 22]], float)
    turned = Word("10,12", 0.99, box, angle=90.0, upright=False)    # tall box read in the 90 deg pass
    upright = Word("10,12", 0.95, box + 0.5, angle=0.0, upright=True)
    kept = _dedupe([turned, upright])
    assert len(kept) == 1 and kept[0].angle == 0.0
