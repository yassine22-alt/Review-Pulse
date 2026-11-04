"""J7 for real use: triage audit flow, rotated pages, multi-sheet PDFs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pymupdf
from typer.testing import CliRunner

from reviewpulse.cli import app
from reviewpulse.report.anchor import anchor_point
from reviewpulse.schema import BuildingModel, load, load_findings
from reviewpulse.synth.make_plan import make_plan

runner = CliRunner()


def _run_dir(runs: Path) -> Path:
    return next(p for p in runs.iterdir() if p.is_dir())


def test_triage_dismiss_and_confirm_are_logged_and_reused(tmp_path):
    p = make_plan(tmp_path, seed=61, errors=("topo_exit_via_bath",), png=False)
    runs = tmp_path / "runs"
    res = runner.invoke(app, ["check", p["pdf"], "--runs", str(runs)])
    assert res.exit_code == 0, res.output
    run_dir = _run_dir(runs)
    fail = next(f for f in load_findings(run_dir / "findings.json") if f.verdict == "FAIL")
    fid = fail.evidence["finding_id"]
    model = load(BuildingModel, run_dir / "building_0.json")
    door = next(e.id for e in model.elements if e.cls == "door")
    res = runner.invoke(app, ["check", str(run_dir), "--dismiss", f"{fid}:accepted by the architect",
                              "--confirm", door])
    assert res.exit_code == 0, res.output
    tri = json.loads((run_dir / "triage.json").read_text())
    assert tri["dismissed"][fid] == "accepted by the architect"
    assert door in tri["confirmed"]
    assert [x["action"] for x in tri["log"]] == ["confirm", "dismiss"]
    # a later run without flags still applies the audit log
    res = runner.invoke(app, ["check", str(run_dir)])
    assert res.exit_code == 0, res.output
    again = {f.evidence["finding_id"]: f for f in load_findings(run_dir / "findings.json")}
    assert again[fid].evidence.get("dismissed") == "accepted by the architect"
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "dismissed: accepted by the architect" in html
    csv = (run_dir / "findings.csv").read_text(encoding="utf-8")
    assert "accepted by the architect" in csv


def _red_near(pix: pymupdf.Pixmap, x: float, y: float, r: int = 18) -> bool:
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    x0, x1 = max(int(x) - r, 0), min(int(x) + r, pix.width)
    y0, y1 = max(int(y) - r, 0), min(int(y) + r, pix.height)
    win = a[y0:y1, x0:x1, :3].astype(int)
    red = (win[..., 0] > 180) & (win[..., 1] < 90) & (win[..., 2] < 90)
    return bool(red.any())


def test_rotated_page_markers_land_on_their_evidence(tmp_path):
    p = make_plan(tmp_path, seed=62, errors=("topo_exit_via_bath",), png=False, rotate=90)
    runs = tmp_path / "runs"
    assert runner.invoke(app, ["check", p["pdf"], "--runs", str(runs)]).exit_code == 0
    run_dir = _run_dir(runs)
    model = load(BuildingModel, run_dir / "building_0.json")
    fail = next(f for f in load_findings(run_dir / "findings.json") if f.verdict == "FAIL")
    ax, ay = anchor_point(fail, model)
    dpi = 72
    k = dpi / 25.4
    # sheet space is the visible orientation, y up: pixel = (x k, (H - y) k) on the rendered page
    px, py = ax * k, (model.sheet.height - ay) * k
    pix = pymupdf.open(run_dir / "report.pdf")[0].get_pixmap(dpi=dpi)
    assert pymupdf.open(run_dir / "report.pdf")[0].rotation == 90
    assert _red_near(pix, px, py), "FAIL marker not drawn at its evidence on the rotated page"
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert 'class="f v-FAIL"' in html and "data:image/png;base64," in html


def test_multi_sheet_pdf_reports_every_page(tmp_path):
    a = make_plan(tmp_path, seed=63, errors=("metric_door_narrow",), png=False, name="sheetA")
    b = make_plan(tmp_path, seed=64, errors=("topo_exit_via_bath",), png=False, name="sheetB")
    both = pymupdf.open()
    for f in (a["pdf"], b["pdf"]):
        both.insert_pdf(pymupdf.open(f))
    multi = tmp_path / "two_sheets.pdf"
    both.save(multi)
    runs = tmp_path / "runs"
    res = runner.invoke(app, ["check", str(multi), "--runs", str(runs)])
    assert res.exit_code == 0, res.output
    run_dir = _run_dir(runs)
    assert (run_dir / "building_0.json").exists() and (run_dir / "building_1.json").exists()
    findings = load_findings(run_dir / "findings.json")
    sheets = {f.evidence.get("sheet") for f in findings}
    assert len(sheets) == 2
    bad = {(f.evidence["sheet"], f.rule_id) for f in findings if f.verdict == "FAIL"}
    assert {r for _s, r in bad} >= {"C-D1", "C-T1"}
    doc = pymupdf.open(run_dir / "report.pdf")
    assert doc.page_count >= 3                       # two annotated sheets + summary
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert html.count('<section class="sheet">') == 2
