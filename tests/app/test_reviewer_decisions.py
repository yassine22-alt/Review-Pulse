"""A reviewer can decide any requirement by hand, with or without the tool: under their name, with evidence that exists."""

import json
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("argon2")

from fastapi.testclient import TestClient  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402

PW = "violet harbour ninety lamps"
DOC = ("# Checklist\n\n1.1 Show the location of smoke detectors on the plans.\n\n1.2 Every door shall have a clear width of "
       "at least 0.80 m.\n\n1.3 Provide the energy compliance form with the application.\n\n1.4 Truss drawings shall be provided.\n")


class NoModel:
    model = "none"

    def complete(self, *_a):
        raise AssertionError("deciding by hand must not ask a model")


def wait(c, pid, job):
    for _ in range(1200):
        record = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if record["status"] in ("done", "failed"):
            assert record["status"] == "done", record.get("error")
            return
        time.sleep(0.1)
    raise AssertionError("the job did not finish")


@pytest.fixture(scope="module")
def review(tmp_path_factory):
    import os

    os.environ["REVIEWPULSE_EVIDENCE"] = "off"             # note search by words only: no model on the test machine
    work = tmp_path_factory.mktemp("decide")
    plan = make_plan(work / "plan", seed=3, png=False)
    app = create_app(work / "data", llm=lambda: NoModel(), workers=1)
    app.state.accounts.create_organisation("Office", "r@o.test", "Rae Reviewer", PW)
    c = TestClient(app)
    c.__enter__()
    c.headers["x-rp-csrf"] = c.post("/api/auth/sign-in", json={"email": "r@o.test", "password": PW}).json()["csrf"]
    pid = c.post("/api/projects", json={"name": "p"}).json()["id"]
    with open(plan["pdf"], "rb") as f:
        wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": ("plan.pdf", f)}).json())
    wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": ("list.md", DOC.encode())}).json())
    view = c.get(f"/api/projects/{pid}/view").json()
    clauses = [x["id"] for x in c.get(f"/api/projects/{pid}/document").json()["clauses"]]
    yield c, pid, view["sheets"][0]["id"], clauses
    c.__exit__(None, None, None)


def put(c, pid, **body):
    return c.put(f"/api/projects/{pid}/clause-states", json=body)


def listing(c, pid):
    return c.get(f"/api/projects/{pid}/correction-list").json()


def clause(clauses, number):
    return next(x for x in clauses if x.endswith(number))


def test_notes_are_found_without_any_model(review):
    c, pid, _sheet, clauses = review
    r = c.get(f"/api/projects/{pid}/notes", params={"clause": clause(clauses, "1.1")})
    assert r.status_code == 200, r.text
    assert "candidates" in r.json() and r.json()["notes_on_drawings"] >= 0
    assert c.get(f"/api/projects/{pid}/notes", params={"clause": "9.9"}).status_code == 409


def test_a_decision_needs_what_makes_it_checkable(review):
    c, pid, sheet, clauses = review
    one = clause(clauses, "1.1")
    assert put(c, pid, clause=one, state="shown").status_code == 400                       # no evidence, no pass
    assert put(c, pid, clause=one, state="correction").status_code == 400                  # no comment
    assert put(c, pid, clause="9.9", state="shown", note="x").status_code == 400           # no such requirement
    for bad in ({"sheet": "nowhere"}, {"sheet": sheet, "box": [0, 0, 1e9, 1e9]}, {"sheet": sheet, "box": [5, 5, 1, 1]},
                {"sheet": sheet, "box": [1, 2]}):
        assert put(c, pid, clause=one, state="shown", evidence=bad).status_code == 400, bad
    assert listing(c, pid)["shown"] == []


def test_every_requirement_can_be_completed_and_the_record_says_who(review):
    c, pid, sheet, clauses = review
    before = listing(c, pid)
    assert before["uncovered_clauses"] == len(clauses) == 4
    place = {"sheet": sheet, "box": [10, 10, 60, 20], "text": "SMOKE DETECTOR IN EACH ROOM"}
    assert put(c, pid, clause=clause(clauses, "1.1"), state="shown", evidence=place, reviewer="Someone Else").status_code == 200
    assert put(c, pid, clause=clause(clauses, "1.2"), state="correction", note="Widen door P5 to 0.80 m",
               evidence={"sheet": sheet, "box": [100, 100, 130, 120]}).status_code == 200
    assert put(c, pid, clause=clause(clauses, "1.3"), state="not_applicable", note="no new envelope").status_code == 200
    assert put(c, pid, clause=clause(clauses, "1.4"), state="deferred", note="truss supplier, before framing").status_code == 200

    data = listing(c, pid)
    assert data["uncovered_clauses"] == 0
    assert [s["clause"] for s in data["shown"]] == [clause(clauses, "1.1")] and data["shown"][0]["by"] == "Rae Reviewer"
    [item] = data["items"]
    assert item["decided_by"] == "Rae Reviewer" and item["status"] == "revision_required"
    assert item["wording"].startswith("Widen door P5 to 0.80 m. Requirement: \"")
    assert "clear width of at least 0.80 m" in item["quote"] and item["locations"][0]["bbox"] == [100, 100, 130, 120]
    assert item["review"] == {**item["review"], "action": "accept", "by": "Rae Reviewer"}
    assert data["edit_burden"]["items"] == 0 and data["edit_burden"]["written_by_reviewer"] == 1   # not the tool's proposal
    assert data["overall"]["result"] == "Revision required"

    record = c.get(f"/api/projects/{pid}/coverage").json()
    assert record["summary"]["decided"] == 4
    page = c.get(f"/api/projects/{pid}/coverage.html").text
    assert "Shown on the plans (decided by a reviewer)" in page and "Rae Reviewer" in page and "Someone Else" not in page
    assert "Widen door P5" in c.get(f"/api/projects/{pid}/correction-list?format=txt").text
    marked = c.get(f"/api/projects/{pid}/correction-list?format=pdf")
    assert marked.status_code == 200 and marked.content.startswith(b"%PDF")
    assert "Someone Else" not in json.dumps(c.get(f"/api/projects/{pid}/audit").json())


