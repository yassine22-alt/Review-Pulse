"""Every uploaded drawing is kept, and a resubmission is read against the comments sent on the one before."""

import hashlib
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.app.store import Store  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402

DOC = "# Checklist\n\n1.1 Show the location of smoke detectors on the plans.\n\n1.2 Provide a general note about finishes.\n"


class NoModel:
    model = "none"

    def complete(self, *_a):
        raise RuntimeError("no model in this test")


def wait(c, pid, job):
    for _ in range(3000):
        record = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if record["status"] in ("done", "failed"):
            assert record["status"] == "done", record.get("error")
            return record
        time.sleep(0.1)
    raise AssertionError("the job did not finish")


def send(c, pid, path, kind="plan"):
    with open(path, "rb") as f:
        r = c.post(f"/api/projects/{pid}/{kind}", files={"file": (Path(path).name, f)})
    assert r.status_code == 202, r.text
    wait(c, pid, r.json())


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    import os

    os.environ["REVIEWPULSE_EVIDENCE"], os.environ["REVIEWPULSE_PREPARE"] = "off", "off"
    work = tmp_path_factory.mktemp("rounds")
    first = make_plan(work / "a", seed=3, png=False)["pdf"]
    revised = make_plan(work / "b", seed=3, errors=("metric_door_narrow",), png=False)["pdf"]       # one thing is different
    (work / "list.md").write_text(DOC, encoding="utf-8")
    app = create_app(work / "data", llm=lambda: NoModel(), workers=1, auth=False)
    with TestClient(app) as c:
        pid = c.post("/api/projects", json={"name": "p"}).json()["id"]
        send(c, pid, first)
        send(c, pid, work / "list.md", "requirements")
        clause = next(x["id"] for x in c.get(f"/api/projects/{pid}/document").json()["clauses"] if x["id"].endswith("1.1"))
        sheet = c.get(f"/api/projects/{pid}/view").json()["sheets"][0]["id"]
        r = c.put(f"/api/projects/{pid}/clause-states", json={
            "clause": clause, "state": "correction", "reviewer": "Rae", "note": "Show the smoke detectors.",
            "evidence": {"sheet": sheet, "box": [40, 40, 90, 70]}})
        assert r.status_code == 200, r.text
        yield c, pid, Store(work / "data"), Path(first), Path(revised)


def test_one_version_has_nothing_to_compare_with(flow):
    c, pid, store, first, _ = flow
    project = store.get(pid)
    assert [v["id"] for v in project.versions] == [hashlib.sha256(first.read_bytes()).hexdigest()[:16]]
    assert c.get(f"/api/projects/{pid}/back-check").json() == {"available": False,
                                                              "why": "only one version of the drawings has been uploaded"}
    assert c.post(f"/api/projects/{pid}/back-check").status_code == 409


def test_a_new_upload_keeps_the_old_drawing_and_answers_its_comments(flow):
    c, pid, store, first, revised = flow
    send(c, pid, first)                                              # the same bytes are the same version
    assert len(store.get(pid).versions) == 1
    send(c, pid, revised)
    project = store.get(pid)
    old, new = [v["id"] for v in project.versions]
    assert store.version_path(project, old).read_bytes() == first.read_bytes()
    assert store.plan_path(project).read_bytes() == revised.read_bytes()
    before = c.get(f"/api/projects/{pid}/back-check").json()
    assert before["available"] and not before["done"] and before["comments"] == 1
    wait(c, pid, c.post(f"/api/projects/{pid}/back-check").json())
    got = c.get(f"/api/projects/{pid}/back-check").json()
    assert got["done"] and len(got["answers"]) == 1
    answer = got["answers"][0]
    assert "smoke detectors" in answer["comment"]
    assert answer["status"] in {"RESOLVED", "NOT ADDRESSED", "CHANGED BUT NOT SETTLED", "MOVED", "CANNOT TELL"}
    assert answer["place"] is None or answer["place"]["sheet"]
    assert got["old_version"]["id"] == old and got["new_version"]["id"] == new
    assert c.get(f"/api/projects/{pid}/correction-list").json()["cycle"] == 2        # the second round
    assert "old_pdf" not in got


def test_a_project_from_before_versions_keeps_its_drawing_as_the_first_one(tmp_path):
    store = Store(tmp_path / "data")
    p = store.create("old", None, "", "")
    folder = store.dir(p.id) / "inputs" / "plan"
    (folder / "plan.pdf").write_bytes(b"%PDF-1.4 first")
    p.plan = "plan.pdf"
    store.save(p)
    assert store.plan_path(store.get(p.id)).read_bytes() == b"%PDF-1.4 first"
    store.put_input(store.get(p.id), "plan", "plan.pdf", b"%PDF-1.4 second")
    p = store.get(p.id)
    assert len(p.versions) == 2
    assert store.version_path(p, p.versions[0]["id"]).read_bytes() == b"%PDF-1.4 first"
    assert store.plan_path(p).read_bytes() == b"%PDF-1.4 second"
    store.put_input(p, "plan", "plan.pdf", b"%PDF-1.4 first")               # going back is allowed and loses nothing
    p = store.get(p.id)
    assert [store.version_path(p, v["id"]).read_bytes() for v in p.versions] == [b"%PDF-1.4 second", b"%PDF-1.4 first"]


def test_a_version_name_cannot_leave_the_project(tmp_path):
    store = Store(tmp_path / "data")
    p = store.create("x", None, "", "")
    for bad in ("..", "../../x", "A" * 16, ""):
        with pytest.raises(KeyError):
            store.version_dir(p.id, bad)
