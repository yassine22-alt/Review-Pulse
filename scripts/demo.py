"""End-to-end demo through the HTTP API: a generated plan with planted errors + the example requirement
document -> analysis -> drafted rules (local model) -> curator approval -> check -> findings.

    python scripts/demo.py                       start a server, run the flow, print the findings
    python scripts/demo.py --keep                 ... and keep serving (open the printed URL)
    python scripts/demo.py --url http://host:8000 use a running server instead

The plan comes from synth/make_plan, so the planted errors are known and the script reports which were
found. Drafted rules are approved automatically only in this demo (curator "demo"); flagged or invalid
drafts are left for a person.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "requirements_example.md"
ERRORS = ("metric_door_narrow", "metric_room_small", "topo_exit_via_bath", "cons_chain_off",
          "comp_tag_missing")   # each on a different room: an unlabelled room has no type for C-T1


def start_server(data: Path, port: int) -> str:
    import uvicorn

    from reviewpulse.app.api import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(data), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(url + "/api/health", timeout=30).status_code == 200:
                return url
        except httpx.HTTPError:
            time.sleep(0.1)
    raise SystemExit("server did not start")


def wait(c: httpx.Client, pid: str, job: dict, label: str) -> dict:
    last = ""
    while True:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        msg = f"  {label}: {rec['message']} ({round(100 * rec['progress'])}%)"
        if msg != last:
            print(msg, flush=True)
            last = msg
        if rec["status"] == "done":
            return rec
        if rec["status"] == "failed":
            raise SystemExit(f"{label} failed: {rec['error']}")
        time.sleep(1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="use a running server")
    ap.add_argument("--data", default=str(ROOT / "runs" / "demo_app"), help="projects folder for the demo server")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--format", default="dxf", choices=["dxf", "pdf"], help="plan file sent to the server")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--keep", action="store_true", help="keep the demo server running")
    a = ap.parse_args()

    from reviewpulse.synth.make_plan import make_plan

    url = a.url or start_server(Path(a.data), a.port)
    c = httpx.Client(base_url=url, timeout=60)
    health = c.get("/api/health").json()
    import os

    print(f"pid {os.getpid()}")
    print(f"server {url} · drafting model: {health['llm']['model']} ({'online' if health['llm']['available'] else 'offline'})")

    out = Path(a.data) / "inputs"
    paths = make_plan(out, seed=a.seed, errors=ERRORS, png=False, name="demo_plan")
    pid = c.post("/api/projects", json={"name": "Demo · Résidence Les Tilleuls, lot 3", "curator": "demo",
                                        "base_pack": "starter"}).json()["id"]
    print(f"project {pid}: planted errors {', '.join(ERRORS)}")

    t0 = time.time()
    with open(paths[a.format], "rb") as f:
        job = c.post(f"/api/projects/{pid}/plan", files={"file": (Path(paths[a.format]).name, f)}).json()
    res = wait(c, pid, job, "plan")["result"]
    print(f"  analysed in {time.time() - t0:.1f}s: {res['elements']} elements, {res['rooms']} rooms, tier {res['tiers']}")

    t0 = time.time()
    with open(DOC, "rb") as f:
        job = c.post(f"/api/projects/{pid}/requirements", files={"file": (DOC.name, f)}).json()
    res = wait(c, pid, job, "requirements")["result"]
    print(f"  {res['clauses']} clauses, {res['drafted']} rules drafted by {res['llm']} in {time.time() - t0:.0f}s")

    approved = 0
    for d in c.get(f"/api/projects/{pid}/drafts").json():
        if d["rule"] and not d["errors"] and not d["flags"]:
            r = c.post(f"/api/projects/{pid}/drafts/{d['index']}/approve", json={"curator": "demo"}).json()
            approved += r["ok"]
            print(f"  {'approved' if r['ok'] else 'refused '} {d['clause_id']:<9} {r['message'][:90]}")
    print(f"  {approved} drafted rules approved")

    t0 = time.time()
    res = wait(c, pid, c.post(f"/api/projects/{pid}/check").json(), "check")["result"]
    print(f"  checked in {time.time() - t0:.1f}s with {res['rules']['total']} rules: {res['summary']}")

    fs = c.get(f"/api/projects/{pid}/findings").json()["findings"]
    print("\nfindings (FAIL / WARNING):")
    for f in fs:
        if f["verdict"] in ("FAIL", "WARNING"):
            print(f"  {f['verdict']:<8} {f['rule_id']:<14} {f['message'][:100]}")
    import json

    truth = json.loads(Path(paths["truth"]).read_text(encoding="utf-8"))
    raised = {f["rule_id"] for f in fs if f["verdict"] in ("FAIL", "WARNING")}
    exp = sorted({e["rule"] for e in truth["expected_findings"]})
    hit = [r for r in exp if r in raised]
    print(f"\nplanted errors -> expected rules {exp}\nraised: {hit} ({len(hit)}/{len(exp)})")
    print(f"\nopen {url}/#/p/{pid}/results")
    if a.keep and not a.url:
        print("serving; Ctrl+C to stop")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    sys.exit(0 if len(hit) == len(exp) else 1)


if __name__ == "__main__":
    main()
