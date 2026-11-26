"""Run the correction list flow on a real plan and a real checklist with no model (a client that declines every question, so
only the program built arms run: measured limits that need no model are not attempted, the mention arm is). Prints counts and
writes the exports under the given folder.

    python scripts/correction_list_demo.py data/real_plans/chief_architect_austin.pdf data/real_docs/us_stpete_residential_checklist.pdf out/
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from reviewpulse.app.api import create_app


class Declines:
    """Answers every question with an empty object: nothing it says passes the code's checks."""

    model = "declines"
    external = False

    def complete(self, system, user, schema):
        return {}


def wait(c, pid, job):
    while True:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            assert rec["status"] == "done", rec.get("error")
            return
        time.sleep(0.5)


def main(plan: Path, doc: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with TestClient(create_app(Path(tempfile.mkdtemp()), llm=lambda: Declines(), workers=1)) as c:
        pid = c.post("/api/projects", json={"name": "demo", "curator": "Demo Reviewer"}).json()["id"]
        wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": (plan.name, plan.read_bytes())}).json())
        wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": (doc.name, doc.read_bytes())}).json())
        clauses = c.get(f"/api/projects/{pid}/document").json()["clauses"]
        drafted = approved = 0
        for cl in clauses:
            r = c.post(f"/api/projects/{pid}/interpret/{cl['id']}")
            if r.status_code == 200 and r.json()["status"] == "DRAFTED":
                drafted += 1
                d = c.post(f"/api/projects/{pid}/decision", json={"clause": cl["id"], "action": "approve", "reviewer": "Demo Reviewer"})
                approved += d.status_code == 200
        print(f"clauses {len(clauses)}, rules written {drafted}, approved {approved}")
        if approved:
            wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
        data = c.get(f"/api/projects/{pid}/correction-list").json()
        print("items", len(data["items"]), "overall", data["overall"]["label"], "uncovered", data["uncovered_clauses"])
        for fmt, name in (("txt", "list.txt"), ("html", "list.html"), ("pdf", "markup.pdf"), ("bcf", "list.bcf"), ("csv", "list.csv")):
            r = c.get(f"/api/projects/{pid}/correction-list?format={fmt}")
            print(fmt, r.status_code, len(r.content))
            if r.status_code == 200:
                (out / name).write_bytes(r.content)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
