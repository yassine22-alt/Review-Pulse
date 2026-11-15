import pytest
from hypothesis import given
from hypothesis import strategies as st

from reviewpulse.engine.policy import Raw, compare, decide


@pytest.mark.parametrize("raw,tier,kw,verdict", [
    (Raw(["x"], None, missing=["scale"]), "T1", {}, "NOT_EVALUATED"),
    (Raw(["x"], False), "T1", {}, "PASS"),
    (Raw(["x"], True, beyond_band=False), "T1", {}, "WARNING"),
    (Raw(["x"], True), "T1", {"guidance": True}, "WARNING"),
    (Raw(["x"], True), "T1", {}, "FAIL"),
    (Raw(["x"], True), "T2", {"all_confirmed": True}, "FAIL"),
    (Raw(["x"], True), "T2", {"all_confirmed": False}, "WARNING"),
    (Raw(["x"], True, metric=True), "T3", {}, "WARNING"),
    (Raw(["x"], True, metric=True), "T1", {"scale_verified": False}, "WARNING"),
    (Raw(["x"], True), "T1", {"max_verdict": "WARNING"}, "WARNING"),
])
def test_policy_table(raw, tier, kw, verdict):
    args = {"guidance": False, **kw}
    assert decide(raw, tier, **args).verdict == verdict


@given(violated=st.booleans(), beyond=st.booleans(), confirmed=st.booleans(), guidance=st.booleans(),
       verified=st.booleans())
def test_no_fail_from_estimated_geometry_on_metric_rules(violated, beyond, confirmed, guidance, verified):
    """NFR-05: a metric rule never FAILs on T3 geometry."""
    d = decide(Raw(["x"], violated, beyond_band=beyond, metric=True), "T3", guidance=guidance,
               all_confirmed=confirmed, scale_verified=verified)
    assert d.verdict != "FAIL"


@pytest.mark.parametrize("det,op,lim,tol,exp", [
    (0.80, ">=", 0.80, 0.01, (False, False)),     # exactly on the limit passes
    (0.795, ">=", 0.80, 0.01, (True, False)),     # inside the tolerance band
    (0.79, ">=", 0.80, 0.01, (True, False)),      # on the band edge
    (0.78, ">=", 0.80, 0.01, (True, True)),
    (15.0, "<=", 15.0, 0.1, (False, False)),
    (15.2, "<=", 15.0, 0.1, (True, True)),
])
def test_compare_edges(det, op, lim, tol, exp):
    assert compare(det, op, lim, tol) == exp
