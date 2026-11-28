"""Connectors (M26). Vendor connectors are contract tested from documentation with recorded fixtures: NOT tested live.

No test opens a network connection: the real transport is replaced by one that fails the test if it is used.
"""

from __future__ import annotations

import json
import urllib.request
import zipfile
from pathlib import Path

import pymupdf
import pytest

from reviewpulse.connectors import __main__ as cli
from reviewpulse.connectors import bcf, filedrop, pdf_io
from reviewpulse.connectors.accela import AccelaClient
from reviewpulse.connectors.bluebeam import BluebeamClient
from reviewpulse.connectors.model import (
    SCHEMA_VERSION,
    Reply,
    ReviewComment,
    StatusEntry,
    dump,
    from_findings,
    json_schema,
    load,
)
from reviewpulse.connectors.opengov import OpenGovClient
from reviewpulse.connectors.transport import (
    ConnectorError,
    FixtureTransport,
    PostedLedger,
    RecordingTransport,
    Request,
    Response,
    redact,
    send_with_retry,
)

XSD = Path(__file__).resolve().parents[1] / "fixtures" / "bcf21"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    for name in ("ACCELA_ACCESS_TOKEN", "ACCELA_APP_ID", "BLUEBEAM_ACCESS_TOKEN", "OPENGOV_ACCESS_TOKEN"):
        monkeypatch.delenv(name, raising=False)


FINDINGS = [
    {"rule_id": "hall_width", "verdict": "FAIL", "severity": "major", "subject_ids": ["door_3"],
     "message": "Hallway width is 30 in (36 in required).", "detected": "30 in", "required": ">= 36 in",
     "source": {"doc": "CRC 2019", "clause": "R311.6"},
     "evidence": {"finding_id": "f-hall", "sheet": "A101", "polygons": [[[100.0, 100.0], [180.0, 100.0], [180.0, 120.0]]],
                  "quote": "Hallway 30 in wide", "discipline": "Building"}},
    {"rule_id": "ceiling", "verdict": "NOT_EVALUATED", "severity": "major", "subject_ids": [],
     "message": "Ceiling height not decided, missing room height.", "source": {"clause": "R305.1"},
     "evidence": {"missing": ["room height"], "page": 2, "bbox_pt": [50, 60, 120, 90]}},
    {"rule_id": "ok", "verdict": "PASS", "severity": "major", "message": "fine", "evidence": {}},
    {"rule_id": "gone", "verdict": "FAIL", "severity": "minor", "message": "dismissed one", "evidence": {"dismissed": "not applicable here"}},
]
SHEETS = {"A101": {"page": 0, "height_pt": 595.0}}


def base_pdf(path: Path, pages: int = 2, rotation: int = 0) -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        p = doc.new_page(width=842, height=595)
        p.insert_text((100, 110), f"Hallway 30 in wide, page {i + 1}")
        if rotation:
            p.set_rotation(rotation)
    doc.save(str(path))
    return path


# ---- model ----------------------------------------------------------------------------------------------------------


def test_adapter_maps_findings_to_comments():
    cs = from_findings(FINDINGS, sheets=SHEETS, cycle=2, author="Khaoula")
    assert [c.number for c in cs] == [1, 2, 3]                                   # PASS left out
    hall = next(c for c in cs if c.id == "f-hall")
    assert hall.state == "open" and hall.page == 1 and hall.located
    assert hall.citation == "R311.6" and hall.citation_doc == "CRC 2019" and hall.discipline == "Building"
    assert hall.evidence_quote == "Hallway 30 in wide" and hall.cycle == 2 and hall.author == "Khaoula"
    # sheet mm to PDF points: x / (25.4/72), y flipped against the page height
    assert hall.bbox == pytest.approx([283.46, 595 - 120 / (25.4 / 72), 510.24, 595 - 100 / (25.4 / 72)], abs=0.01)
    ceiling = next(c for c in cs if c.citation == "R305.1")
    assert ceiling.state == "information_requested" and ceiling.page == 2 and ceiling.bbox == [50, 60, 120, 90]
    assert ceiling.source_facts["missing"] == ["room height"]
    assert next(c for c in cs if c.text == "dismissed one").state == "dismissed"
    assert len(from_findings(FINDINGS, sheets=SHEETS, include_pass=True)) == 4


def test_ids_are_stable_and_schema_validates():
    a = from_findings(FINDINGS, sheets=SHEETS)
    b = from_findings(list(reversed(FINDINGS)), sheets=SHEETS)
    assert sorted(c.id for c in a) == sorted(c.id for c in b)
    schema = json_schema()
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    props = schema["$defs"]["ReviewComment"]["properties"]
    for name in ("id", "discipline", "citation", "text", "sheet", "page", "bbox", "state", "evidence_quote", "source_facts",
                 "cycle", "author", "status_history"):
        assert name in props
    assert load(json.loads(json.dumps(dump(a)))) == a
    with pytest.raises(ValueError):
        load({"schema_version": "other", "comments": []})


