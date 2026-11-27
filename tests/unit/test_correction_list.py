"""The correction list from findings: grouping, wording, states, edits, renderers and the marked up PDF. No model, no server."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pymupdf
import pytest

from reviewpulse.report import correction_list as cl

SHEETS = [{"id": "A-101", "page": 1, "width": 420.0, "height": 297.0, "scale_method": "printed scale", "discipline": "architectural"}]
CLAUSES = [
    {"id": "R311.6", "text": "The minimum width of hallways shall not be less than 36 inches. [CRC R311.6]", "scope": "Means of egress"},
    {"id": "R303.1", "text": "Habitable rooms shall have an aggregate glazing area of not less than 8 percent of the floor area. [CRC R303.1]",
     "scope": "Light and ventilation"},
    {"id": "R314.3", "text": "Smoke alarms shall be installed in each sleeping room. [CRC R314.3]", "scope": "Means of egress"},
]
DOC = {"name": "checklist.pdf", "clauses": CLAUSES}


def finding(rule, clause, verdict, message, sheet="A-101", box=None, **extra):
    detected, required = extra.pop("detected", None), extra.pop("required", None)
    ev = {"sheet": sheet, "title": rule, "finding_id": f"{rule}:{verdict}", **extra}
    if box:
        x0, y0, x1, y1 = box
        ev["polygons"] = [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]]
    return {"rule_id": rule, "verdict": verdict, "severity": "major", "subject_ids": ["h1"], "message": message,
            "detected": detected, "required": required, "tier": "T1",
            "evidence": ev, "source": {"doc": "checklist.pdf", "clause": clause}}


def sample(**kw):
    findings = [
        finding("I-R311.6", "R311.6", "FAIL", "I-R311.6: Hall 1: width is 0.80 m (>= 0.91 m required).", box=(300, 200, 340, 230),
                detected="0.80 m", required=">= 0.91 m"),
        finding("I-R303.1", "R303.1", "NOT_EVALUATED", "I-R303.1: not decided, missing window_area.", box=None,
                unsettled=[{"entity": "r1", "fact": "glazing_area", "explain": "r1.glazing_area: no producer could answer",
                            "question": "What is the glazing_area of r1 in m2? Answer with a source and your name to settle it."}]),
        finding("I-R314.3", "R314.3", "WARNING", "I-R314.3: not found. Check whether this requirement applies.", advisory=True),
        finding("I-OK", "R999", "PASS", "I-OK: satisfied."),
    ]
    return cl.build({"name": "p", "plan": "plan.pdf"}, findings, DOC, {}, SHEETS, **kw)


def test_items_are_numbered_grouped_and_ordered():
    data = sample()
    assert [i["n"] for i in data["items"]] == [1, 2, 3]
    assert {i["clause"] for i in data["items"]} == {"R311.6", "R303.1", "R314.3"}
    assert data["approved_count"] == 1                      # the pass is counted, never listed
    groups = cl.grouped(data)
    assert [g[0] for g in groups] == sorted([g[0] for g in groups], key=lambda d: ["architectural", "structural", "mechanical", "plumbing", "electrical", "fire_life_safety", "energy", "accessibility", "planning", "general"].index(d))
    chapters = [(i["discipline"], i["chapter_label"]) for i in data["items"]]
    assert ("fire_life_safety", "Means of egress") in chapters                      # the document's own heading is the chapter


def test_the_requirement_is_quoted_with_its_own_citation_never_paraphrased():
    item = next(i for i in sample()["items"] if i["clause"] == "R311.6")
    assert item["citation"] == "[CRC R311.6]"
    assert item["quote"] == "The minimum width of hallways shall not be less than 36 inches."
    assert f'"{item["quote"]}" [CRC R311.6]' in item["wording"]
    assert item["status"] == "revision_required" and item["status_label"] == "Revision required"


def test_the_citation_falls_back_to_the_clause_number():
    assert cl.citation_of("Art. 6.1", "Every door has a clear width of at least 0.80 m.") == "[Art. 6.1]"
    assert cl.citation_of("x", "see [CBC 1010.1.1] and [CRC R311.6]") == "[CRC R311.6]"


def test_an_undecided_item_carries_one_question_and_is_never_approved():
    data = sample()
    undecided = {i["clause"]: i for i in data["items"] if i["status"] == "information_requested"}
    assert set(undecided) == {"R303.1", "R314.3"}
    assert undecided["R303.1"]["question"].startswith("What is the glazing_area of r1")           # the ledger's own follow up
    assert undecided["R314.3"]["question"].startswith("Does this requirement apply")
    assert "To settle it:" in undecided["R303.1"]["wording"]
    assert data["overall"]["result"] == "Revision required"


def test_where_on_the_sheet_and_the_facts_with_their_source():
    item = next(i for i in sample()["items"] if i["clause"] == "R311.6")
    loc = item["locations"][0]
    assert loc["sheet"] == "A-101" and loc["page"] == 2 and loc["bbox"] == [300.0, 200.0, 340.0, 230.0]
    assert "upper right of the sheet" in loc["where"]
    fact = item["facts"][0]
    assert "measured on sheet A-101" in fact["source"] and "printed scale" in fact["source"]


def test_an_item_with_no_place_says_so_instead_of_inventing_one():
    item = next(i for i in sample()["items"] if i["clause"] == "R303.1")
    assert item["locations"][0]["bbox"] is None
    assert "No sheet shows this" not in item["wording"] or item["locations"]        # located on a sheet, though not at a spot


def test_a_deferred_clause_is_neither_a_correction_nor_a_failure():
    data = sample(states={"R311.6": {"state": "deferred", "by": "A. Reviewer", "at": "t", "note": "trusses"}})
    assert "R311.6" not in {i["clause"] for i in data["items"]}
    assert [d["clause"] for d in data["deferred"]] == ["R311.6"]
    assert data["deferred"][0]["by"] == "A. Reviewer"
    assert "DEFERRED SUBMITTALS" in cl.render_text(data)
    assert data["overall"]["result"] == "Revision required"          # the other items still count


def test_only_deferred_leaves_approved_with_comments():
    findings = [finding("I-R311.6", "R311.6", "FAIL", "I-R311.6: Hall 1: bad.", detected="1", required=">= 2")]
    data = cl.build({"name": "p"}, findings, DOC, {}, SHEETS, states={"R311.6": {"state": "deferred", "by": "x", "at": "t"}})
    assert data["items"] == [] and data["overall"]["result"] == "Approved with comments"


def test_edits_are_applied_and_counted_and_numbers_close_up():
    data = sample(edits={"R311.6": {"action": "edit", "wording": "Widen the hall  to 36 in. [CRC R311.6]", "by": "r", "at": "t"},
                         "R303.1": {"action": "drop", "by": "r", "at": "t"},
                         "R314.3": {"action": "accept", "by": "r", "at": "t"}})
    by = {i["clause"]: i for i in data["items"]}
    assert by["R311.6"]["wording"] == "Widen the hall to 36 in. [CRC R311.6]"
    assert by["R303.1"]["dropped"] and by["R303.1"]["n"] is None
    assert [i["n"] for i in cl.included(data)] == [1, 2]
    b = data["edit_burden"]
    assert (b["items"], b["accepted"], b["edited"], b["dropped"], b["unreviewed"], b["edit_count"]) == (3, 1, 1, 1, 0, 2)
    assert 0 < b["mean_text_change"] < 1
    assert "Widen the hall" in cl.render_text(data) and "glazing" not in cl.render_text(data)


def test_dismissed_findings_do_not_become_items():
    f = finding("I-R311.6", "R311.6", "FAIL", "I-R311.6: Hall: bad.")
    f["evidence"]["dismissed"] = "not a hall"
    data = cl.build({"name": "p"}, [f], DOC, {}, SHEETS)
    assert data["items"] == [] and data["dismissed"][0]["reasons"] == ["not a hall"]


def test_two_rules_for_one_clause_make_one_item():
    a = finding("I-R311.6", "R311.6", "FAIL", "I-R311.6: Hall 1: bad.", detected="0.8 m", required=">= 0.91 m")
    b = finding("C-D1", "R311.6", "FAIL", "Hall width: Hall 1: bad.", detected="0.8 m", required=">= 0.91 m")
    data = cl.build({"name": "p"}, [a, b], DOC, {}, SHEETS)
    assert len(data["items"]) == 1


def test_sign_off_per_discipline_and_cycle():
    data = sample(signoffs=[{"reviewer": "A", "cycle": 1, "discipline": "architectural", "result": "Revision required", "at": "t"},
                            {"reviewer": "B", "cycle": 2, "discipline": "fire_life_safety", "result": "Approved", "at": "t"}], cycle=1)
    assert data["disciplines"]["architectural"]["signed"]["reviewer"] == "A"
    assert data["disciplines"]["fire_life_safety"]["signed"] is None          # that sign off was for another cycle
    assert data["overall"]["signed"] is None and data["overall"]["unsigned_disciplines"]
    full = sample(signoffs=[{"reviewer": "A", "cycle": 1, "discipline": d, "result": "Approved", "at": "t"} for d in
                            ("architectural", "fire_life_safety", "general")], cycle=1)
    assert full["overall"]["signed"] == "Approved" and full["disciplines"]["architectural"]["differs"]


def test_text_html_and_json_agree_and_use_no_dashes():
    data = sample()
    text, page, js = cl.render_text(data), cl.render_html(data), cl.to_json(data)
    for item in data["items"]:
        assert item["wording"] in text
        assert item["wording"].split(" [")[0][:40] in page.replace("&quot;", '"')
    assert json.loads(js)["items"][0]["n"] == 1
    for out in (text, page, js):
        assert "—" not in out and "–" not in out


# ---- the marked up PDF ----------------------------------------------------------------------------------------------------

def _pdf(tmp_path, pages=2, rotate=0):
    path = tmp_path / "plan.pdf"
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=1190, height=842)
        page.draw_rect(pymupdf.Rect(100, 100, 1090, 742))
        if rotate:
            page.set_rotation(rotate)
    doc.save(path)
    return path


def _models(path):
    return [SimpleNamespace(sheet=SimpleNamespace(id="A-101", page=1, source_file=str(path), width=420.0, height=297.0))]


def test_markup_pdf_keeps_the_submission_and_adds_titled_annotations(tmp_path):
    src = _pdf(tmp_path)
    out = tmp_path / "markup.pdf"
    stats = cl.write_markup_pdf(sample(), _models(src), out, src)
    assert stats["items"] == 3 and stats["fallback"] >= 1                   # two items have no spot: page level notes
    doc = pymupdf.open(out)
    assert len(doc) == 2                                                    # a copy of the submitted pages, none added
    annots = [(p.number, a.type[1], a.info["subject"], a.info["content"], a.rect) for p in doc for a in p.annots() if a.info["subject"]]
    assert {sub for _, _, sub, _, _ in annots} == {"1", "2", "3"}            # the item number is the Subject
    assert {k for _, k, *_ in annots} >= {"Polygon", "FreeText", "Text"}     # standard types, written by the connectors package
    page_no, _, _, content, rect = next(a for a in annots if a[1] == "Polygon")
    assert "[CRC R311.6]" in content
    assert page_no == 1                                                     # on the sheet that holds the evidence
    # the cloud sits where the sheet coordinates say: x 300..340 mm of 420, y 200..230 mm of 297 (up)
    mm = 25.4 / 72
    assert rect.x0 == pytest.approx(300 / mm - 4, abs=4) and rect.y1 == pytest.approx(842 - 200 / mm + 4, abs=4)
    orig = pymupdf.open(src)
    assert [p.read_contents() for p in orig] == [p.read_contents() for p in doc]      # the drawing itself is untouched


def test_markup_pdf_on_a_rotated_page_stays_on_the_page(tmp_path):
    src = _pdf(tmp_path, rotate=90)
    out = tmp_path / "rot.pdf"
    sheets = [{**SHEETS[0], "width": 297.0, "height": 420.0}]            # the sheet is read as it is seen: portrait
    f = finding("I-R311.6", "R311.6", "FAIL", "I-R311.6: Hall 1: bad.", box=(200, 300, 240, 330), detected="1", required=">= 2")
    data = cl.build({"name": "p"}, [f], DOC, {}, sheets)
    cl.write_markup_pdf(data, _models(src), out, src)
    doc = pymupdf.open(out)
    assert doc[1].rotation == 90
    rects = [a.rect for a in doc[1].annots()]
    assert rects
    # the box lands on the drawn frame (the rectangle drawn from 100,100 to 1090,742 in unrotated points), not outside the page
    assert all(doc[1].mediabox.contains(r) for r in rects)


def test_every_export_format_is_written_and_reads_back(tmp_path):
    from reviewpulse.connectors import filedrop
    from reviewpulse.connectors.bcf import import_bcf

    src = _pdf(tmp_path)
    data = sample()
    for fmt in ("pdf", "bcf", "json", "csv"):
        path = cl.export(data, fmt, tmp_path / "x", _models(src), src)
        assert path.exists() and path.stat().st_size > 0
    back = filedrop.read_json(tmp_path / "x" / "correction_list.comments.json")
    assert [c.number for c in back] == [1, 2, 3] and back[0].citation == "CRC R311.6"
    assert "[CRC R311.6]" not in back[0].text and back[0].located and back[0].page == 2
    assert [c.number for c in filedrop.read_csv(tmp_path / "x" / "correction_list.csv")] == [1, 2, 3]
    assert len(import_bcf(tmp_path / "x" / "correction_list.bcf")) == 3
    with pytest.raises(ValueError):
        cl.export(data, "docx", tmp_path / "x")


def test_markup_pdf_with_no_items_is_still_a_copy(tmp_path):
    src = _pdf(tmp_path, pages=1)
    empty = cl.build({"name": "p"}, [], DOC, {}, SHEETS)
    out = tmp_path / "e.pdf"
    stats = cl.write_markup_pdf(empty, [], out, src)
    assert stats["annotations"] == 0 and len(pymupdf.open(out)) == 1


def test_a_reviewers_reading_replaces_the_tools_and_says_what_it_replaced():
    before = sample()
    failing = next(i for i in before["items"] if i["status"] == "revision_required")
    state = {failing["clause"]: {"state": "shown", "by": "A. Reviewer", "at": "t", "note": "sheet detail 4"}}
    after = sample(states=state)
    assert failing["clause"] not in [i["clause"] for i in after["items"]]
    [record] = after["shown"]
    assert record["overrode"] == "Revision required" and record["by"] == "A. Reviewer"
