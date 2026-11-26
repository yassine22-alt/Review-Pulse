"""BCF 2.1 (buildingSMART BIM Collaboration Format) export and import.

One correction item is one BCF topic. A BCF zip holds `bcf.version`, `project.bcfp`, our `extensions.xsd` (the lists of
statuses, priorities and labels we use) and one folder per topic with `markup.bcf`, `viewpoint.bcfv` and, when a source PDF is
at hand, `snapshot.png` (a crop of the page around the item).

Our findings come from PDF drawings, not from an IFC model, so the viewpoint is a stub (`VisualizationInfo` with only a Guid;
no camera, no components) and the real location is a 2D page reference in a snippet: `BimSnippet` of type
`ReviewPulse2DPageReference` pointing at `page_reference.json` in the topic folder (file, page, box in PDF points). A BCF
viewer opens the topic with its text, labels, status and picture but cannot fly to a place in a 3D model, because there is none.

Validated against the buildingSMART release_2_1 XSDs (markup, visinfo, project, version) when a folder holding them is given to
`validate_bcf`; the XSDs are not shipped inside the package (tests keep a copy under tests/fixtures/bcf21). Not opened in
Solibri, Revit or Trimble.
"""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from .model import STATE_WORDS, STATES, Reply, ReviewComment, StatusEntry

NS_UUID = uuid.UUID("6f1c1e0e-7a53-4a55-9a52-2d6f8a3c6b11")
SNIPPET_TYPE = "ReviewPulse2DPageReference"
SNIPPET_SCHEMA = "reviewpulse.page-reference/1"
STATUS_PREFIX = "ReviewPulse status: "
PRIORITY = {"critical": "Critical", "major": "Major", "minor": "Minor", "info": "Info"}
# priorities and statuses used by other tools, read into ours
PRIORITY_IN = {"critical": "critical", "major": "major", "high": "major", "normal": "minor", "medium": "minor",
               "minor": "minor", "low": "info", "info": "info"}
STATUS_IN = {"open": "open", "new": "open", "active": "open", "in progress": "open", "assigned": "open",
             "information requested": "information_requested", "deferred": "deferred", "not applicable": "not_applicable",
             "resolved": "addressed", "addressed": "addressed", "closed": "verified", "verified": "verified",
             "done": "verified", "rejected": "rejected", "dismissed": "dismissed", "reopened": "open"}
WORD_TO_STATE = {v.lower(): k for k, v in STATE_WORDS.items()}


def topic_guid(comment_id: str) -> str:
    return str(uuid.uuid5(NS_UUID, comment_id))


def _dt(iso: str) -> str:
    if not iso:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs) -> ET.Element:
    el = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        el.text = text
    return el


def _xml(root: ET.Element) -> bytes:
    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def _extensions_xsd(comments: list[ReviewComment], author_list: list[str]) -> bytes:
    def enum(name: str, values) -> str:
        items = "".join(f'<xs:enumeration value="{v}"/>' for v in values)
        return f'  <xs:simpleType name="{name}"><xs:restriction base="xs:string">{items}</xs:restriction></xs:simpleType>\n'

    labels = sorted({x for c in comments for x in (c.discipline, c.citation) if x})
    body = (enum("TopicType", ["Correction"]) + enum("TopicStatus", STATE_WORDS.values())
            + enum("Priority", PRIORITY.values()) + enum("TopicLabel", labels or ["ReviewPulse"])
            + enum("SnippetType", [SNIPPET_TYPE]) + enum("UserIdType", author_list or ["ReviewPulse"]))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
            f"{body}</xs:schema>\n").encode()


def _title(c: ReviewComment) -> str:
    head = f"{c.number}. " if c.number else ""
    cite = f"[{c.citation}] " if c.citation else ""
    text = " ".join(c.text.split())
    return (head + cite + (text if len(text) <= 100 else text[:97] + "...")).strip() or c.id


def _description(c: ReviewComment) -> str:
    lines = [c.text]
    if c.citation:
        lines.append(f"Code: {c.citation}" + (f" ({c.citation_doc})" if c.citation_doc else ""))
    if c.evidence_quote:
        lines.append(f"Evidence from the plan: {c.evidence_quote}")
    for k in ("detected", "required"):
        if c.source_facts.get(k):
            lines.append(f"{k.capitalize()}: {c.source_facts[k]}")
    if c.sheet or c.page:
        lines.append(f"Sheet {c.sheet or '?'}, page {c.page or '?'}")
    return "\n".join(lines)


