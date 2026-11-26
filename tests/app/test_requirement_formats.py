"""A requirement document may arrive as a spreadsheet, a web page, a csv file or a scan: the app accepts it and lists its clauses."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402

ITEMS = ["Hallways must be at least 0.9 m wide.", "Every habitable room shall have a window.",
         "Exit doors shall be at least 0.8 m wide."]


class _NoModel:
    model = "none"

    def complete(self, system, user, schema):
        return {}


def _client(tmp_path):
    return TestClient(create_app(tmp_path / "data", llm=lambda: _NoModel(), workers=1, auth=False))


def _upload(c, pid, name, data):
    r = c.post(f"/api/projects/{pid}/requirements", files={"file": (name, data)})
    assert r.status_code == 202, r.text
    return r.json()


def _wait(c, pid, job):
    import time

    for _ in range(300):
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            return rec
        time.sleep(0.2)
    raise AssertionError("the upload job did not finish")


def _texts(c, pid):
    return [" ".join(x["text"].split()) for x in c.get(f"/api/projects/{pid}/clauses").json()]


def test_the_health_check_lists_the_new_requirement_types(tmp_path):
    with _client(tmp_path) as c:
        types = c.get("/api/health").json()["requirement_types"]
    for t in (".xlsx", ".csv", ".html", ".png", ".docx", ".pdf"):
        assert t in types


@pytest.mark.parametrize("name,build", [
    ("checks.xlsx", "xlsx"), ("checks.csv", "csv"), ("checks.html", "html")])
def test_a_checklist_in_another_format_is_read_into_clauses(tmp_path, name, build):
    if build == "xlsx":
        import io

        import openpyxl

        wb = openpyxl.Workbook()
        for i, t in enumerate(ITEMS, 1):
            wb.active.append([i, t, "yes / no"])
        buf = io.BytesIO()
        wb.save(buf)
        data = buf.getvalue()
    elif build == "csv":
        data = ("Code;Requirement\n" + "\n".join(f"R{i};{t}" for i, t in enumerate(ITEMS, 1))).encode()
    else:
        data = ("<html><body><h1>Checklist</h1><ul>" + "".join(f"<li>{t}</li>" for t in ITEMS) + "</ul></body></html>").encode()
    with _client(tmp_path) as c:
        pid = c.post("/api/projects", json={"name": "x", "curator": "t"}).json()["id"]
        _wait(c, pid, _upload(c, pid, name, data))
        got = _texts(c, pid)
    joined = " ".join(got)
    for t in ITEMS:
        assert t in joined, (t, got)