# ---- PDF annotations ------------------------------------------------------------------------------------------------


def test_pdf_roundtrip_keeps_the_correction_list(tmp_path):
    cs = from_findings(FINDINGS, sheets=SHEETS, author="Khaoula")
    h = _hall(cs)
    h.status_history = [StatusEntry(state="addressed", by="Architect", at="2026-11-02T10:00:00Z", note="Widened to 36 in")]
    h.replies = [Reply(author="Plan checker", at="2026-11-03T09:00:00Z", text="Thanks (see sheet A102)")]
    src = base_pdf(tmp_path / "plan.pdf")
    out = tmp_path / "marked.pdf"
    res = pdf_io.write_annotations(src, out, cs)
    assert res.written == 3 and not res.skipped and not res.warnings
    assert pymupdf.open(str(src)).load_page(0).first_annot is None                # the source is untouched
    back = pdf_io.read_annotations(out)
    assert not back.warnings and len(back.comments) == 3
    by_id = {c.id: c for c in back.comments}
    hall = by_id["f-hall"]
    assert hall.text == "Hallway width is 30 in (36 in required)." and hall.citation == "R311.6"
    assert hall.evidence_quote == "Hallway 30 in wide" and hall.discipline == "Building" and hall.number == h.number
    assert hall.state == "addressed" and hall.status_history[-1].note == "Widened to 36 in"
    assert hall.status_history[-1].by == "Architect" and hall.status_history[-1].at.startswith("2026-11-02T10:00:00")
    assert hall.replies[0].text == "Thanks (see sheet A102)" and hall.replies[0].author == "Plan checker"
    assert hall.author == "Khaoula" and hall.page == 1 and hall.color == "#d91a1a"
    assert hall.source_facts["cloud"] is True and hall.source_facts["annotation_type"] == "Polygon"
    for want in h.bbox:                                                       # the box survives within the border width
        assert any(abs(want - got) < 2.0 for got in hall.bbox)
    un = next(c for c in back.comments if c.citation == "R305.1")
    assert un.page == 2 and un.state == "information_requested"
    assert un.status_history[-1].state == "information_requested"


def test_pdf_standard_structures_are_present(tmp_path):
    cs = from_findings(FINDINGS[:1], sheets=SHEETS)
    cs[0].state = "verified"
    assert cs[0].id == "f-hall"
    out = tmp_path / "m.pdf"
    pdf_io.write_annotations(base_pdf(tmp_path / "p.pdf"), out, cs)
    doc = pymupdf.open(str(out))
    kinds = {a.type[1]: a for a in doc[0].annots()}
    assert {"Polygon", "FreeText", "Text"} <= set(kinds)
    cloud = kinds["Polygon"]
    assert doc.xref_get_key(cloud.xref, "BE")[1].replace(" ", "") == "<</S/C/I2>>"
    assert cloud.info["subject"] == str(cs[0].number) and cloud.info["title"] == "ReviewPulse"
    callout = kinds["FreeText"]
    assert doc.xref_get_key(callout.xref, "IT")[1] == "/FreeTextCallout"
    assert len(doc.xref_get_key(callout.xref, "CL")[1].strip("[]").split()) == 4
    reply = next(a for a in doc[0].annots() if doc.xref_get_key(a.xref, "StateModel")[0] != "null")
    assert doc.xref_get_key(reply.xref, "StateModel")[1] == "Review" and doc.xref_get_key(reply.xref, "State")[1] == "Accepted"
    assert doc.xref_get_key(reply.xref, "IRT")[1] == f"{cloud.xref} 0 R"


def test_unlocated_comment_and_bad_page_are_kept(tmp_path):
    c = ReviewComment(id="x1", number=1, text="Show the smoke alarm note", citation="R314", located=False, page=9)
    out = tmp_path / "u.pdf"
    res = pdf_io.write_annotations(base_pdf(tmp_path / "p.pdf"), out, [c])
    assert res.written == 1 and res.unlocated == 1
    back = pdf_io.read_annotations(out).comments[0]
    assert back.id == "x1" and not back.located and back.page is None and back.bbox is None


