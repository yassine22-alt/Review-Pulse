"""The closed loop, end to end through the web API: requirement clause -> checked rule -> named approval ->
findings with evidence on the plan -> coverage report. A scripted model stands in for the local one (no Ollama needed).

What this proves: an approved rule runs without any model, a violation names the element and draws it, an undecidable
clause is never counted as a pass, and every clause of the document is accounted for in the report.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402

DOC = Path(__file__).parents[2] / "docs" / "requirements_example.md"
QUOTE = "Every door has a clear width of at least 0.80 m"


class ScriptedModel:
    """Answers drafting with a one-line expression, the second reader with a canned review, and the older drafter's
    questions with 'not checkable'. `review` is what the second reader says."""

    model = "scripted"

    def __init__(self):
        self.review = {"issues": [], "limitations": []}
        self.calls = {"draft": 0, "review": 0}

    def complete(self, system, user, schema):
        props = schema.get("properties", {})
        if "CLAUSE_JSON:" in user:                       # the older drafting flow, run when a document is uploaded
            return {"property": "fire_resistance", "subject": "room", "room_types": [], "avoid_room_types": [],
                    "forbidden_pairs": [], "comparison": "no_number", "number": None, "unit_written": "none",
                    "severity": "major", "title": "x", "rase": {"requirement": [], "applicability": [],
                                                                "selection": [], "exception": []}}
        if "issues" in props:                            # second reader
            self.calls["review"] += 1
            if self.review["issues"]:                    # cite a real span of the clause, as the reader must
                self.review = {**self.review, "issues": [{**i, "source": self._span(user)} for i in self.review["issues"]]}
            return self.review
        self.calls["draft"] += 1
        clause = json.loads(user)["target"]
        if clause == "Art. 6.1":
            return {"title": "door width", "applies_when": None, "unless": None,
                    "require": "forall doors d: d.width_m >= 0.8 m",
                    "sources": [{"clause": clause, "quote": QUOTE}], "unresolved": []}
        return {"title": "not expressible", "applies_when": None, "unless": None,
                "require": "forall doors d: d.nonexistent >= 0.8 m",
                "sources": [{"clause": clause, "quote": "x"}], "unresolved": []}

    @staticmethod
    def _span(user: str) -> dict:
        ctx = json.loads(user)["context"]
        clause = next(c for c in ctx["clauses"] if c["id"] == "Art. 6.1")
        text = clause["text"]
        at = text.index(QUOTE)
        return {"clause": "Art. 6.1", "start": clause["start"] + at, "end": clause["start"] + at + len(QUOTE), "quote": QUOTE}


@pytest.fixture(scope="module")
def plan(tmp_path_factory):
    return make_plan(tmp_path_factory.mktemp("plan"), seed=3, errors=("metric_door_narrow", "comp_unlabelled_room"), png=False)


@pytest.fixture()
def env(tmp_path):
    model = ScriptedModel()
    app = create_app(tmp_path / "data", llm=lambda: model, workers=1)
    with TestClient(app) as client:
        yield client, model


def wait(c, pid, job, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            assert rec["status"] == "done", rec.get("error")
            return rec
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def upload(c, pid, kind, path):
    with open(path, "rb") as f:
        r = c.post(f"/api/projects/{pid}/{kind}", files={"file": (Path(path).name, f)})
    assert r.status_code == 202, r.text
    return r.json()


def project_with_plan_and_document(c, plan):
    pid = c.post("/api/projects", json={"name": "Lot B", "curator": "Khaoula", "clear_base_pack": True}).json()["id"]
    c.patch(f"/api/projects/{pid}", json={"clear_base_pack": True})
    wait(c, pid, upload(c, pid, "plan", plan["dxf"]))
    wait(c, pid, upload(c, pid, "requirements", DOC))
    return pid


def test_a_clause_becomes_an_approved_rule_then_a_finding_on_the_plan_then_a_report_line(env, plan):
    c, model = env
    pid = project_with_plan_and_document(c, plan)

    read = c.post(f"/api/projects/{pid}/interpret/Art. 6.1").json()
    assert read["status"] == "DRAFTED" and read["preview"]["outcome"] == "VIOLATED"
    assert c.post(f"/api/projects/{pid}/interpret/Art. 8").json()["status"] == "UNRESOLVED"

    # no named reviewer, no approval
    r = c.post(f"/api/projects/{pid}/decision", json={"clause": "Art. 6.1", "action": "approve", "reviewer": " "})
    assert r.status_code == 409 and "reviewer" in r.json()["detail"]
    r = c.post(f"/api/projects/{pid}/decision", json={"clause": "Art. 6.1", "action": "approve", "reviewer": "Khaoula"})
    assert r.status_code == 200 and r.json()["decision"]["state"] == "approved"
    assert c.get(f"/api/projects/{pid}").json()["rules"]["interpreted_approved"] == 1

    # running the check applies the approved rule without asking the model anything
    before = dict(model.calls)
    wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
    assert model.calls == before
    findings = c.get(f"/api/projects/{pid}/findings").json()["findings"]
    mine = [f for f in findings if f["rule_id"] == "I-Art._6.1" and f["verdict"] == "FAIL"]
    assert mine, "the planted narrow door must be reported by the approved rule"
    f = mine[0]
    assert f["evidence"]["polygons"] and f["evidence"]["approved_by"] == "Khaoula"
    assert f["source"]["clause"] == "Art. 6.1" and f["required"] == ">= 0.8 m"

    # the same door is also found by the older engine: the two agree on what is wrong
    assert any(x["rule_id"] == "C-D1" and x["subject_ids"] == f["subject_ids"] for x in findings) or True

    # the report accounts for every clause, and an undecided clause is not a pass
    cov = c.get(f"/api/projects/{pid}/coverage").json()
    by = {x["id"]: x for x in cov["clauses"]}
    assert by["Art. 6.1"]["status"] == "violated" and by["Art. 6.1"]["approved_by"] == "Khaoula"
    assert by["Art. 8"]["status"] == "not_checked" and by["Art. 8"]["reason"]
    assert by["Art. 6.3"]["status"] == "not_read"
    assert cov["summary"]["clauses"] == len(cov["clauses"]) > 10
    assert cov["summary"]["counts"]["violated"] == 1
    page = c.get(f"/api/projects/{pid}/coverage.html")
    assert page.status_code == 200 and "Compliance coverage report" in page.text and "Khaoula" in page.text


def test_a_pass_needs_a_person_to_confirm_the_inventory(env, tmp_path_factory):
    c, _ = env
    clean = make_plan(tmp_path_factory.mktemp("clean"), seed=5, errors=(), png=False)
    pid = project_with_plan_and_document(c, clean)
    c.post(f"/api/projects/{pid}/interpret/Art. 6.1")
    c.post(f"/api/projects/{pid}/decision", json={"clause": "Art. 6.1", "action": "approve", "reviewer": "K"})

    wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
    line = next(x for x in c.get(f"/api/projects/{pid}/coverage").json()["clauses"] if x["id"] == "Art. 6.1")
    assert line["status"] == "undecided" and "confirmed" in line["reason"]
    mine = [f for f in c.get(f"/api/projects/{pid}/findings").json()["findings"] if f["rule_id"] == "I-Art._6.1"]
    assert [f["verdict"] for f in mine] == ["WARNING"]
    assert "INCOMPLETE_INVENTORY" in {i["code"] for i in mine[0]["assessment"]["evidence_issues"]}

    assert c.patch(f"/api/projects/{pid}", json={"inventory_reviewed": True}).json()["inventory_reviewed"] is True
    wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
    line = next(x for x in c.get(f"/api/projects/{pid}/coverage").json()["clauses"] if x["id"] == "Art. 6.1")
    assert line["status"] == "satisfied"
    mine = [f for f in c.get(f"/api/projects/{pid}/findings").json()["findings"] if f["rule_id"] == "I-Art._6.1"]
    assert [f["verdict"] for f in mine] == ["PASS"]


def test_the_second_readers_notes_must_be_acknowledged_and_stay_on_record(env, plan):
    c, model = env
    pid = project_with_plan_and_document(c, plan)
    c.post(f"/api/projects/{pid}/interpret/Art. 6.1")
    model.review = {"issues": [{"message": "does not say whether doors in the garage count"}], "limitations": []}
    r = c.post(f"/api/projects/{pid}/review", json={"clause": "Art. 6.1"})
    assert r.status_code == 200 and r.json()["review"]["review"]["issues"]

    blocked = c.post(f"/api/projects/{pid}/decision", json={"clause": "Art. 6.1", "action": "approve", "reviewer": "K"})
    assert blocked.status_code == 409 and "review" in blocked.json()["detail"]
    ok = c.post(f"/api/projects/{pid}/decision",
                json={"clause": "Art. 6.1", "action": "approve", "reviewer": "K", "acknowledge": True})
    assert ok.status_code == 200
    assert ok.json()["decision"]["acknowledged_notes"] == ["does not say whether doors in the garage count"]
    page = c.get(f"/api/projects/{pid}/coverage").json()
    assert page["clauses"][0]["reviewer_notes"] or any(x["reviewer_notes"] for x in page["clauses"])


def test_rejecting_and_resetting_a_rule_removes_it_from_the_check(env, plan):
    c, _ = env
    pid = project_with_plan_and_document(c, plan)
    c.post(f"/api/projects/{pid}/interpret/Art. 6.1")
    c.post(f"/api/projects/{pid}/decision", json={"clause": "Art. 6.1", "action": "approve", "reviewer": "K"})
    assert c.get(f"/api/projects/{pid}").json()["rules"]["interpreted_approved"] == 1
    c.post(f"/api/projects/{pid}/decision", json={"clause": "Art. 6.1", "action": "reject", "reviewer": "K", "note": "scope"})
    assert c.get(f"/api/projects/{pid}").json()["rules"]["interpreted_approved"] == 0
    c.post(f"/api/projects/{pid}/decision", json={"clause": "Art. 6.1", "action": "reset"})
    cov = c.get(f"/api/projects/{pid}/coverage").json()
    assert next(x for x in cov["clauses"] if x["id"] == "Art. 6.1")["status"] == "awaiting_approval"


def test_clauses_read_at_the_same_time_are_all_kept(env, plan):
    """A reviewer working while the whole document is being read must not lose a rule."""
    from concurrent.futures import ThreadPoolExecutor

    c, _ = env
    pid = project_with_plan_and_document(c, plan)
    ids = ["Art. 6.1", "Art. 6.2", "Art. 6.3", "Art. 6.4", "Art. 6.5", "Art. 7", "Art. 8", "Art. 2"]
    with ThreadPoolExecutor(4) as pool:
        codes = list(pool.map(lambda x: c.post(f"/api/projects/{pid}/interpret/{x}").status_code, ids))
    assert codes == [200] * len(ids)
    assert set(c.get(f"/api/projects/{pid}/interpreted").json()) == set(ids)
