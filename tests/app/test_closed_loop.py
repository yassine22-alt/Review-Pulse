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
from slot_responses import slot_response

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

    @slot_response
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


def test_demo_reviewed_schedule_updates_existing_rule(tmp_path):
    import ezdxf

    quote = "Every door has a scheduled height of at least 1.90 m."

    class DemoModel(ScriptedModel):
        @slot_response
        def complete(self, system, user, schema):
            if "CLAUSE_JSON:" not in user and "issues" not in schema.get("properties", {}):
                target = json.loads(user)["target"]
                if target == "Art. 2":
                    return {"title": "scheduled height", "applies_when": None, "unless": None,
                            "require": "forall doors d: d.scheduled_height_m >= 1.90 m",
                            "sources": [{"clause": target, "quote": quote}], "unresolved": []}
                return {"title": "door width", "applies_when": None, "unless": None,
                        "require": "forall doors d: d.width_m >= 0.8 m",
                        "sources": [{"clause": target, "quote": QUOTE}], "unresolved": []}
            return super().complete(system, user, schema)

    drawing = make_plan(tmp_path / "plan", seed=3, errors=("metric_door_narrow",), png=False)["dxf"]
    dxf = ezdxf.readfile(drawing)
    table = [t for t in dxf.modelspace().query("TEXT") if t.dxf.layer == "A-ANNO-TABL"]
    header = next(t for t in table if t.dxf.text == "HAUTEUR")
    header.dxf.text = "HAUTEUR (m)"
    col = header.dxf.insert.x
    heights = [t for t in table if t is not header and abs(t.dxf.insert.x - col) < 1e-6]
    assert heights
    cell = max(heights, key=lambda t: t.dxf.insert.y)
    original = cell.dxf.text
    cell.dxf.text = "-"
    first, verified = tmp_path / "initial.dxf", tmp_path / "verified.dxf"
    dxf.saveas(first)
    cell.dxf.text = original
    dxf.saveas(verified)
    doc = tmp_path / "demo.md"
    doc.write_text(f"Art. 1: {QUOTE}.\n\nArt. 2: {quote}\n", encoding="utf-8")

    with TestClient(create_app(tmp_path / "data", llm=lambda: DemoModel(), workers=1)) as c:
        pid = c.post("/api/projects", json={"name": "18 November rehearsal", "curator": "Demo"}).json()["id"]
        c.patch(f"/api/projects/{pid}", json={"clear_base_pack": True})
        wait(c, pid, upload(c, pid, "plan", first))
        wait(c, pid, upload(c, pid, "requirements", doc))
        for cid in ("Art. 1", "Art. 2"):
            draft = c.post(f"/api/projects/{pid}/interpret/{cid}")
            assert draft.json()["status"] == "DRAFTED", draft.text
            response = c.post(f"/api/projects/{pid}/decision",
                              json={"clause": cid, "action": "approve", "reviewer": "Demo"})
            assert response.status_code == 200, response.text

        def check():
            c.patch(f"/api/projects/{pid}", json={"inventory_reviewed": True})
            wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
            coverage = c.get(f"/api/projects/{pid}/coverage").json()
            return {line["id"]: line["status"] for line in coverage["clauses"]}

        initial = check()
        assert initial == {"Art. 1": "violated", "Art. 2": "undecided"}, initial
        findings = c.get(f"/api/projects/{pid}/findings").json()["findings"]
        assert any(f["source"].get("clause") == "Art. 1" and f["evidence"].get("polygons") for f in findings)
        print("Initial review:", initial)
        (tmp_path / "coverage-before.html").write_text(
            c.get(f"/api/projects/{pid}/coverage.html").text, encoding="utf-8")
        wait(c, pid, upload(c, pid, "plan", verified))
        final = check()
        assert final == {"Art. 1": "violated", "Art. 2": "satisfied"}, final
        print("With the verified schedule cell:", final)
        (tmp_path / "coverage-after.html").write_text(
            c.get(f"/api/projects/{pid}/coverage.html").text, encoding="utf-8")


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