def test_write_refuses_encrypted_pdf(tmp_path):
    src = base_pdf(tmp_path / "p.pdf")
    enc = tmp_path / "enc.pdf"
    pymupdf.open(str(src)).save(str(enc), encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    with pytest.raises(ValueError, match="password"):
        pdf_io.write_annotations(enc, tmp_path / "o.pdf", [ReviewComment(id="a", text="t")])
    with pytest.raises(ValueError, match="password"):
        pdf_io.read_annotations(enc)


def _foreign_pdf(path: Path) -> Path:
    """A PDF annotated the way other tools do it: no ReviewPulse keys, Bluebeam status replies, odd annotation types."""
    doc = pymupdf.open()
    doc.new_page(width=612, height=792)
    doc.new_page(width=612, height=792)
    p1, p2 = doc[0], doc[1]
    p1.insert_text((72, 100), "Provide 7 ft ceiling height in habitable rooms")
    p2.set_rotation(90)
    # a cloud drawn as a polygon with the cloud border effect, subject and author the way Revu writes them
    cloud = p1.add_polygon_annot([(70, 85), (400, 85), (400, 110), (300, 130), (70, 110)])
    cloud.set_info(content="Show ceiling height [CRC R305.1]", title="J. Reviewer", subject="Cloud+",
                   creationDate="D:20261101090000-05'00'", modDate="D:20261101091500-05'00'")
    cloud.set_colors(stroke=(1, 0, 0))
    cloud.update()
    doc.xref_set_key(cloud.xref, "BE", "<</S/C/I 2>>")
    # the applicant's reply, then two status changes (Bluebeam: reply annotations with StateModel Review)
    reply = p1.add_text_annot((70, 85), "Added to sheet A-201")
    reply.set_info(content="Added to sheet A-201", title="A. Architect", creationDate="D:20261105100000-05'00'")
    reply.update()
    doc.xref_set_key(reply.xref, "IRT", f"{cloud.xref} 0 R")
    doc.xref_set_key(reply.xref, "RT", "/R")
    for who, state, day in (("A. Architect", "Completed", "06"), ("J. Reviewer", "Accepted", "09")):
        st = p1.add_text_annot((70, 85), "")
        st.set_info(title=who, creationDate=f"D:202611{day}120000-05'00'")
        st.update()
        doc.xref_set_key(st.xref, "IRT", f"{cloud.xref} 0 R")
        doc.xref_set_key(st.xref, "StateModel", "(Review)")
        doc.xref_set_key(st.xref, "State", f"({state})")
    hl = p1.add_highlight_annot(p1.search_for("ceiling height")[0])
    hl.set_info(content="", title="J. Reviewer", subject="Highlight")
    hl.update()
    p1.add_ink_annot([[(100, 300), (150, 340), (200, 300)]]).update()
    p1.add_line_annot((100, 400), (300, 450)).update()
    stamp = p1.add_stamp_annot(pymupdf.Rect(300, 300, 400, 340), stamp=0)
    stamp.update()
    p1.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(10, 10, 50, 20), "uri": "https://example.com"})
    note2 = p2.add_text_annot((100, 100), "Rotated page note")
    note2.set_info(title="Fire reviewer", subject="7")
    note2.update()
    # broken structure: a reply to a missing object, and two annotations that reply to each other
    lost = p2.add_text_annot((200, 200), "orphan reply")
    lost.update()
    doc.xref_set_key(lost.xref, "IRT", "99999 0 R")
    a = p2.add_text_annot((300, 300), "loop a")
    b = p2.add_text_annot((320, 300), "loop b")
    a.update()
    b.update()
    doc.xref_set_key(a.xref, "IRT", f"{b.xref} 0 R")
    doc.xref_set_key(b.xref, "IRT", f"{a.xref} 0 R")
    doc.save(str(path))
    return path


def test_reads_markups_made_by_other_tools(tmp_path):
    res = pdf_io.read_annotations(_foreign_pdf(tmp_path / "revu.pdf"), cycle=1)
    by_text = {c.text: c for c in res.comments}
    cloud = by_text["Show ceiling height [CRC R305.1]"]
    assert cloud.author == "J. Reviewer" and cloud.subject == "Cloud+" and cloud.page == 1
    assert cloud.created.startswith("2026-11-01T09:00:00-05:00") and cloud.modified.startswith("2026-11-01T09:15:00")
    assert cloud.color == "#ff0000" and cloud.source_facts["cloud"] is True and cloud.source_facts["vertices"] == 5
    assert cloud.state == "verified"                                   # latest status was Accepted
    assert [h.state for h in cloud.status_history] == ["addressed", "verified"]
    assert [h.by for h in cloud.status_history] == ["A. Architect", "J. Reviewer"]
    assert cloud.replies and cloud.replies[0].text == "Added to sheet A-201"
    hl = next(c for c in res.comments if c.source_facts.get("annotation_type") == "Highlight")
    assert "ceiling height" in hl.evidence_quote
    kinds = {c.source_facts.get("annotation_type") for c in res.comments}
    assert {"Ink", "Line", "Stamp", "Polygon", "Highlight", "Text"} <= kinds
    assert "Link" not in kinds
    rot = by_text["Rotated page note"]
    assert rot.page == 2 and rot.number == 7 and rot.author == "Fire reviewer"
    assert any("unreadable" in w for w in res.warnings)               # the missing IRT target was reported, not fatal
    assert "loop a" in by_text and "loop b" in by_text                # a reply loop does not hang or lose markups


