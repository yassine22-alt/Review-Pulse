"""Drive the closed loop against a running app with the real local model: second reader, named approval, check,
findings with evidence, and the coverage report. Usage: python scripts/closed_loop_demo.py <project id> [reviewer]"""
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
pid = sys.argv[1]
reviewer = sys.argv[2] if len(sys.argv) > 2 else "Khaoula"
c = httpx.Client(base_url=BASE, timeout=600)


def say(msg=""):
    print(msg, flush=True)


entries = c.get(f"/api/projects/{pid}/interpreted").json()
drafted = [k for k, v in entries.items() if v["status"] == "DRAFTED"]
say(f"[1] {len(drafted)} clauses have a rule waiting: {drafted}")
for cid in drafted:
    t0 = time.time()
    rv = c.post(f"/api/projects/{pid}/review", json={"clause": cid}).json()
    notes = [i["message"] for i in rv["review"]["review"]["issues"]] + rv["review"]["review"]["limitations"]
    say(f"[2] {cid}: second reader in {time.time() - t0:.0f}s, {len(notes)} note(s)")
    for n in notes[:2]:
        say(f"       note: {n[:110]}")
    r = c.post(f"/api/projects/{pid}/decision",
               json={"clause": cid, "action": "approve", "reviewer": reviewer, "acknowledge": bool(notes)})
    say(f"    approve -> {r.status_code} {r.json().get('decision', {}).get('state') or r.json().get('detail')}")
c.patch(f"/api/projects/{pid}", json={"inventory_reviewed": True})
say("[3] inventory confirmed by the reviewer")
job = c.post(f"/api/projects/{pid}/check").json()
while c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()["status"] not in ("done", "failed"):
    time.sleep(1)
say("[4] check finished")
for f in c.get(f"/api/projects/{pid}/findings").json()["findings"]:
    if f["evidence"].get("interpreted"):
        say(f"    {f['verdict']:<14} {f['rule_id']:<12} {f['message'][:100]}")
cov = c.get(f"/api/projects/{pid}/coverage").json()
s = cov["summary"]
say(f"[5] coverage: {s['decided']} of {s['clauses']} clauses decided ({round(100 * s['decided_share'])}%)")
say("    " + ", ".join(f"{k} {v}" for k, v in s["counts"].items() if v))
open("reports/extractor_eval/coverage_demo.html", "w", encoding="utf-8").write(c.get(f"/api/projects/{pid}/coverage.html").text)
say("[6] report saved: reports/extractor_eval/coverage_demo.html")
