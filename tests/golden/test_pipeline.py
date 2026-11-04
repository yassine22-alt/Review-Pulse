"""End-to-end on generated plans (DXF and PDF): perception, scale, rules, reports."""

import json
from pathlib import Path

import pytest

from reviewpulse.engine.run import run
from reviewpulse.eval.cli import _model_from


@pytest.mark.parametrize("denominator", [50, 100, 200])
def test_pdf_scale_recovered(synth_dir, denominator):
    from reviewpulse.synth.make_plan import make_plan

    p = make_plan(synth_dir, seed=11, denominator=denominator, png=False, name=f"scale_{denominator}")
    m = _model_from(p["pdf"])
    assert m.sheet.scale.method == "dimension_consensus"
    assert m.sheet.scale.metres_per_unit == pytest.approx(denominator / 1000, rel=0.005)
    assert m.sheet.scale.confidence >= 0.95
    assert m.tier == "T1"


def test_written_vs_drawn_outlier_is_reported(synth_dir):
    from reviewpulse.synth.make_plan import make_plan

    p = make_plan(synth_dir, seed=12, errors=("cons_written_vs_drawn",), png=False)
    m = _model_from(p["pdf"])
    k = [d for d in m.sheet.dimensions if d.value_m and d.measured_m and abs(d.value_m - d.measured_m) > 0.2]
    assert len(k) == 1


@pytest.mark.parametrize("fmt", ["dxf", "pdf"])
def test_clean_plan_has_no_violation(synth_dir, pack, fmt):
    from reviewpulse.synth.make_plan import make_plan

    p = make_plan(synth_dir, seed=21, png=False, name="clean21")
    m = _model_from(p[fmt])
    bad = [f for f in run(m, pack) if f.verdict in ("FAIL", "WARNING")]
    assert bad == [], [(f.rule_id, f.message) for f in bad]


@pytest.mark.parametrize("error", ["topo_exit_via_bath", "topo_bedroom_via_bedroom", "metric_door_narrow",
                                   "metric_corridor_pinch", "cons_chain_off", "cons_schedule_width",
                                   "comp_tag_missing", "coord_swing_overlap"])
def test_planted_error_found_on_pdf(synth_dir, pack, error):
    from reviewpulse.synth.make_plan import make_plan

    p = make_plan(synth_dir, seed=31, errors=(error,), png=False)
    t = json.loads(Path(p["truth"]).read_text())
    got = {(f.rule_id, f.verdict) for f in run(_model_from(p["pdf"]), pack)}
    for e in t["expected_findings"]:
        assert (e["rule"], e["verdict"]) in got


def test_reports_written(tmp_path, synth_dir):
    from reviewpulse import pipeline
    from reviewpulse.cli import DEFAULT_PACK
    from reviewpulse.synth.make_plan import make_plan

    p = make_plan(synth_dir, seed=41, errors=("topo_exit_via_bath",), png=False, rotate=90, name="rot90")
    run_dir, summary = pipeline.run_all(p["pdf"], DEFAULT_PACK, runs_dir=tmp_path)
    assert summary.get("FAIL", 0) >= 1
    for name in ("findings.json", "findings.csv", "report.pdf", "report.html", "building_0.json", "sheets.json"):
        assert (run_dir / name).exists(), name
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "C-T1" in html and "<svg" in html and "http" not in html.split("<script>")[0].replace("http://www.w3.org", "")
