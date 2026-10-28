"""`rp doctor`: is this installation complete and working? Plain answers, one line per check.

Three parts:
1. what is installed (required packages, optional features and what each one adds);
2. the pipeline end to end: a generated plan with planted errors is checked, and every planted error
   must be found;
3. the web app: started in-process, a project is created, the plan uploaded and checked through the
   same HTTP API the browser uses.

Exit code 0 when everything required works (optional features may be missing), 1 otherwise.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

OK, OPTIONAL, BROKEN = "ok", "optional, not installed", "BROKEN"

REQUIRED = {
    "pymupdf": "PDF reading", "ezdxf": "DXF reading", "shapely": "geometry", "numpy": "numbers",
    "scipy": "numbers", "networkx": "room graph", "pydantic": "data model", "typer": "command line",
    "rich": "command line output", "cv2": "images (opencv)", "PIL": "images (pillow)",
    "skimage": "images (scikit-image)", "yaml": "rule files", "lxml": "SVG reading",
    "lightgbm": "learned pass on CAD drawings", "docx": "Word briefs and requirements",
    "openpyxl": "Excel briefs",
}
OPTIONAL_FEATURES = {
    "web app (rp serve)": (["fastapi", "uvicorn", "multipart", "jinja2", "httpx"], 'pip install -e ".[app]"'),
    "scanned plans: wall/door/window model": (["torch", "segmentation_models_pytorch"], 'see README, "Scans"'),
    "scanned plans: text reading (OCR)": (["paddleocr"], 'see README, "Scans"'),
    "tests": (["pytest", "hypothesis"], 'pip install -e ".[dev]"'),
}
PLANTED = ("metric_door_narrow", "metric_room_small", "topo_exit_via_bath")


def _line(status: str, what: str, note: str = "") -> None:
    mark = {"ok": "[ ok ]", OPTIONAL: "[ -- ]", BROKEN: "[FAIL]"}.get(status, "[ ?? ]")
    print(f"{mark} {what}" + (f": {note}" if note else ""), flush=True)


def _importable(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:  # noqa: BLE001 - a broken install raises anything
        return False


def check_install() -> bool:
    good = True
    v = sys.version_info
    if (3, 11) <= v[:2] <= (3, 12):
        _line(OK, f"Python {v.major}.{v.minor}")
    else:
        _line(BROKEN, f"Python {v.major}.{v.minor}", "ReviewPulse needs Python 3.11 or 3.12")
        good = False
    missing = [f"{m} ({why})" for m, why in REQUIRED.items() if not _importable(m)]
    if missing:
        _line(BROKEN, "required packages", "missing " + ", ".join(missing) + '; run pip install -e ".[app,dev]"')
        good = False
    else:
        _line(OK, f"required packages ({len(REQUIRED)})")
    for feature, (mods, how) in OPTIONAL_FEATURES.items():
        if all(_importable(m) for m in mods):
            _line(OK, feature)
        else:
            _line(OPTIONAL, feature, how)
    from .perception.learned.classifier import available, model_dir

    if available():
        _line(OK, "trained model for CAD drawings", str(model_dir()))
    else:
        _line(OPTIONAL, "trained model for CAD drawings",
              f"not found at {model_dir()}; CAD drawings are read with the geometric rules only")
    _check_drafting_model()
    return good


def _check_drafting_model() -> None:
    import urllib.request

    host = (os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    if "://" not in host:
        host = "http://" + host
    want = os.environ.get("REVIEWPULSE_LLM_MODEL") or "qwen2.5:7b"
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=3) as r:
            names = {m.get("name", "") for m in json.loads(r.read()).get("models", [])}
    except Exception:  # noqa: BLE001 - not running is a normal state
        _line(OPTIONAL, "rule-drafting model", f"Ollama not running at {host}; install it from ollama.com, "
                                                f"then: ollama pull {want}")
        return
    if want in names or f"{want}:latest" in names:
        _line(OK, f"rule-drafting model ({want})")
    else:
        _line(OPTIONAL, "rule-drafting model", f"Ollama is running but {want} is not downloaded: ollama pull {want}")


def _plan(work: Path) -> dict:
    from .synth.make_plan import make_plan

    return make_plan(work / "plan", seed=11, errors=PLANTED, png=False, name="doctor_plan")


def _expected(paths: dict) -> set:
    truth = json.loads(Path(paths["truth"]).read_text(encoding="utf-8"))
    return {e["rule"] for e in truth["expected_findings"]}


def check_pipeline(work: Path) -> bool:
    from . import pipeline
    from .schema import load_findings

    pack = Path(__file__).parent / "rules" / "packs" / "starter"
    paths = _plan(work)
    exp = _expected(paths)
    good = True
    for fmt in ("dxf", "pdf"):
        t0 = time.time()
        try:
            run_dir, _summary = pipeline.run_all(paths[fmt], pack, work / "runs")
            fs = load_findings(run_dir / "findings.json")
        except Exception as e:  # noqa: BLE001 - reported, not raised
            _line(BROKEN, f"check a {fmt.upper()} plan", repr(e)[:160])
            good = False
            continue
        raised = {f.rule_id for f in fs if f.verdict in ("FAIL", "WARNING")}
        hit = exp & raised
        reports = all((run_dir / n).exists() for n in ("report.pdf", "report.html"))
        if hit == exp and reports:
            _line(OK, f"check a {fmt.upper()} plan", f"{len(hit)}/{len(exp)} planted errors found, reports written, "
                                                      f"{time.time() - t0:.0f} s")
        else:
            _line(BROKEN, f"check a {fmt.upper()} plan",
                  f"planted errors found {sorted(hit)} of {sorted(exp)}; reports {'written' if reports else 'missing'}")
            good = False
    return good


def check_app(work: Path) -> bool:
    if not all(_importable(m) for m in OPTIONAL_FEATURES["web app (rp serve)"][0]):
        _line(OPTIONAL, "web app", 'not installed (pip install -e ".[app]")')
        return True
    import warnings

    with warnings.catch_warnings():         # a library notice about its own test client, not ours
        warnings.simplefilter("ignore")
        from fastapi.testclient import TestClient

    from .app.api import create_app

    paths = _plan(work)
    exp = _expected(paths)
    try:
        with TestClient(create_app(work / "app")) as c:
            assert c.get("/api/health").json()["ok"]
            assert c.get("/").status_code == 200
            pid = c.post("/api/projects", json={"name": "doctor", "curator": "doctor", "base_pack": "starter"}).json()["id"]

            def wait(job):
                for _ in range(600):
                    rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
                    if rec["status"] in ("done", "failed"):
                        return rec
                    time.sleep(0.5)
                return {"status": "failed", "error": "timed out"}

            with open(paths["dxf"], "rb") as f:
                rec = wait(c.post(f"/api/projects/{pid}/plan", files={"file": ("doctor_plan.dxf", f)}).json())
            if rec["status"] != "done":
                raise RuntimeError(f"plan analysis failed: {rec.get('error')}")
            rec = wait(c.post(f"/api/projects/{pid}/check").json())
            if rec["status"] != "done":
                raise RuntimeError(f"check failed: {rec.get('error')}")
            fs = c.get(f"/api/projects/{pid}/findings").json()["findings"]
    except Exception as e:  # noqa: BLE001 - reported, not raised
        _line(BROKEN, "web app", repr(e)[:160])
        return False
    hit = exp & {f["rule_id"] for f in fs if f["verdict"] in ("FAIL", "WARNING")}
    if hit == exp:
        _line(OK, "web app", f"page served, plan uploaded and checked through the API, {len(hit)}/{len(exp)} planted errors found")
        return True
    _line(BROKEN, "web app", f"planted errors found {sorted(hit)} of {sorted(exp)}")
    return False


def run(keep: Path | None = None) -> int:
    print("ReviewPulse doctor\n\n1. Installation", flush=True)
    os.environ.setdefault("REVIEWPULSE_LABEL_LLM", "0")      # the self-test never waits on a language model
    good = check_install()
    with tempfile.TemporaryDirectory() as td:
        work = keep or Path(td)
        print("\n2. Pipeline (a generated plan with planted errors)", flush=True)
        good &= check_pipeline(work)
        print("\n3. Web app", flush=True)
        good &= check_app(work)
    print("\nAll required parts work." if good else "\nSomething required is broken: see the [FAIL] lines above.")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(run())
