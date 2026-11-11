"""Acceptance suite: every input type through ``rp check`` end to end (M4).

Each case builds its input from the synthetic generators (and renders of them), runs the real CLI in
a subprocess, and checks the run folder:
- the command exits cleanly and writes findings + reports;
- the confidence tier is one the input can justify (a scan is never T1);
- no FAIL rests on estimated input: no metric FAIL without a verified scale (NFR-05), no presence
  FAIL on OCR-read text, no FAIL on a room typed by the language model;
- planted errors are reported (FAIL or WARNING). On vector input this is required; on scans it is
  measured and reported, since detection there is a model result, not a guarantee;
- seconds per page are recorded.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

METRIC_CLASSES = {"threshold", "derived", "arithmetic"}
AREA_TOL = 0.10            # total room area vs truth on a T1/T2 sheet (scans measure ~0.97: wall faces)


@dataclass
class Case:
    name: str
    kind: str                                   # "vector" | "raster"
    build: Callable[[Path], Path]
    tiers: set[str]
    planted: set[str] = field(default_factory=set)   # rule ids that must be reported
    sheets: int = 1
    note: str = ""
    verdict_truth: list[dict] = field(default_factory=list)


def verdict_metrics(findings: list[dict], truth: list[dict]) -> dict:
    """Score only explicit subject-level truth. Unlabelled findings are never assumed correct."""
    def key(row):
        return row["rule_id"], tuple(sorted(row["subject_ids"]))

    predictions = {key(f): f for f in findings}
    counts = Counter(key(f) for f in findings)
    ambiguous = {k for k, n in counts.items() if n > 1}
    predictions = {k: f for k, f in predictions.items() if k not in ambiguous}
    if len({key(t) for t in truth}) != len(truth):
        raise ValueError("duplicate verdict ground truth")

    def outcome(f):
        return f.get("assessment", {}).get("outcome") if f else None

    matched = [(t, predictions.get(key(t))) for t in truth]
    labelled_violations = [(t, f) for t, f in matched if outcome(f) == "VIOLATED"]
    actual_violations = [(t, f) for t, f in matched if t["outcome"] == "VIOLATED"]
    unresolved = [(t, f) for t, f in matched
                  if t["outcome"] == "UNRESOLVED" and "evidence_issues" in t]
    reason_correct = 0
    for t, f in unresolved:
        actual = {i["code"] for i in f.get("assessment", {}).get("evidence_issues", [])} if f else set()
        reason_correct += outcome(f) == "UNRESOLVED" and actual == set(t["evidence_issues"])

    def fraction(n, d):
        return n / d if d else None

    structured = [f for f in findings if outcome(f) is not None]
    return {
        "labelled_checks": len(truth),
        "ambiguous_prediction_keys": len(ambiguous),
        "matched_checks": sum(f is not None for _, f in matched),
        "verdict_correctness": fraction(sum(t["outcome"] == outcome(f) for t, f in matched), len(truth)),
        "precision_violated": fraction(sum(t["outcome"] == "VIOLATED" for t, _ in labelled_violations),
                                       len(labelled_violations)),
        "false_pass_rate": fraction(sum(outcome(f) == "SATISFIED" for _, f in actual_violations),
                                    len(actual_violations)),
        "decisive_coverage": fraction(sum(outcome(f) != "UNRESOLVED" for f in structured), len(findings)),
        "unresolved_reason_accuracy": fraction(reason_correct, len(unresolved)),
        "reason_labelled_checks": len(unresolved),
        "unlabelled_predictions": sum(key(f) not in {key(t) for t in truth} for f in findings),
    }


# ---- input builders ---------------------------------------------------------------------------------

def _plan(work: Path, seed: int, errors: tuple[str, ...] = (), **kw) -> dict:
    from ..synth.make_plan import make_plan

    return make_plan(work, seed=seed, errors=errors, **kw)


def _dxf(errors, seed=11):
    return lambda w: Path(_plan(w, seed, errors, png=False)["dxf"])


def _pdf(errors, seed=12):
    return lambda w: Path(_plan(w, seed, errors, png=False)["pdf"])


def _random_dxf(seed):
    def b(w):
        from ..synth.random_plan import random_plan

        return Path(random_plan(w, seed=seed)["dxf"])
    return b


def _svg(w: Path) -> Path:
    import pymupdf

    pdf = Path(_plan(w, 13, ("metric_door_narrow",), png=False)["pdf"])
    out = w / (pdf.stem + ".svg")
    out.write_text(pymupdf.open(pdf)[0].get_svg_image(text_as_path=False), encoding="utf-8")
    return out


def _png(errors=(), seed=14, dpi=200, noise=0.0, rotate90=False):
    def b(w):
        from ..synth.make_plan import _write_png

        pdf = Path(_plan(w, seed, errors, png=False)["pdf"])
        png = w / f"{pdf.stem}_{dpi}dpi{'_noisy' if noise else ''}{'_r90' if rotate90 else ''}.png"
        _write_png(pdf, png, dpi=dpi, noise=noise, seed=seed)
        if rotate90:
            from PIL import Image

            with Image.open(png) as im:
                im.rotate(90, expand=True, fillcolor=255).save(png, dpi=(dpi, dpi))
        return png
    return b


def _scanned_pdf(w: Path) -> Path:
    import pymupdf
    from PIL import Image

    png = _png(("topo_exit_via_bath",), seed=15)(w)
    with Image.open(png) as im:
        wpx, hpx = im.size
    dpi = 200
    doc = pymupdf.open()
    page = doc.new_page(width=wpx / dpi * 72, height=hpx / dpi * 72)
    page.insert_image(page.rect, filename=str(png))
    out = w / (png.stem + "_scan.pdf")
    doc.save(out)
    return out


def _multipage(w: Path) -> Path:
    import pymupdf

    a = pymupdf.open(_plan(w, 16, ("metric_room_small",), png=False)["pdf"])
    b = pymupdf.open(_plan(w, 17, ("cons_chain_off",), png=False)["pdf"])
    a.insert_pdf(b)
    out = w / "two_sheets.pdf"
    a.save(out)
    return out


def _no_labels(w: Path) -> Path:
    import ezdxf

    src = Path(_plan(w, 18, (), png=False)["dxf"])
    doc = ezdxf.readfile(src)
    msp = doc.modelspace()
    for e in list(msp.query("TEXT MTEXT")):
        msp.delete_entity(e)
    out = w / (src.stem + "_nolabels.dxf")
    doc.saveas(out)
    return out


CASES: list[Case] = [
    Case("dxf", "vector", _dxf(("metric_room_small",)), {"T1"}, {"C-D3"}),
    Case("dxf_random_style", "vector", _random_dxf(5), {"T1"}, note="random layers, units, wall style, clutter"),
    Case("pdf_vector", "vector", _pdf(("topo_exit_via_bath",)), {"T1", "T2"}, {"C-T1"}),
    Case("svg", "vector", _svg, {"T1", "T2"}, {"C-D1"}, note="PDF page exported to SVG (tspan glyph positions, rotated text)"),
    Case("multipage_pdf", "vector", _multipage, {"T1", "T2"}, {"C-D3", "K-A1"}, sheets=2),
    Case("no_dimensions", "vector", _pdf(("comp_no_dimensions",), seed=19), {"T1", "T2", "T3"}, {"P-2"}),
    Case("no_labels", "vector", _no_labels, {"T1"}, {"P-1"}, note="every text entity removed"),
    Case("png_scan", "raster", _png(("topo_exit_via_bath",)), {"T2", "T3"}, {"C-T1"}),
    Case("scanned_pdf", "raster", _scanned_pdf, {"T2", "T3"}, {"C-T1"}),
    Case("skewed_noisy_scan", "raster", _png(("topo_exit_via_bath",), seed=20, noise=0.04), {"T2", "T3"}, {"C-T1"},
         note="1-3 deg skew, noise, blur"),
    Case("rotated_scan_90", "raster", _png(("topo_exit_via_bath",), seed=21, rotate90=True), {"T2", "T3"}, {"C-T1"}),
    Case("low_dpi_scan", "raster", _png(("topo_exit_via_bath",), seed=22, dpi=100), {"T2", "T3"}, {"C-T1"},
         note="100 dpi"),
]


# ---- running and checking ---------------------------------------------------------------------------

def run_case(case: Case, work: Path, env: dict | None = None) -> dict:
    import os

    from ..cli import DEFAULT_PACK
    from ..rules.schema import load_pack

    work.mkdir(parents=True, exist_ok=True)
    src = case.build(work / "input")
    runs = work / "runs"
    t0 = time.time()
    p = subprocess.run([sys.executable, "-c", "from reviewpulse.cli import app; app()", "check", str(src),
                        "--runs", str(runs)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, **(env or {})}, timeout=3600)
    secs = time.time() - t0
    res: dict = {"case": case.name, "kind": case.kind, "input": src.name, "exit": p.returncode,
                 "seconds": round(secs, 1), "problems": [], "note": case.note}
    if p.returncode != 0:
        res["problems"].append("crash: " + (p.stderr or p.stdout)[-600:])
        return res
    run_dirs = [d for d in runs.iterdir() if d.is_dir()]
    run_dir = max(run_dirs, key=lambda d: d.stat().st_mtime)
    buildings = sorted(run_dir.glob("building_*.json"))
    res["sheets"] = len(buildings)
    res["seconds_per_page"] = round(secs / max(len(buildings), 1), 1)
    findings = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    findings = findings["findings"] if isinstance(findings, dict) else findings
    for f in ("report.html", "report.pdf"):
        if not (run_dir / f).exists():
            res["problems"].append(f"missing {f}")
    models = [json.loads(b.read_text(encoding="utf-8")) for b in buildings]
    tiers = sorted({f["tier"] for f in findings})
    res["tiers"] = tiers
    res["walls"] = sum(sum(1 for e in m["elements"] if e["cls"] == "wall") for m in models)
    res["rooms"] = sum(len(m["rooms"]) for m in models)
    res["verdicts"] = {v: sum(1 for f in findings if f["verdict"] == v) for v in ("FAIL", "WARNING", "PASS",
                                                                                  "NOT_EVALUATED")}
    if len(buildings) != case.sheets:
        res["problems"].append(f"expected {case.sheets} sheet(s), got {len(buildings)}")
    if not set(tiers) <= case.tiers:
        res["problems"].append(f"tier {tiers} not in {sorted(case.tiers)}")
    if res["walls"] == 0 or res["rooms"] == 0:
        res["problems"].append("no walls or no rooms detected")
    # measurements against the generator's truth: a T1/T2 sheet must measure what was drawn
    from shapely.geometry import Polygon

    true_area = sum(Polygon(r["polygon"]).area for t in (work / "input").glob("*.truth.json")
                    for r in json.loads(t.read_text(encoding="utf-8"))["rooms"])
    meas_area = sum(r["area_m2"] or 0 for m in models for r in m["rooms"])
    if true_area:
        res["area_ratio"] = round(meas_area / true_area, 3)
        if set(tiers) & {"T1", "T2"} and not 1 - AREA_TOL <= res["area_ratio"] <= 1 + AREA_TOL:
            res["problems"].append(f"measured room area {res['area_ratio']}x the truth at {tiers}")
    cls_of = {r.id: r.cls for r in load_pack(DEFAULT_PACK)}
    llm_rooms = {r["id"] for m in models for r in m["rooms"] if r["prov"]["evidence"].get("label_source") == "llm"}
    raster = any(m["sheet"]["mode"] == "raster" for m in models)
    for f in findings:
        if f["verdict"] != "FAIL":
            continue
        c = cls_of.get(f["rule_id"])
        if f["tier"] != "T1" and c in METRIC_CLASSES and not f.get("evidence", {}).get("measurement_interval"):
            res["problems"].append(f"unsafe FAIL: metric rule {f['rule_id']} at {f['tier']}")
        if c == "presence" and raster and any(i["code"] == "POSSIBLE_TEXT_OMISSION"
                                              for i in f.get("assessment", {}).get("evidence_issues", [])):
            res["problems"].append(f"unsafe FAIL: presence rule {f['rule_id']} on OCR text")
        if llm_rooms & set(f["subject_ids"]):
            res["problems"].append(f"unsafe FAIL: {f['rule_id']} on an LLM-typed room")
    reported = {f["rule_id"] for f in findings if f["verdict"] in ("FAIL", "WARNING")}
    res["planted_found"] = sorted(case.planted & reported)
    res["planted_missed"] = sorted(case.planted - reported)
    res["detection_recall"] = len(res["planted_found"]) / len(case.planted) if case.planted else None
    res["verdict_metrics"] = verdict_metrics(findings, case.verdict_truth)
    if res["planted_missed"] and case.kind == "vector":
        res["problems"].append(f"planted errors missed: {res['planted_missed']}")
    res["ok"] = not res["problems"]
    return res


def write_report(results: list[dict], out: Path) -> Path:
    lines = ["# Acceptance: every input type through `rp check`", "",
             "| case | kind | ok | sheets | tier | walls | rooms | area / truth | FAIL/WARN | detection recall (found/total) | s/page | problems |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        v = r.get("verdicts", {})
        found = f"{len(r.get('planted_found', []))}/{len(r.get('planted_found', [])) + len(r.get('planted_missed', []))}"
        lines.append(f"| {r['case']} | {r['kind']} | {'yes' if r.get('ok') else 'NO'} | {r.get('sheets', '-')} | "
                     f"{','.join(r.get('tiers', []))} | {r.get('walls', '-')} | {r.get('rooms', '-')} | {r.get('area_ratio', '-')} | "
                     f"{v.get('FAIL', '-')}/{v.get('WARNING', '-')} | {found} | {r.get('seconds_per_page', r['seconds'])} | "
                     f"{'; '.join(r['problems'])[:200]} |")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n\n```\n" + json.dumps(results, indent=1) + "\n```\n", encoding="utf-8")
    return out