def test_taking_a_decision_back_leaves_the_requirement_undecided_again(review):
    c, pid, _sheet, clauses = review
    assert put(c, pid, clause=clause(clauses, "1.2"), state="reset").status_code == 200
    data = listing(c, pid)
    assert data["items"] == [] and data["uncovered_clauses"] == 1
    assert data["overall"]["result"] != "Approved"                        # an undecided requirement is never a pass


def test_a_decision_stops_counting_when_the_drawings_or_the_words_change(review, tmp_path):
    """A pass must never rest on drawings that were replaced."""
    c, pid, sheet, clauses = review
    one, four = clause(clauses, "1.1"), clause(clauses, "1.4")
    for cid in (one, four):
        put(c, pid, clause=cid, state="reset")
    assert put(c, pid, clause=one, state="shown", note="detail 4").status_code == 200
    assert put(c, pid, clause=four, state="deferred", note="truss supplier").status_code == 200
    assert one in [s["clause"] for s in listing(c, pid)["shown"]]

    other = make_plan(tmp_path / "other", seed=11, png=False)
    with open(other["pdf"], "rb") as f:
        wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": ("plan.pdf", f)}).json())
    states = c.get(f"/api/projects/{pid}/clause-states").json()
    assert states[one]["stale"] == "the drawings were replaced" and states[one]["by"] == "Rae Reviewer"       # kept, not counted
    assert states[four]["stale"] is None                                     # a deferral does not rest on the drawings
    data = listing(c, pid)
    assert one not in [s["clause"] for s in data["shown"]] and data["overall"]["result"] != "Approved"
    record = c.get(f"/api/projects/{pid}/coverage").json()
    assert next(x for x in record["clauses"] if x["id"] == one)["status"] != "reviewer_shown"

    changed = DOC.replace("smoke detectors", "smoke and heat detectors").replace("Truss drawings", "Roof truss drawings")
    wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": ("list.md", changed.encode())}).json())
    states = c.get(f"/api/projects/{pid}/clause-states").json()
    assert "words changed" in states[one]["stale"] and "words changed" in states[four]["stale"]
    assert listing(c, pid)["deferred"] == []
    assert put(c, pid, clause=one, state="shown", note="confirmed on the new set").status_code == 200          # deciding again works
    assert c.get(f"/api/projects/{pid}/clause-states").json()[one]["stale"] is None


def test_each_part_is_searched_and_only_a_shown_part_can_be_ticked(review):
    c, pid, _sheet, clauses = review
    two = clause(clauses, "1.2")
    got = c.get(f"/api/projects/{pid}/parts", params={"clause": two})
    assert got.status_code == 200, got.text
    body = got.json()
    # the test model refuses every question, so the requirement stands whole: searching still works without a model
    assert not body["split_by_model"] and len(body["parts"]) == 1
    part = body["parts"][0]["text"]
    assert {"notes", "written"} <= set(body["parts"][0])
    assert put(c, pid, clause=two, state="correction", note="x", parts=[{"text": "a guard rail", "mark": "missing"}]).status_code == 400
    assert put(c, pid, clause=two, state="correction", note="x", parts=[{"text": part, "mark": "maybe"}]).status_code == 400
    assert put(c, pid, clause=two, state="shown", note="x", parts=[{"text": part, "mark": "missing"}]).status_code == 400
    ok = put(c, pid, clause=two, state="correction", note="Show it.", parts=[{"text": part, "mark": "missing"}])
    assert ok.status_code == 200, ok.text
    assert c.get(f"/api/projects/{pid}/clause-states").json()[two]["parts"] == [{"text": part, "mark": "missing"}]
    assert put(c, pid, clause=two, state="reset").status_code == 200
