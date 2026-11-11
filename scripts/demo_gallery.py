"""Run the variant plans through the whole product with the real local model and build a gallery to show.

    python scripts/demo_gallery.py [output folder] [--doc en|fr] [--only 02,04,10]

For every scenario of `reviewpulse.synth.scenarios` it creates a project, uploads the plan and the requirement document,
lets the model read the clauses it can turn into checked rules, approves them under the name "demo reviewer", confirms
the inventory, runs the check and saves the coverage report. `index.html` in the output folder lists every scenario with
what it shows, the errors planted in it, what ReviewPulse reported, and a link to its report.

The older drafter that runs when a document is uploaded is answered with a canned reply so each scenario takes minutes,
not an hour; the clauses are read by the real model through the same code the web app uses.
"""

from __future__ import annotations

import argparse
import html
import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from reviewpulse.app.api import create_app
from reviewpulse.synth.make_plan import make_plan
from reviewpulse.synth.random_plan import random_plan
from reviewpulse.synth.scenarios import SCENARIOS
from reviewpulse.xeval.drafters import BoundedOllama

DOCS = {"en": Path("docs/requirements_example.md"), "fr": Path("docs/requirements_example_fr.md")}
CLAUSES = ["Art. 1", "Art. 2", "Art. 2.1", "Art. 3", "Art. 4", "Art. 5", "Art. 6.1", "Art. 6.3", "Art. 6.4", "Art. 8"]


class Hybrid:
    """Real model for reading clauses and the second reading; a canned answer for the older drafter."""

    model = "qwen2.5:7b"

    def __init__(self):
        self.real = BoundedOllama()

    def complete(self, system, user, schema):
        if "CLAUSE_JSON:" in user:
            return {"property": "fire_resistance", "subject": "room", "room_types": [], "avoid_room_types": [],
                    "forbidden_pairs": [], "comparison": "no_number", "number": None, "unit_written": "none",
                    "severity": "major", "title": "x",
                    "rase": {"requirement": [], "applicability": [], "selection": [], "exception": []}}
        return self.real.complete(system, user, schema)


def wait(c, pid, job):
    while True:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            assert rec["status"] == "done", rec.get("error")
            return
        time.sleep(0.3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="demo_results")
    ap.add_argument("--doc", choices=list(DOCS), default="en")
    ap.add_argument("--only", default="", help="comma separated scenario numbers, e.g. 02,04,10")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    rows = []
    llm = Hybrid()
    with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp) / "data", llm=lambda: llm, workers=1)) as c:
        for name, kind, kw, shows in SCENARIOS:
            if only and name.split("_")[0] not in only:
                continue
            t0 = time.time()
            paths = make_plan(Path(tmp) / name, png=False, **kw) if kind == "make" else random_plan(Path(tmp) / name, **kw)
            truth = json.loads(Path(paths["truth"]).read_text(encoding="utf-8"))
            planted = sorted({e["rule"] for e in truth.get("expected_findings", [])})
            pid = c.post("/api/projects", json={"name": name, "curator": "demo reviewer"}).json()["id"]
            with open(paths["dxf"], "rb") as f:
                wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": ("plan.dxf", f)}).json())
            with open(DOCS[args.doc], "rb") as f:
                wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": ("requirements.md", f)}).json())
            for clause in CLAUSES:
                r = c.post(f"/api/projects/{pid}/interpret/{clause}").json()
                if r["status"] == "DRAFTED":
                    c.post(f"/api/projects/{pid}/decision",
                           json={"clause": clause, "action": "approve", "reviewer": "demo reviewer", "acknowledge": True})
            c.patch(f"/api/projects/{pid}", json={"inventory_reviewed": True})
            wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
            cov = c.get(f"/api/projects/{pid}/coverage").json()
            (out / f"{name}.html").write_text(c.get(f"/api/projects/{pid}/coverage.html").text, encoding="utf-8")
            violated = [x["id"] for x in cov["clauses"] if x["status"] == "violated"]
            rows.append({"name": name, "shows": shows, "planted": planted, "violated": violated,
                         "decided": cov["summary"]["decided"], "clauses": cov["summary"]["clauses"],
                         "seconds": round(time.time() - t0)})
            print(f"{name}: violated {violated or 'nothing'}  (planted {planted or 'nothing'})  "
                  f"decided {cov['summary']['decided']}/{cov['summary']['clauses']}  {rows[-1]['seconds']}s", flush=True)
    body = "".join(
        f"<tr><td><a href=\"{html.escape(r['name'])}.html\">{html.escape(r['name'])}</a></td><td>{html.escape(r['shows'])}</td>"
        f"<td>{html.escape(', '.join(r['planted']) or 'none')}</td><td>{html.escape(', '.join(r['violated']) or 'nothing')}</td>"
        f"<td>{r['decided']} of {r['clauses']}</td></tr>" for r in rows)
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>ReviewPulse demo gallery</title>"
        "<style>body{font:15px system-ui;margin:24px;max-width:1100px}td,th{border:1px solid #ccc;padding:6px 10px;"
        "vertical-align:top}table{border-collapse:collapse}</style><h1>ReviewPulse demo gallery</h1>"
        f"<p>Each row is a different plan checked against the {args.doc.upper()} example requirement document. "
        "Open a report to see every clause with its rule, its result and the reason when it was not checked.</p>"
        "<table><tr><th>Scenario</th><th>What it shows</th><th>Errors planted (older engine rule ids)</th>"
        "<th>Clauses reported as violated</th><th>Clauses decided</th></tr>" + body + "</table>", encoding="utf-8")
    (out / "results.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"\nGallery: {(out / 'index.html').resolve()}")


if __name__ == "__main__":
    main()