def test_read_survives_a_pdf_with_no_annotations(tmp_path):
    res = pdf_io.read_annotations(base_pdf(tmp_path / "plain.pdf"))
    assert res.comments == [] and res.annotations_seen == 0


def test_our_cycle_two_reads_cycle_one_markups_as_back_check_input(tmp_path):
    first = from_findings(FINDINGS[:2], sheets=SHEETS, cycle=1)
    pdf_io.write_annotations(base_pdf(tmp_path / "p.pdf"), tmp_path / "c1.pdf", first)
    prior = pdf_io.read_annotations(tmp_path / "c1.pdf", cycle=1).comments
    assert {c.id for c in prior} == {c.id for c in first}
    assert all(c.cycle == 1 for c in prior)


# ---- BCF ------------------------------------------------------------------------------------------------------------


def _hall(cs):
    return next(c for c in cs if c.id == "f-hall")


def _comments_for_bcf():
    cs = from_findings(FINDINGS, sheets=SHEETS, author="Khaoula")
    hall = _hall(cs)
    hall.status_history = [StatusEntry(state="addressed", by="Architect", at="2026-11-02T10:00:00Z", note="Widened")]
    hall.replies = [Reply(author="Checker", at="2026-11-03T09:00:00Z", text="Please also update A102")]
    return cs


def test_bcf_export_is_valid_bcf_2_1(tmp_path):
    cs = _comments_for_bcf()
    out = bcf.export_bcf(cs, tmp_path / "x.bcf", project_name="Demo", pdf_name="plan.pdf", snapshots={cs[0].id: b"\x89PNG..."})
    names = zipfile.ZipFile(out).namelist()
    assert {"bcf.version", "project.bcfp", "extensions.xsd"} <= set(names)
    assert sum(n.endswith("markup.bcf") for n in names) == len(cs)
    assert sum(n.endswith("viewpoint.bcfv") for n in names) == len(cs)
    assert sum(n.endswith("snapshot.png") for n in names) == 1
    problems = bcf.validate_bcf(out, XSD)
    assert problems == [], problems


def test_bcf_roundtrip(tmp_path):
    cs = _comments_for_bcf()
    out = bcf.export_bcf(cs, tmp_path / "x.bcf", pdf_name="plan.pdf")
    back = {c.id: c for c in bcf.import_bcf(out)}
    assert set(back) == {c.id for c in cs}
    for c in cs:
        b = back[c.id]
        assert (b.text, b.state, b.page, b.bbox, b.citation, b.discipline, b.number, b.severity) == (
            c.text, c.state, c.page, c.bbox, c.citation, c.discipline, c.number, c.severity)
        assert b.evidence_quote == c.evidence_quote and b.cycle == c.cycle and b.origin == "bcf"
    hall = back["f-hall"]
    assert hall.status_history[0].state == "addressed" and hall.status_history[0].note == "Widened"
    assert hall.replies[0].text == "Please also update A102" and hall.replies[0].author == "Checker"


def test_bcf_viewpoint_is_a_page_reference_not_a_camera(tmp_path):
    out = bcf.export_bcf([_hall(_comments_for_bcf())], tmp_path / "x.bcf", pdf_name="plan.pdf")
    z = zipfile.ZipFile(out)
    vp = next(n for n in z.namelist() if n.endswith(".bcfv"))
    text = z.read(vp).decode()
    assert "Camera" not in text and "Components" not in text
    ref = json.loads(z.read(next(n for n in z.namelist() if n.endswith("page_reference.json"))))
    assert ref["page"] == 1 and len(ref["bbox_pt"]) == 4 and "PDF points" in ref["coordinates"]
    assert bcf.SNIPPET_TYPE in z.read(next(n for n in z.namelist() if n.endswith("markup.bcf"))).decode()


def test_bcf_import_from_another_tool(tmp_path):
    markup = """<?xml version="1.0" encoding="UTF-8"?>
<Markup><Topic Guid="3f2504e0-4f89-41d3-9a0c-0305e82c3301" TopicType="Clash" TopicStatus="Closed">
<Title>Duct hits beam</Title><Priority>High</Priority><Labels>MEP</Labels>
<CreationDate>2026-10-01T08:00:00Z</CreationDate><CreationAuthor>eng@example.com</CreationAuthor><Description>Move duct</Description>
</Topic><Comment Guid="3f2504e0-4f89-41d3-9a0c-0305e82c3302"><Date>2026-10-01T08:00:00Z</Date><Author>eng@example.com</Author>
<Comment>Duct clashes with beam B12</Comment></Comment>
<Comment Guid="3f2504e0-4f89-41d3-9a0c-0305e82c3303"><Date>2026-10-02T08:00:00Z</Date><Author>arch@example.com</Author>
<Comment>Rerouted</Comment></Comment></Markup>"""
    p = tmp_path / "other.bcfzip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("3f2504e0-4f89-41d3-9a0c-0305e82c3301/markup.bcf", markup)
        z.writestr("bcf.version", '<Version VersionId="2.0"/>')
    (c,) = bcf.import_bcf(p)
    assert c.text == "Duct clashes with beam B12" and c.state == "verified" and c.severity == "major"
    assert c.replies[0].text == "Rerouted" and c.discipline == "" and not c.located and c.author == "eng@example.com"