def export_bcf(comments: list[ReviewComment], out: str | Path, *, project_name: str = "ReviewPulse",
               project_id: str | None = None, pdf_name: str = "", snapshots: dict[str, bytes] | None = None) -> Path:
    """Write a BCF 2.1 zip with one topic per comment. `snapshots` maps a comment id to PNG bytes."""
    out = Path(out)
    snapshots = snapshots or {}
    authors = sorted({c.author for c in comments if c.author})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        ver = ET.Element("Version", VersionId="2.1")
        _sub(ver, "DetailedVersion", "2.1")
        z.writestr("bcf.version", _xml(ver))
        proj = ET.Element("ProjectExtension")
        _sub(proj, "Project", None, ProjectId=project_id or str(uuid.uuid5(NS_UUID, project_name))).append(
            _text_el("Name", project_name))
        _sub(proj, "ExtensionSchema", "extensions.xsd")
        z.writestr("project.bcfp", _xml(proj))
        z.writestr("extensions.xsd", _extensions_xsd(comments, authors))
        for c in comments:
            guid, vguid = topic_guid(c.id), topic_guid(c.id + "#viewpoint")
            root = ET.Element("Markup")
            if pdf_name:
                h = _sub(root, "Header")
                f = _sub(h, "File", None, isExternal="true")
                _sub(f, "Filename", pdf_name)
                _sub(f, "Reference", pdf_name)
            t = _sub(root, "Topic", None, Guid=guid, TopicType="Correction", TopicStatus=STATE_WORDS[c.state])
            _sub(t, "ReferenceLink", f"reviewpulse:{c.id}")
            _sub(t, "Title", _title(c))
            if c.severity in PRIORITY:
                _sub(t, "Priority", PRIORITY[c.severity])
            if c.number:
                _sub(t, "Index", str(c.number))
            for label in dict.fromkeys(x for x in (c.discipline, c.citation, f"Cycle {c.cycle}") if x):
                _sub(t, "Labels", label)
            _sub(t, "CreationDate", _dt(c.created))
            _sub(t, "CreationAuthor", c.author or "ReviewPulse")
            if c.modified:
                _sub(t, "ModifiedDate", _dt(c.modified))
            _sub(t, "Description", _description(c))
            sn = _sub(t, "BimSnippet", None, SnippetType=SNIPPET_TYPE, isExternal="false")
            _sub(sn, "Reference", "page_reference.json")
            _sub(sn, "ReferenceSchema", SNIPPET_SCHEMA)
            first = _sub(root, "Comment", None, Guid=topic_guid(c.id + "#c0"))
            _sub(first, "Date", _dt(c.created))
            _sub(first, "Author", c.author or "ReviewPulse")
            _sub(first, "Comment", c.text)
            _sub(first, "Viewpoint", None, Guid=vguid)
            for i, h in enumerate(c.status_history, 1):
                el = _sub(root, "Comment", None, Guid=topic_guid(f"{c.id}#s{i}"))
                _sub(el, "Date", _dt(h.at))
                _sub(el, "Author", h.by or "ReviewPulse")
                _sub(el, "Comment", STATUS_PREFIX + STATE_WORDS[h.state] + (f". {h.note}" if h.note else ""))
            for i, r in enumerate(c.replies, 1):
                el = _sub(root, "Comment", None, Guid=topic_guid(f"{c.id}#r{i}"))
                _sub(el, "Date", _dt(r.at))
                _sub(el, "Author", r.author or "ReviewPulse")
                _sub(el, "Comment", r.text)
            vp = _sub(root, "Viewpoints", None, Guid=vguid)
            _sub(vp, "Viewpoint", "viewpoint.bcfv")
            if c.id in snapshots:
                _sub(vp, "Snapshot", "snapshot.png")
                z.writestr(f"{guid}/snapshot.png", snapshots[c.id])
            _sub(vp, "Index", "0")
            z.writestr(f"{guid}/markup.bcf", _xml(root))
            z.writestr(f"{guid}/viewpoint.bcfv", _xml(ET.Element("VisualizationInfo", Guid=vguid)))
            ref = {"schema": SNIPPET_SCHEMA, "file": pdf_name, "page": c.page, "bbox_pt": c.bbox, "sheet": c.sheet,
                   "coordinates": "PDF points, unrotated page, origin top left, y down; page counted from 1",
                   "reviewpulse": c.model_dump(mode="json", include={"id", "discipline", "citation_doc", "evidence_quote",
                                                                   "source_facts", "cycle", "number", "located"})}
            z.writestr(f"{guid}/page_reference.json", json.dumps(ref, indent=1, ensure_ascii=False))
    return out


