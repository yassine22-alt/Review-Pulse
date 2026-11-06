"""The stair finder: found with the right numbers, nothing found where there is no stair, no scale means no stairs."""

import pytest

from reviewpulse.perception.stairs import find_stairs
from reviewpulse.xeval.stairgen import make_case


def test_a_drawn_flight_is_found_with_its_true_tread_depth():
    found = 0
    for seed in range(12):
        case = make_case(seed, True)
        stairs = find_stairs(case.sheet, case.mpu)
        hit = [s for s in stairs if abs(s.prov.evidence["width_m"] - case.width) < 0.25 * case.width + 0.05]
        if hit:
            found += 1
            best = max(hit, key=lambda s: s.prov.evidence["n_levels"])
            assert abs(best.prov.evidence["tread_depth_m"] - case.pitch) < 0.01
            assert best.prov.evidence["steps_min"] <= case.treads <= best.prov.evidence["steps_max"] + 1
    assert found >= 10          # measured 98% on 200 cases; a handful of cases keeps this test fast


def test_no_scale_means_no_stairs():
    case = make_case(3, True)
    assert find_stairs(case.sheet, None) == []


def test_clutter_without_a_stair_is_not_a_stair():
    false = sum(bool(find_stairs((c := make_case(s, False)).sheet, c.mpu)) for s in range(1000, 1030))
    assert false <= 3           # measured 3% on 200 cases


def test_trace_says_why_a_candidate_was_rejected():
    case = make_case(1001, False)
    trace: list[str] = []
    find_stairs(case.sheet, case.mpu, trace)
    assert all(isinstance(t, str) for t in trace)


@pytest.mark.parametrize("style", [[], ["nosing"], ["broken"], ["stringers"]])
def test_every_drawing_style_of_an_isolated_flight_is_found(style):
    import math
    import random

    from reviewpulse.schema import Sheet
    from reviewpulse.xeval.stairgen import _Draw, _flight

    ok = 0
    for s in range(10):
        rng = random.Random(s)
        d = _Draw(0.01)
        _flight(d, rng, (5, 5), rng.uniform(0, math.pi), 0.27, 1.2, 9, style, 0.0)
        sheet = Sheet(id="x", source_file="s", mode="vector", coord_unit="drawing_unit", width=1, height=1,
                      primitives=d.prims)
        ok += bool(find_stairs(sheet, 0.01))
    assert ok == 10