# ---- transport ------------------------------------------------------------------------------------------------------


def test_retry_backoff_and_give_up():
    sleeps = []
    t = FixtureTransport([("POST", "x", [Response(503), Response(429, headers={"Retry-After": "3"}), Response(200, b"{}")])])
    r = send_with_retry(t, Request("POST", "https://x/a"), sleep=sleeps.append, backoff=0.5)
    assert r.status == 200 and sleeps == [0.5, 3.0]
    t2 = FixtureTransport([("GET", "x", Response(500)), ("GET", "y", Response(503))])
    assert send_with_retry(t2, Request("GET", "https://y"), retries=2, sleep=lambda s: None).status == 503
    assert len(t2.sent) == 3
    with pytest.raises(ConnectorError):
        send_with_retry(FixtureTransport([]), Request("GET", "https://nowhere"), retries=1, sleep=lambda s: None)


def test_redaction_masks_secrets():
    req = Request("POST", "https://x", {"Authorization": "Bearer SECRET", "x-accela-appsecret": "S2", "Accept": "a"},
                  form={"client_secret": "S3", "refresh_token": "S4", "grant_type": "refresh_token"},
                  multipart={"f": ("a.pdf", b"%PDF", "application/pdf")})
    text = json.dumps(redact(req))
    for s in ("SECRET", "S2", "S3", "S4", "%PDF"):
        assert s not in text
    assert "refresh_token" in text and "a.pdf" in text


# ---- Accela ---------------------------------------------------------------------------------------------------------


def _cs():
    return from_findings(FINDINGS, sheets=SHEETS)


def test_accela_comment_contract():
    t = FixtureTransport([("POST", r"/v4/documentReview/documents/154694/comments$",
                           lambda r: Response(200, json.dumps({"result": {"id": 14483}, "status": 200}).encode()))])
    ledger = PostedLedger()
    cli_ = AccelaClient(transport=t, dry_run=False, access_token="TOKEN123", app_id="APP9", agency="BPTDEV", environment="TEST",
                        ledger=ledger, status_map={"open": "Open"}, send_discipline=True)
    res = cli_.post_comments("154694", _cs())
    assert [r.outcome for r in res] == ["posted"] * 3 and res[0].remote_id == 14483
    req = t.raw[0]
    assert req.url == "https://apis.accela.com/v4/documentReview/documents/154694/comments"
    assert req.headers["Authorization"] == "TOKEN123" and "Bearer" not in req.headers["Authorization"]
    assert req.headers["x-accela-appid"] == "APP9" and req.headers["x-accela-agency"] == "BPTDEV"
    assert req.headers["x-accela-environment"] == "TEST"
    hall = next(r.json for r in t.raw if "R311.6" in r.json["comment"])
    assert set(hall) == {"comment", "pageNumber", "status", "discipline"}
    assert hall["pageNumber"] == 1 and hall["status"] == {"value": "Open", "text": ""}
    assert hall["discipline"] == {"value": "Building", "text": ""}
    assert "TOKEN123" not in json.dumps(t.sent)                                  # never in what we keep


def test_accela_never_posts_twice_and_notices_changes(tmp_path):
    t = FixtureTransport([("POST", "comments", Response(200, b'{"result": {"id": 1}}'))])
    path = tmp_path / "ledger.json"
    c1 = AccelaClient(transport=t, dry_run=False, access_token="t", app_id="a", ledger=PostedLedger(path))
    cs = _cs()
    c1.post_comments("7", cs)
    assert len(t.sent) == 3
    c2 = AccelaClient(transport=t, dry_run=False, access_token="t", app_id="a", ledger=PostedLedger(path))   # a new run
    again = c2.post_comments("7", cs)
    assert [r.outcome for r in again] == ["skipped_duplicate"] * 3 and len(t.sent) == 3
    cs[0].text += " (edited)"
    assert c2.post_comments("7", cs)[0].outcome == "skipped_changed" and len(t.sent) == 3
    assert c2.post_comments("8", cs)[0].outcome == "posted"                      # another document is another target
    assert "t" not in {v for e in json.loads(path.read_text()).values() for v in e.values() if isinstance(v, str) and len(v) == 1}