def _text_el(tag: str, text: str) -> ET.Element:
    el = ET.Element(tag)
    el.text = text
    return el


def import_bcf(path: str | Path, *, cycle: int = 1) -> list[ReviewComment]:
    """Read a BCF 2.1 or 2.0 zip (from us or from another tool) into comments. Unknown statuses become `open`.

    The first Comment is the item wording; later comments that start with our status prefix become status history, the rest
    become replies."""
    out: list[ReviewComment] = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for name in sorted(n for n in names if n.endswith("markup.bcf")):
            folder = name[: -len("markup.bcf")]
            root = ET.fromstring(z.read(name))
            topic = root.find("Topic")
            if topic is None:
                continue
            ref = {}
            if f"{folder}page_reference.json" in names:
                try:
                    ref = json.loads(z.read(f"{folder}page_reference.json"))
                except ValueError:
                    ref = {}
            kept = ref.get("reviewpulse", {})

            def val(tag, node=topic):
                el = node.find(tag)
                return (el.text or "").strip() if el is not None and el.text else ""

            link = val("ReferenceLink")
            cid = link.split("reviewpulse:", 1)[1] if link.startswith("reviewpulse:") else topic.get("Guid", folder.strip("/"))
            comments = root.findall("Comment")
            first = comments[0] if comments else None
            history, replies = [], []
            for el in comments[1:]:
                text = val("Comment", el)
                if text.startswith(STATUS_PREFIX):
                    word, _, note = text[len(STATUS_PREFIX):].partition(". ")
                    history.append(StatusEntry(state=WORD_TO_STATE.get(word.strip().lower(), "open"),
                                               by=val("Author", el), at=val("Date", el), note=note))
                else:
                    replies.append(Reply(author=val("Author", el), at=val("Date", el), text=text))
            status = (topic.get("TopicStatus") or "").strip().lower()
            state = WORD_TO_STATE.get(status) or STATUS_IN.get(status, "open")
            labels = [(el.text or "").strip() for el in topic.findall("Labels")]
            title = val("Title")
            text = val("Comment", first) if first is not None else (val("Description") or title)
            number = int(kept["number"]) if kept.get("number") else (int(val("Index")) if val("Index").isdigit() else 0)
            citation = next((x for x in labels if x and not x.startswith("Cycle ") and x != kept.get("discipline")), "")
            page = ref.get("page")
            bbox = ref.get("bbox_pt")
            out.append(ReviewComment(
                id=cid, number=number, discipline=kept.get("discipline", ""), citation=citation,
                citation_doc=kept.get("citation_doc", ""), text=text or title, sheet=ref.get("sheet", ""),
                page=int(page) if page else None, bbox=[float(x) for x in bbox] if bbox else None,
                located=bool(page and bbox), state=state if state in STATES else "open",
                severity=PRIORITY_IN.get(val("Priority").lower(), ""), evidence_quote=kept.get("evidence_quote", ""),
                source_facts=kept.get("source_facts", {}), cycle=kept.get("cycle", cycle),
                author=val("CreationAuthor"), created=val("CreationDate"), modified=val("ModifiedDate"),
                status_history=history, replies=replies, origin="bcf"))
    return out


def validate_bcf(path: str | Path, schema_dir: str | Path) -> list[str]:
    """Validate every XML part of a BCF zip against the buildingSMART 2.1 XSDs in `schema_dir`; returns the problems found
    (empty list: valid). Needs markup.xsd, visinfo.xsd, project.xsd, version.xsd in that folder."""
    from lxml import etree

    schemas = {k: etree.XMLSchema(etree.parse(str(Path(schema_dir) / f"{k}.xsd")))
               for k in ("markup", "visinfo", "project", "version")}
    wanted = {"markup.bcf": "markup", "viewpoint.bcfv": "visinfo", "project.bcfp": "project", "bcf.version": "version"}
    problems = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            kind = wanted.get(name.rsplit("/", 1)[-1])
            if not kind:
                continue
            doc = etree.fromstring(z.read(name))
            if not schemas[kind].validate(doc):
                problems += [f"{name}: {e.message} (line {e.line})" for e in schemas[kind].error_log]
    return problems
