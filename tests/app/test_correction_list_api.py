"""The correction list through the web API on generated demo plans: the real flow, no model (a scripted one writes the rules).

Covers the three formats, the marked up PDF (annotations titled with the item number, placed on drawn content, also on a page
rotated 90 degrees), the reviewer's accept / edit / drop with the edit count, deferred clauses, sign off per discipline with a
required name, the audit trail and the browser route.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from test_scenarios import DOC, RULES, Scripted, wait  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402
from reviewpulse.synth.scenarios import SCENARIOS  # noqa: E402


def scenario(name):
    return next(s for s in SCENARIOS if s[0] == name)[2]


def flow(tmp_path, kw, plan_kind="pdf"):
    paths = make_plan(tmp_path / "plan", png=False, **kw)
    c = TestClient(create_app(tmp_path / "data", llm=lambda: Scripted(), workers=1, auth=False))
    c.__enter__()
    pid = c.post("/api/projects", json={"name": "demo", "curator": "Test Reviewer", "base_pack": "starter"}).json()["id"]
    with open(paths[plan_kind], "rb") as f:
        wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": (f"plan.{plan_kind}", f)}).json())
    with open(DOC, "rb") as f:
        wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": ("req.md", f)}).json())
    for clause in RULES:
        if c.post(f"/api/projects/{pid}/interpret/{clause}").json()["status"] == "DRAFTED":
            c.post(f"/api/projects/{pid}/decision", json={"clause": clause, "action": "approve", "reviewer": "Test Reviewer"})
    wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
    return c, pid


@pytest.fixture(scope="module")
def narrow_door(tmp_path_factory):
    c, pid = flow(tmp_path_factory.mktemp("narrow"), scenario("02_door_too_narrow"))
    yield c, pid
    c.__exit__(None, None, None)


@pytest.fixture()
def fresh(tmp_path):
    c, pid = flow(tmp_path, scenario("02_door_too_narrow"), "dxf")
    yield c, pid
    c.__exit__(None, None, None)


def listing(c, pid):
    r = c.get(f"/api/projects/{pid}/correction-list")
    assert r.status_code == 200, r.text
    return r.json()


def door_item(data):
    return next(i for i in data["items"] if i["clause"] == "Art. 6.1")


def test_json_list_has_the_planted_door_with_its_citation_sheet_and_state(narrow_door):
    c, pid = narrow_door
    data = listing(c, pid)
    item = door_item(data)
    assert item["status_label"] == "Revision required" and item["outcome"] == "Violated"
    assert item["citation"] == "[Art. 6.1]"
    assert "Every door has a clear width of at least 0.80 m" in item["quote"]
    assert item["quote"] in item["wording"] and item["citation"] in item["wording"]
    loc = item["locations"][0]
    assert loc["page"] == 1 and loc["bbox"] and "of the sheet" in loc["where"]
    assert any("0.7" in f["statement"] and "measured on sheet" in f["source"] for f in item["facts"])
    assert data["overall"]["result"] == "Revision required"
    assert [i["n"] for i in data["items"]] == list(range(1, len(data["items"]) + 1))


def test_undecided_items_are_information_requested_with_one_question_never_approved(narrow_door):
    c, pid = narrow_door
    data = listing(c, pid)
    asked = [i for i in data["items"] if i["status"] == "information_requested"]
    assert asked, "the demo plan has clauses that could not be decided without a confirmed inventory"
    for i in asked:
        assert i["question"].endswith(("?", ".")) and i["question"] in i["wording"]
        assert i["status_label"] == "Information requested" and i["status"] != "approved"


def test_text_and_html_formats_and_a_bad_format(narrow_door):
    c, pid = narrow_door
    data = listing(c, pid)
    text = c.get(f"/api/projects/{pid}/correction-list?format=txt")
    page = c.get(f"/api/projects/{pid}/correction-list?format=html")
    assert text.status_code == page.status_code == 200
    assert "text/plain" in text.headers["content-type"] and "text/html" in page.headers["content-type"]
    for item in data["items"]:
        assert item["wording"] in text.text
    assert "[Art. 6.1]" in text.text and "Correction list" in page.text
    assert c.get(f"/api/projects/{pid}/correction-list?format=xlsx").status_code == 400
    csv = c.get(f"/api/projects/{pid}/correction-list?format=csv")
    assert csv.status_code == 200 and "Art. 6.1" in csv.text or "Revise the plans" in csv.text
    bcf = c.get(f"/api/projects/{pid}/correction-list?format=bcf")
    assert bcf.status_code == 200 and bcf.content[:2] == b"PK"
    assert c.get(f"/api/projects/{pid}/correction-list?format=json&file=true").json()["comments"]
    for out in (text.text, page.text, str(data)):
        assert "—" not in out and "–" not in out


def _frame_hits(page, rect):
    """Drawn content (not annotations) under a rectangle: independent of how the annotation was placed."""
    return [d for d in page.get_drawings() if d["rect"].intersects(rect)]


def test_marked_up_pdf_has_titled_annotations_on_the_drawn_door(narrow_door):
    c, pid = narrow_door
    data = listing(c, pid)
    r = c.get(f"/api/projects/{pid}/correction-list.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and "application/pdf" in r.headers["content-type"]
    doc = pymupdf.open(stream=r.content, filetype="pdf")
    found = {}
    for page in doc:
        for a in page.annots():
            if a.info["subject"]:
                found.setdefault(a.info["subject"], []).append((page, a.type[1], a.rect, a.info["content"]))
    assert set(found) == {str(i["n"]) for i in data["items"]}
    page, kind, rect, content = next(v for v in found[str(door_item(data)["n"])] if v[1] == "Polygon")
    assert "[Art. 6.1]" in content
    assert page.rect.contains(rect) and _frame_hits(page, rect), "the box must sit on drawn content"
    assert {k for v in found.values() for _, k, _, _ in v} >= {"Polygon", "FreeText", "Text"}      # Text: items with no spot


def test_marked_up_pdf_on_a_page_rotated_90_degrees(tmp_path):
    c, pid = flow(tmp_path, scenario("10_rotated_other_scale"))
    try:
        data = listing(c, pid)
        door = door_item(data)
        r = c.get(f"/api/projects/{pid}/correction-list.pdf")
        doc = pymupdf.open(stream=r.content, filetype="pdf")
        assert doc[0].rotation == 90
        squares = [(p, a.rect) for p in doc for a in p.annots() if a.type[1] == "Polygon" and a.info["subject"] == str(door["n"])]
        assert squares
        page, rect = squares[0]
        assert page.mediabox.contains(rect) and _frame_hits(page, rect)
    finally:
        c.__exit__(None, None, None)


def test_accept_edit_drop_are_stored_counted_and_renumber(fresh):
    c, pid = fresh
    data = listing(c, pid)
    keys = [i["key"] for i in data["items"]]
    url = f"/api/projects/{pid}/correction-list/items/"
    assert c.put(url + keys[0], json={"action": "accept"}).status_code == 400             # a name is required
    assert c.put(url + "no-such-item", json={"action": "accept", "reviewer": "Rev"}).status_code == 404
    assert c.put(url + keys[0], json={"action": "dance", "reviewer": "Rev"}).status_code == 400
    assert c.put(url + keys[0], json={"action": "edit", "reviewer": "Rev", "wording": "  "}).status_code == 400
    c.put(url + keys[0], json={"action": "accept", "reviewer": "Rev"})
    c.put(url + keys[1], json={"action": "edit", "reviewer": "Rev", "wording": "Show the exit on sheet 1.  [Art. X]"})
    assert c.put(url + keys[2], json={"action": "drop", "reviewer": "Rev"}).status_code == 400   # dismissing needs a reason
    assert c.put(url + keys[2], json={"action": "drop", "reviewer": "Rev", "reason": "  "}).status_code == 400
    after = c.put(url + keys[2], json={"action": "drop", "reviewer": "Rev", "reason": "the sheet  shows it"}).json()
    assert after["items"][2]["review"]["reason"] == "the sheet shows it"
    b = after["edit_burden"]
    assert (b["accepted"], b["edited"], b["dropped"], b["edit_count"]) == (1, 1, 1, 2)
    assert b["unreviewed"] == len(keys) - 3
    assert after["items"][1]["wording"] == "Show the exit on sheet 1. [Art. X]"
    assert after["items"][2]["dropped"] and after["items"][2]["n"] is None
    assert [i["n"] for i in after["items"] if not i["dropped"]] == list(range(1, len(keys)))
    text = c.get(f"/api/projects/{pid}/correction-list?format=txt").text
    assert "Show the exit on sheet 1. [Art. X]" in text and data["items"][2]["wording"] not in text
    again = listing(c, pid)                                                                     # stored under the project
    assert again["edit_burden"]["edit_count"] == 2
    # the marked up PDF carries the edited wording and not the dropped item (a DXF plan is redrawn as vector pages)
    doc = pymupdf.open(stream=c.get(f"/api/projects/{pid}/correction-list.pdf").content, filetype="pdf")
    contents = [a.info["content"] for p in doc for a in p.annots()]
    assert any("Show the exit on sheet 1. [Art. X]" in x for x in contents)
    assert not any(data["items"][2]["wording"] in x for x in contents)
    c.put(url + keys[2], json={"action": "reset", "reviewer": "Rev"})
    assert listing(c, pid)["edit_burden"]["dropped"] == 0


def test_a_comment_is_assigned_resolved_and_opened_again_with_a_trail(fresh):
    c, pid = fresh
    first = listing(c, pid)["items"][0]
    assert first["severity"] in ("critical", "major", "minor", "info") and first["family"]
    url = f"/api/projects/{pid}/correction-list/follow-up/"
    key = first["key"]
    assert c.put(url + "no-such-item", json={"assignee": "Eng", "reviewer": "Rev"}).status_code == 404
    assert c.put(url + key, json={"reviewer": "Rev"}).status_code == 400
    assert c.put(url + key, json={"assignee": "Eng", "due": "next week", "reviewer": "Rev"}).status_code == 400
    after = c.put(url + key, json={"assignee": "Eng", "due": "2026-12-04", "reviewer": "Rev"}).json()
    assert after["items"][0]["followup"] == {**after["items"][0]["followup"], "assignee": "Eng", "due": "2026-12-04", "by": "Rev"}
    assert c.put(url + key, json={"resolved": True, "reviewer": "Rev"}).status_code == 400       # say what was checked
    done = c.put(url + key, json={"resolved": True, "note": "corrected on sheet 1", "reviewer": "Rev"}).json()
    resolved = done["items"][0]["followup"]["resolved"]
    assert resolved["by"] == "Rev" and resolved["note"] == "corrected on sheet 1" and resolved["stale"] is False
    again = c.put(url + key, json={"resolved": False, "reviewer": "Rev"}).json()["items"][0]["followup"]
    assert "resolved" not in again and again["assignee"] == "Eng"
    assert c.put(url + key, json={"assignee": "", "reviewer": "Rev"}).json()["items"][0]["followup"] is None
    trail = " | ".join(e["what"] for e in c.get(f"/api/projects/{pid}/audit").json())
    for said in ("assigned to Eng", "resolved", "opened again", "assignment removed"):
        assert said in trail


def test_the_building_use_and_location_are_kept_and_head_the_list(fresh):
    c, pid = fresh
    assert "Building use" not in c.get(f"/api/projects/{pid}/correction-list?format=html").text
    got = c.patch(f"/api/projects/{pid}", json={"occupancy": "  Residential,\n two storeys ", "location": "<Aachen>"}).json()
    assert got["occupancy"] == "Residential, two storeys" and got["location"] == "<Aachen>"
    page = c.get(f"/api/projects/{pid}/correction-list?format=html").text
    assert "Building use <b>Residential, two storeys</b>" in page and "&lt;Aachen&gt;" in page and "<Aachen>" not in page
    assert "Building use: Residential, two storeys    Location: <Aachen>" in c.get(
        f"/api/projects/{pid}/correction-list?format=txt").text
    made = c.post("/api/projects", json={"name": "n", "occupancy": "Office", "location": "x" * 500}).json()
    assert made["occupancy"] == "Office" and len(made["location"]) == 160 and made["base_pack"] is None


def test_a_deferred_clause_leaves_the_list_and_goes_on_the_cover(fresh):
    c, pid = fresh
    before = listing(c, pid)
    victim = door_item(before)
    url = f"/api/projects/{pid}/clause-states"
    assert c.put(url, json={"clause": "Art. 6.1", "state": "deferred"}).status_code == 400            # a name is required
    assert c.put(url, json={"clause": "Art. 6.1", "state": "approved", "reviewer": "R"}).status_code == 400
    assert c.put(url, json={"clause": "Art. 6.1", "state": "deferred", "reviewer": "R", "note": "door hardware"}).status_code == 200
    after = listing(c, pid)
    assert victim["key"] not in {i["key"] for i in after["items"]}
    assert [d["clause"] for d in after["deferred"]] == ["Art. 6.1"] and after["deferred"][0]["note"] == "door hardware"
    assert "DEFERRED SUBMITTALS" in c.get(f"/api/projects/{pid}/correction-list?format=txt").text
    assert "Deferred submittals" in c.get(f"/api/projects/{pid}/correction-list?format=html").text
    assert c.get(url).json()["Art. 6.1"]["state"] == "deferred"
    c.put(url, json={"clause": "Art. 6.1", "state": "reset", "reviewer": "R"})
    assert door_item(listing(c, pid))


def test_sign_off_needs_a_name_and_the_audit_trail_records_who_what_when(fresh):
    c, pid = fresh
    data = listing(c, pid)
    discipline = door_item(data)["discipline"]
    url = f"/api/projects/{pid}/signoffs"
    assert c.post(url, json={"discipline": discipline, "result": "Revision required"}).status_code == 400
    assert c.post(url, json={"reviewer": "R", "discipline": "astrology", "result": "Approved"}).status_code == 400
    assert c.post(url, json={"reviewer": "R", "discipline": discipline, "result": "Maybe"}).status_code == 400
    ok = c.post(url, json={"reviewer": "Ada Reviewer", "discipline": discipline, "result": "Revision required", "cycle": 1, "note": "ok"})
    assert ok.status_code == 201
    c.post(url, json={"reviewer": "Bob Reviewer", "discipline": discipline, "result": "Approved with comments", "cycle": 1})
    signed = listing(c, pid)["disciplines"][discipline]["signed"]
    assert signed["reviewer"] == "Bob Reviewer"                                    # the latest per cycle and discipline counts
    assert len(c.get(url).json()) == 2                                             # both are kept
    c.put(f"/api/projects/{pid}/clause-states", json={"clause": "Art. 6.1", "state": "not_applicable", "reviewer": "Ada Reviewer"})
    trail = c.get(f"/api/projects/{pid}/audit").json()
    assert [e["who"] for e in trail if e["what"].startswith("signed off")] == ["Ada Reviewer", "Bob Reviewer"]
    assert all(e["at"] and e["who"] and e["what"] for e in trail)
    assert any("Art. 6.1 set to not_applicable" in e["what"] for e in trail)
    assert any(e["what"].startswith("rule for clause") for e in trail)                # the earlier rule approvals are in it too
    assert c.get("/api/projects/nonexistent1/audit").status_code == 404


def test_reviewer_states_and_the_browser_route(narrow_door):
    c, pid = narrow_door
    states = c.get("/api/reviewer-states").json()
    assert set(states["statuses"].values()) == {"Approved", "Approved with comments", "Information requested", "Revision required",
                                                "Not applicable", "Deferred submittal"}
    assert "Rejected" in states["signoff_results"] and "architectural" in states["disciplines"]
    index = c.get("/")
    assert index.status_code == 200 and "/static/app.js" in index.text
    js = c.get("/static/app.js").text
    assert "correctionsTab" in js and "#/p/${pid}/corrections" in js and "correction-list.pdf" in js
    assert "—" not in js and "–" not in js
    assert c.get("/static/app.css").status_code == 200
