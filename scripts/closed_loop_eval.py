"""End-to-end measurement of the closed loop on generated plans with planted errors, using the real local model.

For each plan: upload the plan and the example requirement document, read three clauses (door width, bedroom size,
living room size), approve the written rules under a reviewer's name, run the check, and compare what the approved
rules report with the planted errors. The older rule engine is the reference for which element is wrong: it finds every
planted error on these plans (the self-check). Clean plans (no planted error) measure false alarms.

The second reader is replaced by an empty review so the measurement is about drafting and execution; a person is the
critic in real use. Usage: python scripts/closed_loop_eval.py [plans]
"""

import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from reviewpulse.app.api import create_app
from reviewpulse.synth.make_plan import make_plan
from reviewpulse.xeval.drafters import BoundedOllama

DOC = Path("docs/requirements_example.md")
CLAUSES = {"Art. 6.1": ["C-D1"], "Art. 6.3": ["C-D3", "C-D3W"], "Art. 6.4": ["C-D3L"]}
SETS = [(), ("metric_door_narrow",), ("metric_room_small",), ("metric_living_small",), ("metric_bedroom_narrow",),
        ("metric_door_narrow", "metric_room_small"), ("metric_door_narrow", "metric_living_small"),
        ("metric_room_small", "metric_living_small"), ("metric_door_narrow", "metric_bedroom_narrow"), ()]


class Hybrid:
    """Old-style drafting questions get a fast 'not checkable'; the new drafting goes to the real model; the second
    reader says nothing (see the module docstring)."""

    model = "qwen2.5:7b"

    def __init__(self):
        self.real = BoundedOllama()

    def complete(self, system, user, schema):
        props = schema.get("properties", {})
        if "CLAUSE_JSON:" in user:
            return {"property": "fire_resistance", "subject": "room", "room_types": [], "avoid_room_types": [],
                    "forbidden_pairs": [], "comparison": "no_number", "number": None, "unit_written": "none",
                    "severity": "major", "title": "x",
                    "rase": {"requirement": [], "applicability": [], "selection": [], "exception": []}}
        if "issues" in props:
            return {"issues": [], "limitations": []}
        return self.real.complete(system, user, schema)


def wait(c, pid, job):
    while True:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            assert rec["status"] == "done", rec.get("error")
            return
        time.sleep(0.3)


def main(n: int):
    llm = Hybrid()
    rows = []
    with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp) / "data", llm=lambda: llm, workers=1)) as c:
        for k in range(n):
            errors = SETS[k % len(SETS)]
            paths = make_plan(Path(tmp) / f"p{k}", seed=100 + k, errors=errors, png=False)
            pid = c.post("/api/projects", json={"name": f"p{k}", "curator": "eval"}).json()["id"]
            with open(paths["dxf"], "rb") as f:
                wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": ("plan.dxf", f)}).json())
            with open(DOC, "rb") as f:
                wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": ("req.md", f)}).json())
            t0 = time.time()
            status = {}
            for clause in CLAUSES:
                r = c.post(f"/api/projects/{pid}/interpret/{clause}").json()
                status[clause] = r["status"]
                if r["status"] == "DRAFTED":
                    c.post(f"/api/projects/{pid}/decision", json={"clause": clause, "action": "approve", "reviewer": "eval"})
            c.patch(f"/api/projects/{pid}", json={"inventory_reviewed": True})
            wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
            findings = c.get(f"/api/projects/{pid}/findings").json()["findings"]
            truth = json.loads(Path(paths["truth"]).read_text(encoding="utf-8"))
            planted = [e for e in truth["expected_findings"] if e["rule"] in sum(CLAUSES.values(), [])]
            for clause, old_ids in CLAUSES.items():
                old = {s for f in findings if f["rule_id"] in old_ids and f["verdict"] == "FAIL" for s in f["subject_ids"]}
                new = {s for f in findings if f["rule_id"] == "I-" + clause.replace(" ", "_") and f["verdict"] == "FAIL"
                       for s in f["subject_ids"]}
                outcome = next((x["outcome"] for x in json.load(open(next(Path(tmp, "data").glob(
                    f"projects/{pid}/run/interpreted_results.json")), encoding="utf-8")) if x["clause"] == clause), "none")
                rows.append({"plan": k, "errors": list(errors), "clause": clause, "draft": status[clause], "outcome": outcome,
                             "old_fail": sorted(old), "new_fail": sorted(new), "planted_for_clause": sum(
                                 1 for e in planted if e["rule"] in old_ids), "seconds": round(time.time() - t0)})
            print(k, errors, {r["clause"]: (r["draft"], r["outcome"], len(r["old_fail"]), len(r["new_fail"]))
                              for r in rows if r["plan"] == k}, flush=True)
    summary = Counter()
    for r in rows:
        summary["clause runs"] += 1
        summary["drafted"] += r["draft"] == "DRAFTED"
        summary["old finds an error"] += bool(r["old_fail"])
        summary["new finds the same elements"] += bool(r["old_fail"]) and set(r["new_fail"]) == set(r["old_fail"])
        summary["new misses an element the old engine found"] += bool(set(r["old_fail"]) - set(r["new_fail"]))
        summary["new reports an element the old engine did not"] += bool(set(r["new_fail"]) - set(r["old_fail"]))
        summary["clean: new reports a violation (false alarm)"] += not r["old_fail"] and bool(r["new_fail"])
        summary["clean: new says unresolved"] += not r["old_fail"] and r["outcome"] == "UNRESOLVED"
        summary["no clause read"] += r["draft"] != "DRAFTED"
    Path("reports/extractor_eval/closed_loop_eval.json").write_text(
        json.dumps({"rows": rows, "summary": dict(summary)}, indent=1), encoding="utf-8")
    print(json.dumps(dict(summary), indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