def test_accela_failure_is_reported_and_not_remembered():
    t = FixtureTransport([("POST", "comments", Response(400, b'{"message":"bad"}'))])
    ledger = PostedLedger()
    r = AccelaClient(transport=t, dry_run=False, access_token="t", app_id="a", ledger=ledger).post_comments("7", _cs()[:1])
    assert r[0].outcome == "failed" and r[0].http_status == 400 and not ledger.data


def test_accela_dry_run_records_and_sends_nothing():
    c = AccelaClient(dry_run=True)
    res = c.post_comments("154694", _cs())
    assert [r.outcome for r in res] == ["dry_run"] * 3 and len(c.transport.sent) == 3
    assert c.transport.sent[0]["json"]["comment"].startswith("1.")
    assert "dry-run-token" not in json.dumps(c.transport.sent)                   # even the placeholder is masked
    assert AccelaClient(dry_run=True).ledger.data == {}


def test_accela_missing_token_is_an_error_not_a_guess():
    with pytest.raises(ConnectorError, match="ACCELA_ACCESS_TOKEN"):
        AccelaClient(transport=FixtureTransport([]), dry_run=False).post_comments("1", _cs()[:1])


def test_accela_token_comes_from_environment(monkeypatch):
    monkeypatch.setenv("ACCELA_ACCESS_TOKEN", "ENVTOKEN")
    monkeypatch.setenv("ACCELA_APP_ID", "ENVAPP")
    t = FixtureTransport([("POST", "comments", Response(200, b'{"result": {"id": 5}}'))])
    AccelaClient(transport=t, dry_run=False).post_comments("1", _cs()[:1])
    assert t.raw[0].headers["Authorization"] == "ENVTOKEN" and t.raw[0].headers["x-accela-appid"] == "ENVAPP"


def test_accela_checkin_multipart(tmp_path):
    t = FixtureTransport([("POST", r"/records/14CAP-00000-009AZ/documents/500062/checkin$",
                           Response(200, b'{"status": 200, "result": [{"id": 500063}]}'))])
    pdf = base_pdf(tmp_path / "marked.pdf")
    c = AccelaClient(transport=t, dry_run=False, access_token="t", app_id="a")
    r = c.checkin("14CAP-00000-009AZ", "500062", pdf, service_provider_code="BPTDEV", resubmit=True)
    assert r.outcome == "posted" and r.remote_id == 500063
    parts = t.raw[0].multipart
    assert set(parts) == {"uploadedFile", "fileInfo"} and parts["uploadedFile"][0] == "marked.pdf"
    info = json.loads(parts["fileInfo"][1])
    assert info == [{"serviceProviderCode": "BPTDEV", "fileName": "marked.pdf", "type": "application/pdf", "resubmit": "true",
                     "description": "ReviewPulse annotated set"}]
    assert c.checkin("14CAP-00000-009AZ", "500062", pdf, service_provider_code="BPTDEV", resubmit=True).outcome == "skipped_duplicate"


# ---- Bluebeam Studio ------------------------------------------------------------------------------------------------

UPLOAD = "https://storage.example.invalid/bucket/key?sig=abc"


def _studio_routes(snapshots=None):
    snaps = snapshots or [Response(200, b'{"Status": "Complete", "DownloadUrl": "https://dl.example.invalid/x"}')]
    return FixtureTransport([
        ("POST", r"/oauth2/token$", Response(200, b'{"token_type":"Bearer","expires_in":3600,"access_token":"AT1","refresh_token":"RT2"}')),
        ("POST", r"/publicapi/v1/sessions$", Response(200, b'{"$id": "1", "Id": "123-456-789"}')),
        ("POST", r"/sessions/123-456-789/files$", Response(200, json.dumps(
            {"Id": 1234567, "UploadUrl": UPLOAD, "UploadContentType": "Application/PDF"}).encode())),
        ("PUT", r"storage\.example\.invalid", Response(200)),
        ("POST", r"/files/1234567/confirm-upload$", Response(204)),
        ("POST", r"/invite$", Response(204)),
        ("POST", r"/users$", Response(204)),
        ("PUT", r"/publicapi/v1/sessions/123-456-789$", Response(204)),
        ("POST", r"/files/1234567/snapshot$", Response(200, b"{}")),
        ("GET", r"/files/1234567/snapshot$", snaps),
        ("DELETE", r"/publicapi/v1/sessions/123-456-789$", Response(204)),
    ])


