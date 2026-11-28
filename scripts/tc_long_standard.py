"""Test case TC-17: how long the app takes to read a long requirement document, through its web API.

The app is run as it is served, with accounts: an upload then stops at the clauses (rules are drafted one at a time when a
reviewer asks). Also timed: the first time the review desk asks for the document afterwards.

    python scripts/tc_long_standard.py data/real_docs/ada_2010.pdf

Prints the seconds from upload until the clauses are listed, how many there are, and a hash of their ids and words, so a run
on a second machine can be compared. No model is asked and the document is never committed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

PASSWORD = "violet harbour ninety lamps"      # a throwaway account in a temporary folder
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests" / "app")]


def main() -> None:
    from fastapi.testclient import TestClient
    from test_scenarios import wait

    from reviewpulse.app.api import create_app

    doc = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Path(tmp), llm=lambda: None, fallback=lambda: None, workers=1)
        app.state.accounts.create_organisation("Test Office", "t@test.test", "Test Reviewer", PASSWORD)
        c = TestClient(app)
        signed = c.post("/api/auth/sign-in", json={"email": "t@test.test", "password": PASSWORD})
        c.headers["x-rp-csrf"] = signed.json()["csrf"]
        pid = c.post("/api/projects", json={"name": "TC-17"}).json()["id"]
        started = time.perf_counter()
        with doc.open("rb") as f:
            r = c.post(f"/api/projects/{pid}/requirements", files={"file": (doc.name, f)})
        wait(c, pid, r.json())
        clauses = c.get(f"/api/projects/{pid}/clauses").json()
        seconds = time.perf_counter() - started
        listed = clauses["clauses"] if isinstance(clauses, dict) else clauses
        digest = hashlib.sha256(json.dumps([[x.get("id"), x.get("text")] for x in listed],
                                           ensure_ascii=False).encode()).hexdigest()[:12]
        again = time.perf_counter()
        assert c.get(f"/api/projects/{pid}/document").status_code == 200
        print(f"{doc.name}: {len(listed)} clauses listed in {seconds:.0f} s (limit 180 s); clause hash {digest}; "
              f"the review desk then got the document in {time.perf_counter() - again:.1f} s")
        app.state.preparer.close()
        app.state.jobs.shutdown()


if __name__ == "__main__":
    main()
