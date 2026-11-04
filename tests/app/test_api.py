"""Product API, end to end on a synthetic plan with planted errors and the example requirement document.

The drafting model is replaced by a fake that answers like the local model would (no Ollama needed)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402

DOC = Path(__file__).parents[2] / "docs" / "requirements_example.md"
RASE = {"requirement": [], "applicability": [], "selection": [], "exception": []}


def frame(prop, subject="room", rooms=(), comp="no_number", number=None, unit="none"):
    return {"property": prop, "subject": subject, "room_types": list(rooms), "avoid_room_types": [],
            "forbidden_pairs": [], "comparison": comp, "number": number, "unit_written": unit,
            "severity": "major", "title": prop, "rase": RASE}


class FakeLLM:
    """Clause id -> frame; every other clause is answered as not checkable on a drawing."""

    model = "fake-llm"
    ANSWERS = {
        "Art. 6.1": frame("clear_width", "door", comp="at_least", number=0.80, unit="m"),
        "Art. 6.4": frame("floor_area", rooms=["living"], comp="at_least", number=14.0, unit="m2"),
    }

    def complete(self, system, user, json_schema):
        cid = json.loads(user.split("CLAUSE_JSON:", 1)[1])["id"]
        return self.ANSWERS.get(cid, frame("fire_resistance"))


@pytest.fixture(scope="module")
def plan(tmp_path_factory):
    out = tmp_path_factory.mktemp("plan")
    return make_plan(out, seed=3, errors=("metric_door_narrow", "comp_unlabelled_room"), png=False)


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "data", llm=lambda: FakeLLM(), workers=1)
    with TestClient(app) as c:
        yield c


def wait(c, pid, job, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            assert rec["status"] == "done", rec.get("error")
            return rec
        time.sleep(0.2)
    raise AssertionError(f"job {job['kind']} did not finish")


def new_project(c, **kw):
    r = c.post("/api/projects", json={"name": "Lot B", "curator": "tester", **kw})
    assert r.status_code == 201
    return r.json()["id"]


def upload(c, pid, kind, path):
    with open(path, "rb") as f:
        r = c.post(f"/api/projects/{pid}/{kind}", files={"file": (Path(path).name, f)})
    assert r.status_code == 202, r.text
    return r.json()


def test_health_and_packs(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["llm"]["available"] and ".dxf" in h["plan_types"] and ".docx" in h["requirement_types"]
    assert any(p["name"] == "starter" and p["rules"] > 0 for p in client.get("/api/packs").json())
    assert client.get("/").status_code == 200 and "ReviewPulse" in client.get("/").text


def test_full_flow(client, plan):
    pid = new_project(client)
    rec = wait(client, pid, upload(client, pid, "plan", plan["dxf"]))
    assert rec["result"]["sheets"] >= 1 and rec["result"]["rooms"] > 0 and rec["result"]["tiers"] == ["T1"]

    fs = client.get(f"/api/projects/{pid}/findings").json()
    fails = {(f["rule_id"], f["verdict"]) for f in fs["findings"]}
    assert ("C-D1", "FAIL") in fails and ("P-1", "FAIL") in fails

    view = client.get(f"/api/projects/{pid}/view").json()
    s = view["sheets"][0]
    assert s["elements"] and s["rooms"] and s["findings"]
    assert all(0 <= x <= s["width"] + 1 and 0 <= y <= s["height"] + 1 for r in s["rooms"] for x, y in r["poly"])
    assert client.get(f"/api/projects/{pid}/sheets/{s['index']}/backdrop.png").headers["content-type"] == "image/png"
    for name in ("report.pdf", "report.html", "findings.csv", "findings.json"):
        assert client.get(f"/api/projects/{pid}/files/{name}").status_code == 200

    # requirements -> drafts -> review -> check with the project's own rules
    rec = wait(client, pid, upload(client, pid, "requirements", DOC))
    assert rec["result"]["drafted"] == 2 and rec["result"]["clauses"] > 10
    drafts = client.get(f"/api/projects/{pid}/drafts").json()
    by = {d["clause_id"]: d for d in drafts}
    living = by["Art. 6.4"]
    assert living["rule"]["check"]["value"] == 14.0 and living["decision"]["state"] == "pending"
    assert by["Art. 8"]["rule"] is None

    # approve an edited version (the curator raises the threshold)
    edited = living["rule_yaml"].replace("value: 14.0", "value: 60.0")
    r = client.post(f"/api/projects/{pid}/drafts/{living['index']}/approve", json={"curator": "tester", "rule_yaml": edited}).json()
    assert r["ok"], r["message"]
    assert str(Path("data")) not in r["message"]
    rid = living["rule"]["id"]
    rec = wait(client, pid, client.post(f"/api/projects/{pid}/check").json())
    own = [f for f in client.get(f"/api/projects/{pid}/findings").json()["findings"] if f["rule_id"] == rid]
    # no living room is 60 m2; the plan's unlabelled room (planted P-1) cannot be typed, so it is
    # reported as not evaluated rather than skipped
    assert own and any(f["verdict"] == "FAIL" for f in own)
    assert all(f["verdict"] in ("FAIL", "NOT_EVALUATED") for f in own)

    # reject the draft again: its rule leaves the pack
    client.post(f"/api/projects/{pid}/drafts/{living['index']}/reject", json={"curator": "tester"})
    wait(client, pid, client.post(f"/api/projects/{pid}/check").json())
    assert not [f for f in client.get(f"/api/projects/{pid}/findings").json()["findings"] if f["rule_id"] == rid]

    # reject the narrow door: the element leaves the model and its width finding with it
    narrow = next(f for f in client.get(f"/api/projects/{pid}/findings").json()["findings"]
                  if f["rule_id"] == "C-D1" and f["verdict"] == "FAIL")
    door = narrow["subject_ids"][0]
    r = client.post(f"/api/projects/{pid}/triage", json={"reject": [door]}).json()
    assert door in r["triage"]["rejected"]
    wait(client, pid, r["job"])
    after = client.get(f"/api/projects/{pid}/findings").json()["findings"]
    assert not any(door in f["subject_ids"] and f["rule_id"] == "C-D1" for f in after)
    view = client.get(f"/api/projects/{pid}/view").json()
    assert next(e for e in view["sheets"][0]["elements"] if e["id"] == door)["state"] == "rejected"

    # undo, and dismiss a finding with a reason
    wait(client, pid, client.post(f"/api/projects/{pid}/triage", json={"unset": [door]}).json()["job"])
    fid = narrow["evidence"]["finding_id"]
    wait(client, pid, client.post(f"/api/projects/{pid}/triage", json={"dismiss": [f"{fid}:checked on site"]}).json()["job"])
    f = next(x for x in client.get(f"/api/projects/{pid}/findings").json()["findings"] if x["evidence"].get("finding_id") == fid)
    assert f["evidence"]["dismissed"] == "checked on site"
    assert any(j["kind"] == "check" for j in client.get(f"/api/projects/{pid}/jobs").json())


def test_errors(client, tmp_path):
    pid = new_project(client)
    bad = tmp_path / "notes.exe"
    bad.write_bytes(b"x")
    with open(bad, "rb") as f:
        r = client.post(f"/api/projects/{pid}/plan", files={"file": ("notes.exe", f)})
    assert r.status_code == 400 and "unsupported" in r.json()["detail"]
    assert client.get("/api/projects/zzzzzzzzzzzz").status_code == 404
    assert client.get("/api/projects/../etc").status_code == 404
    assert client.post(f"/api/projects/{pid}/check").status_code == 400
    assert client.post("/api/projects", json={"name": "x", "base_pack": "nope"}).status_code == 400
    assert client.get(f"/api/projects/{pid}/files/sheet_0.json").status_code == 404


def test_drafting_without_llm(tmp_path):
    app = create_app(tmp_path / "data", llm=lambda: None, workers=1)
    with TestClient(app) as c:
        assert c.get("/api/health").json()["llm"]["available"] is False
        pid = new_project(c, base_pack=None)
        rec = wait(c, pid, upload(c, pid, "requirements", DOC))
        assert rec["result"]["llm"] == "unavailable" and rec["result"]["clauses"] > 10
        assert len(c.get(f"/api/projects/{pid}/clauses").json()) == rec["result"]["clauses"]
        assert c.get(f"/api/projects/{pid}").json()["rules"]["total"] == 0


def test_jobs_interrupted_on_restart(tmp_path):
    from reviewpulse.app.jobs import JobRunner
    from reviewpulse.app.store import Store

    st = Store(tmp_path / "data")
    p = st.create("x")
    (st.dir(p.id) / "jobs" / "abc.json").write_text(json.dumps({"id": "abc", "project": p.id, "kind": "check",
                                                                "status": "running", "created": "2026"}))
    runner = JobRunner(st)
    assert runner.get(p.id, "abc")["status"] == "failed"
    runner.shutdown()