def test_bluebeam_session_flow_from_the_guide(tmp_path):
    t = _studio_routes()
    rotated = []
    c = BluebeamClient(transport=t, dry_run=False, region="UK", client_id="CID", client_secret="CSECRET",
                       refresh_token="RT1", on_refresh_token=rotated.append)
    pdf = base_pdf(tmp_path / "marked.pdf")
    out = c.publish("Plan review 24-0113", pdf, ["a@example.com", "b@example.com"], message="Please review")
    assert out == {"session_id": "123-456-789", "file_id": 1234567, "invited": ["a@example.com", "b@example.com"], "dry_run": False}
    assert rotated == ["RT2"]                                                    # the new refresh token is handed over
    steps = [(r.method, r.url.replace("https://api.bluebeamstudio.co.uk", "")) for r in t.raw]
    assert steps[0] == ("POST", "/oauth2/token")
    assert steps[1:5] == [("POST", "/publicapi/v1/sessions"), ("POST", "/publicapi/v1/sessions/123-456-789/files"),
                          ("PUT", UPLOAD), ("POST", "/publicapi/v1/sessions/123-456-789/files/1234567/confirm-upload")]
    tok = t.raw[0]
    assert tok.headers["Authorization"].startswith("Basic ") and tok.form == {"grant_type": "refresh_token", "refresh_token": "RT1"}
    sess = t.raw[1]
    assert sess.headers["Authorization"] == "Bearer AT1" and sess.headers["client_id"] == "CID"
    assert sess.json["Name"] == "Plan review 24-0113" and {"Type": "Markup", "Allow": "Allow"} in sess.json["DefaultPermissions"]
    meta = t.raw[2].json
    assert meta == {"Name": "marked.pdf", "Source": "ReviewPulse", "Size": None, "CRC": None}
    put = t.raw[3]
    assert put.body == pdf.read_bytes() and put.headers["x-amz-server-side-encryption"] == "AES256"
    assert "Authorization" not in put.headers and "client_id" not in put.headers  # the Bluebeam token never goes to storage
    assert t.raw[5].json == {"Email": "a@example.com", "Message": "Please review"} and t.raw[5].url.endswith("/invite")
    dump_ = json.dumps(t.sent)
    for secret in ("CSECRET", "RT1", "RT2", "AT1"):
        assert secret not in dump_


def test_bluebeam_snapshot_polls_until_complete():
    t = _studio_routes([Response(200, b'{"Status": "InProgress"}'), Response(200, b'{"Status": "Complete", "DownloadUrl": "https://dl/x"}')])
    c = BluebeamClient(transport=t, dry_run=False, access_token="AT", client_id="CID")
    waits = []
    assert c.snapshot("123-456-789", 1234567, sleep=waits.append) == "https://dl/x" and waits == [2.0]
    c.finalize("123-456-789")
    assert next(r for r in t.raw if r.method == "PUT").json == {"Status": "Finalizing"}
    c.close("123-456-789")
    assert t.raw[-1].method == "DELETE"


def test_bluebeam_rejects_non_pdf_and_failed_upload(tmp_path):
    c = BluebeamClient(transport=_studio_routes(), dry_run=False, access_token="AT", client_id="CID")
    with pytest.raises(ConnectorError, match=".pdf"):
        c.add_pdf("123-456-789", b"x", name="plan.dwg")
    bad = _studio_routes()
    bad.routes.insert(0, ("PUT", "storage", Response(403)))
    with pytest.raises(ConnectorError, match="storage upload"):
        BluebeamClient(transport=bad, dry_run=False, access_token="AT", client_id="CID").add_pdf("123-456-789", b"%PDF", name="a.pdf")
    with pytest.raises(ConnectorError, match="region"):
        BluebeamClient(region="MARS")


def test_bluebeam_dry_run_goes_through_every_step(tmp_path):
    c = BluebeamClient(dry_run=True)
    out = c.publish("Dry", base_pdf(tmp_path / "p.pdf"), ["a@example.com"])
    assert out["dry_run"] is True and out["session_id"] == "dry-run-session"
    assert len(c.transport.sent) >= 6
    assert any("storage.example.invalid" in r["url"] for r in c.transport.sent)


def test_bluebeam_needs_credentials_from_environment():
    with pytest.raises(ConnectorError, match="BLUEBEAM_CLIENT_ID"):
        BluebeamClient(transport=_studio_routes(), dry_run=False).create_session("x")


# ---- OpenGov --------------------------------------------------------------------------------------------------------


def test_opengov_step_comment_contract():
    t = FixtureTransport([("POST", r"/plce/v2/springfield/records/R1/workflow-steps/S2/comments$",
                           Response(201, b'{"data": {"id": "88", "type": "workflowStepComment"}}'))])
    o = OpenGovClient(transport=t, dry_run=False, community="springfield", access_token="OGT")
    res = o.post_step_comments("R1", "S2", _cs())
    assert [r.outcome for r in res] == ["posted"] * 3 and res[0].remote_id == "88"
    req = t.raw[0]
    assert req.headers["Content-Type"] == "application/vnd.api+json" and req.headers["Authorization"] == "Bearer OGT"
    body = next(r.json for r in t.raw if "R311.6" in r.json["data"]["attributes"]["comment"])
    assert body["data"]["type"] == "workflowStepComment" and body["data"]["attributes"]["commentType"] == "COMMENT"
    assert "(sheet A101, page 1)" in body["data"]["attributes"]["comment"]       # the place goes into the text
    assert [r.outcome for r in o.post_step_comments("R1", "S2", _cs())] == ["skipped_duplicate"] * 3
    assert "OGT" not in json.dumps(t.sent)


