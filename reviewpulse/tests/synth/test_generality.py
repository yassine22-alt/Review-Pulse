"""Generality: randomised plans (rotation, units, layer schemes, wall and door styles)."""

import json
from pathlib import Path

import pytest

from reviewpulse.eval.perception import score_plan
from reviewpulse.synth.random_plan import random_plan

STYLES = [
    dict(scheme="none", wall_style="filled", door_style="segments", angle=0.0, units="mm"),
    dict(scheme="numeric", wall_style="hatched", door_style="block", angle=17.0, units="m"),
    dict(scheme="fr", wall_style="polylines", door_style="bulge", angle=-33.0, units="mm"),
    dict(scheme="aia", wall_style="lines", door_style="arc_only", angle=90.0, units="m"),
]


@pytest.mark.parametrize("fmt", ["dxf", "pdf"])
@pytest.mark.parametrize("i,style", list(enumerate(STYLES)))
def test_random_plan_rooms_and_doors(tmp_path, fmt, i, style):
    p = random_plan(tmp_path, seed=700 + i, **style)
    t = json.loads(Path(p["truth"]).read_text())
    r = score_plan(p, t, fmt)
    tp, npred, ntrue = r["rooms"]
    assert tp == ntrue == npred, r
    tp, npred, ntrue = r["edges"]
    assert tp >= 0.9 * ntrue and tp >= 0.9 * npred, r
    assert r["walls"][0] > 0.95 and r["walls"][1] > 0.95, r


@pytest.mark.slow
@pytest.mark.parametrize("seed", range(5000, 5030))
def test_random_plan_sweep(tmp_path, seed):
    p = random_plan(tmp_path, seed=seed)
    t = json.loads(Path(p["truth"]).read_text())
    r = score_plan(p, t, "dxf")
    assert r["rooms"][0] == r["rooms"][2], r