def test_opengov_dry_run():
    o = OpenGovClient(dry_run=True, community="c")
    assert [r.outcome for r in o.post_step_comments("R", "S", _cs())] == ["dry_run"] * 3


# ---- file drop and webhook ------------------------------------------------------------------------------------------


def test_json_and_csv_roundtrip(tmp_path):
    cs = _comments_for_bcf()
    assert filedrop.read_json(filedrop.write_json(cs, tmp_path / "c.json")) == cs
    back = filedrop.read_csv(filedrop.write_csv(cs, tmp_path / "c.csv"))
    assert [(c.id, c.text, c.state, c.page, c.bbox, c.citation) for c in back] == [
        (c.id, c.text, c.state, c.page, c.bbox, c.citation) for c in cs]
    assert _hall(back).source_facts["detected"] == "30 in"
    bad = (tmp_path / "c.csv").read_text(encoding="utf-8-sig").replace(",open,", ",weird,", 1)
    (tmp_path / "bad.csv").write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError, match="unknown state"):
        filedrop.read_csv(tmp_path / "bad.csv")


def test_drop_folder_writes_whole_files(tmp_path):
    paths = filedrop.drop(_cs(), tmp_path / "inbox", project="p1")
    assert {p.suffix for p in paths} == {".json", ".csv"} and not list((tmp_path / "inbox").glob(".*.part"))


def test_webhook_is_signed_and_dry_run_sends_nothing():
    r = filedrop.post_webhook(_cs(), "https://office.example/hook", dry_run=True)
    rec = json.loads(r.headers["recorded"])
    assert rec["headers"]["X-ReviewPulse-Signature"].startswith("sha256=") and rec["body"]["bytes"] > 100
    t = FixtureTransport([("POST", "office.example", Response(202))])
    filedrop.post_webhook(_cs(), "https://office.example/hook", transport=t, dry_run=False, secret="whsec")
    sent = t.raw[0]
    assert filedrop.verify(sent.body, sent.headers["X-ReviewPulse-Signature"], "whsec")
    assert not filedrop.verify(sent.body + b"x", sent.headers["X-ReviewPulse-Signature"], "whsec")
    assert "whsec" not in json.dumps(t.sent)


def test_recording_transport_has_no_network():
    t = RecordingTransport()
    assert t.send(Request("GET", "https://example.invalid")).ok and len(t.sent) == 1


# ---- command line ---------------------------------------------------------------------------------------------------


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    run = proj / "run"
    run.mkdir(parents=True)
    pdf = base_pdf(proj / "plan.pdf")
    (run / "findings.json").write_text(json.dumps(FINDINGS), encoding="utf-8")
    (run / "building_0.json").write_text(json.dumps({"sheet": {"id": "A101", "page": 0, "source_file": str(pdf)}}), encoding="utf-8")
    return proj


@pytest.mark.parametrize("fmt", ["pdf", "bcf", "json", "csv"])
def test_cli_export(tmp_path, fmt, capsys):
    proj = _project(tmp_path)
    out = tmp_path / f"o.{fmt}"
    assert cli.main(["export", "--project", str(proj), "--format", fmt, "--out", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 100
    if fmt == "pdf":
        assert len(pdf_io.read_annotations(out).comments) == 3
    if fmt == "bcf":
        assert bcf.validate_bcf(out, XSD) == []
        assert any(n.endswith("snapshot.png") for n in zipfile.ZipFile(out).namelist())
    if fmt == "json":
        assert len(filedrop.read_json(out)) == 3


def test_cli_read_markups_and_dry_push(tmp_path, capsys):
    proj = _project(tmp_path)
    marked = tmp_path / "m.pdf"
    cli.main(["export", "--project", str(proj), "--format", "pdf", "--out", str(marked)])
    js = tmp_path / "m.json"
    assert cli.main(["read-markups", str(marked), "--out", str(js)]) == 0 and len(filedrop.read_json(js)) == 3
    assert cli.main(["push", "accela", str(js), "--document-id", "154694"]) == 0
    text = capsys.readouterr().out
    assert "dry_run" in text and "154694" in text
    with pytest.raises(SystemExit):
        cli.main(["export", "--project", str(tmp_path), "--format", "json"])
