"""Standard PDF annotations, written and read back with PyMuPDF.

Write. Each correction item becomes, on its page: a cloud (Polygon annotation with the /BE cloud border effect) that carries the
item (Subject = item number, Contents = full wording, T = author, colour by state); a FreeText callout with a leader line (/IT
/FreeTextCallout, /CL) holding the short wording; and a Text note (sticky note) at the corner. A state other than `open` is
written as a reply annotation with /IRT, /StateModel (Review) and /State, the way Bluebeam Revu stores the Status column.
Replies are Text annotations with /IRT. Our own keys (/RPId, /RPRole, /RPState) make a round trip lossless; other tools ignore them.

Read. Any annotated PDF (Bluebeam Revu, Acrobat, Foxit, ...). One markup is one comment; replies with /IRT become replies,
replies with /State become the status history, and the latest status sets the state. Odd files are survived and reported
in `ReadResult.warnings`: a bad /IRT, a loop of replies, an annotation that cannot be read, a PDF needing a password.

Not verified: that Revu draws the cloud and callout exactly as we mean. The files are valid PDF annotations read back by
PyMuPDF; nobody has opened them in Revu (see docs/progress/M26_connectors.md).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pymupdf

from .model import STATES, Reply, ReviewComment, StatusEntry, short_text

# Bluebeam's Review state model against our states (lossy; /RPState carries ours exactly)
TO_REVIEW = {"open": "None", "information_requested": "None", "deferred": "None", "not_applicable": "Cancelled",
             "addressed": "Completed", "verified": "Accepted", "rejected": "Rejected", "dismissed": "Cancelled"}
FROM_REVIEW = {"none": "open", "accepted": "verified", "rejected": "rejected", "cancelled": "dismissed",
               "completed": "addressed", "marked": "open", "unmarked": "open"}
STATE_COLOURS = {"open": (0.85, 0.1, 0.1), "information_requested": (0.95, 0.6, 0.0), "deferred": (0.4, 0.4, 0.8),
                 "not_applicable": (0.5, 0.5, 0.5), "addressed": (0.1, 0.6, 0.2), "verified": (0.1, 0.6, 0.2),
                 "rejected": (0.85, 0.1, 0.1), "dismissed": (0.5, 0.5, 0.5)}
SKIP_TYPES = {"Link", "Widget", "Popup", "Movie", "Sound", "Screen", "TrapNet", "Watermark", "3D", "Redact"}
FLAG_PRINT, FLAG_NOZOOM, FLAG_NOROTATE = 4, 8, 16


def _pdf_date(when: datetime | None = None) -> str:
    return (when or datetime.now(UTC)).strftime("D:%Y%m%d%H%M%SZ")


def _iso(pdf_date: str) -> str:
    """'D:20260301120000+01'00'' to ISO 8601; '' when it cannot be read."""
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(Z|[+-]\d{2}'?\d{0,2}'?)?", pdf_date or "")
    if not m:
        return ""
    y, mo, d, h, mi, s, tz = m.groups()
    out = f"{y}-{mo or '01'}-{d or '01'}T{h or '00'}:{mi or '00'}:{s or '00'}"
    if tz and tz != "Z":
        digits = re.sub(r"[^0-9]", "", tz[1:])
        out += f"{tz[0]}{digits[:2]}:{(digits[2:4] or '00')}"
    else:
        out += "Z"
    return out


def _pdf_date_from_iso(iso: str) -> str:
    try:
        return _pdf_date(datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC))
    except ValueError:
        return _pdf_date()


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0, min(1, v)) * 255):02x}" for v in rgb[:3]) if rgb and len(rgb) >= 3 else ""


def _lit(text: str) -> str:
    """A PDF literal string for xref_set_key."""
    return "(" + str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


# ---- write ----------------------------------------------------------------------------------------------------------


@dataclass
class WriteResult:
    out: Path
    written: int = 0
    unlocated: int = 0
    skipped: list[str] = field(default_factory=list)       # comment ids that could not be placed on the PDF
    warnings: list[str] = field(default_factory=list)


def _callout_rect(bbox: pymupdf.Rect, text: str, W: float, H: float) -> pymupdf.Rect:
    width = 190.0
    lines = max(1, -(-len(text) * 4.6 // (width - 8)) + text.count("\n"))
    height = min(150.0, 12.0 * lines + 10)
    for x0 in (bbox.x1 + 14, bbox.x0 - 14 - width):
        if 0 <= x0 and x0 + width <= W:
            y0 = min(max(0, bbox.y0), H - height)
            return pymupdf.Rect(x0, y0, x0 + width, y0 + height)
    y0 = bbox.y0 - 8 - height if bbox.y0 - 8 - height >= 0 else min(bbox.y1 + 8, H - height)
    x0 = min(max(0, bbox.x0), W - width)
    return pymupdf.Rect(x0, y0, x0 + width, y0 + height)


def _tag(doc, xref: int, cid: str, role: str, state: str | None = None) -> None:
    doc.xref_set_key(xref, "RPId", _lit(cid))
    doc.xref_set_key(xref, "RPRole", f"/{role}")
    if state:
        doc.xref_set_key(xref, "RPState", f"/{state}")


def _info(annot, c: ReviewComment, author: str, content: str, created: str) -> None:
    annot.set_info(content=content, title=author, subject=str(c.number or ""), creationDate=created, modDate=created)


def _reply(doc, page, parent_xref: int, at: pymupdf.Point, *, author: str, content: str, when: str,
           state: str | None = None, cid: str = "") -> int:
    r = page.add_text_annot(at, content or " ", icon="Comment")
    r.set_info(content=content, title=author, creationDate=when, modDate=when)
    r.set_flags(FLAG_PRINT | FLAG_NOZOOM | FLAG_NOROTATE)
    r.update()
    x = r.xref
    doc.xref_set_key(x, "IRT", f"{parent_xref} 0 R")
    doc.xref_set_key(x, "RT", "/R")
    if state:
        doc.xref_set_key(x, "StateModel", "(Review)")
        doc.xref_set_key(x, "State", _lit(TO_REVIEW[state]))
        doc.xref_set_key(x, "RPState", f"/{state}")
        _tag(doc, x, cid, "status")
    else:
        _tag(doc, x, cid, "reply")
    return x


def write_annotations(src: str | Path, out: str | Path, comments: list[ReviewComment], *, author: str = "",
                      parts: tuple[str, ...] = ("cloud", "callout", "note")) -> WriteResult:
    """Copy `src` to `out` with the comments added as standard annotations. The source file is never changed.

    A comment without a page or box (or one beyond the page count) is still written, as a note at the top left of page 1 when
    it has no place, and is listed in `skipped` only when the PDF has no pages."""
    doc = pymupdf.open(str(src))
    res = WriteResult(Path(out))
    if doc.needs_pass:
        raise ValueError("the PDF is encrypted and needs a password; unlock it first")
    if doc.page_count == 0:
        raise ValueError("the PDF has no pages")
    stack: dict[int, int] = {}          # unlocated notes already placed per page
    for c in comments:
        who = c.author or author or "ReviewPulse"
        created = _pdf_date_from_iso(c.created) if c.created else _pdf_date()
        pno = (c.page - 1) if c.page and 1 <= c.page <= doc.page_count else 0
        page = doc[pno]
        W, H = page.mediabox_size
        located = bool(c.located and c.bbox and c.page == pno + 1)
        if located:
            box = pymupdf.Rect(*c.bbox) & pymupdf.Rect(0, 0, W, H)
            if box.is_empty or box.width < 6 or box.height < 6:
                box = pymupdf.Rect(box.x0 - 6, box.y0 - 6, box.x0 + 6, box.y0 + 6) & pymupdf.Rect(0, 0, W, H)
        else:
            res.unlocated += 1
            k = stack.get(pno, 0)
            stack[pno] = k + 1
            box = pymupdf.Rect(36, 36 + 22 * k, 56, 56 + 22 * k)
        colour = STATE_COLOURS[c.state]
        full = f"{c.text}" + (f"\n[{c.citation}]" if c.citation else "") + (f"\nEvidence: {c.evidence_quote}" if c.evidence_quote else "")
        primary: int | None = None
        try:
            if "cloud" in parts and located:
                pts = [box.tl, box.tr, box.br, box.bl]
                a = page.add_polygon_annot(pts)
                a.set_border(width=1.5)
                a.set_colors(stroke=colour)
                _info(a, c, who, full, created)
                a.set_flags(FLAG_PRINT)
                a.update()
                doc.xref_set_key(a.xref, "BE", "<</S/C/I 2>>")
                _tag(doc, a.xref, c.id, "primary", c.state)
                primary = a.xref
            if "callout" in parts and located:
                text = f"{c.number}. {short_text(c)}" if c.number else short_text(c)
                rect = _callout_rect(box, text, W, H)
                f = page.add_freetext_annot(rect, text, fontsize=8, text_color=colour, fill_color=(1, 1, 0.85),
                                            border_width=0.8)
                _info(f, c, who, text, created)
                f.set_flags(FLAG_PRINT)
                f.update()
                inv = ~page.transformation_matrix
                start = (pymupdf.Point(rect.x0, rect.y0 + rect.height / 2) if rect.x0 > box.x1
                         else pymupdf.Point(rect.x1, rect.y0 + rect.height / 2)) * inv
                end = pymupdf.Point(box.x1 if rect.x0 > box.x1 else box.x0, (box.y0 + box.y1) / 2) * inv
                doc.xref_set_key(f.xref, "IT", "/FreeTextCallout")
                doc.xref_set_key(f.xref, "CL", f"[{start.x:.2f} {start.y:.2f} {end.x:.2f} {end.y:.2f}]")
                _tag(doc, f.xref, c.id, "callout", c.state)
            if "note" in parts or primary is None:
                n = page.add_text_annot(pymupdf.Point(box.x0, box.y0), full, icon="Comment")
                n.set_colors(stroke=colour)
                _info(n, c, who, full, created)
                n.set_flags(FLAG_PRINT)
                n.update()
                _tag(doc, n.xref, c.id, "primary" if primary is None else "pin", c.state)
                if primary is None:
                    primary = n.xref
            if not located:
                doc.xref_set_key(primary, "RPUnlocated", "true")
            keep = c.model_dump(mode="json", exclude={"status_history", "replies", "text", "bbox", "page", "state"})
            doc.xref_set_key(primary, "RPJson", _lit(json.dumps(keep, ensure_ascii=True, separators=(",", ":"))))
            point = pymupdf.Point(box.x0, box.y0)
            history = c.status_history or ([StatusEntry(state=c.state, by=who)] if c.state != "open" else [])
            for h in history:
                _reply(doc, page, primary, point, author=h.by or who, content=h.note, state=h.state,
                       when=_pdf_date_from_iso(h.at) if h.at else created, cid=c.id)
            for r in c.replies:
                _reply(doc, page, primary, point, author=r.author or who, content=r.text,
                       when=_pdf_date_from_iso(r.at) if r.at else created, cid=c.id)
            res.written += 1
        except Exception as exc:        # one bad item must not lose the rest of the list
            res.skipped.append(c.id)
            res.warnings.append(f"{c.id}: {type(exc).__name__}: {exc}")
    doc.save(str(out), garbage=1, deflate=True)
    doc.close()
    return res


# ---- read -----------------------------------------------------------------------------------------------------------


@dataclass
class ReadResult:
    comments: list[ReviewComment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    annotations_seen: int = 0


def _key(doc, xref: int, name: str) -> tuple[str, str]:
    try:
        kind, value = doc.xref_get_key(xref, name)
    except Exception:
        return "null", ""
    return kind, value


def _key_str(doc, xref: int, name: str) -> str:
    kind, value = _key(doc, xref, name)
    if kind == "null":
        return ""
    return value[1:] if kind == "name" and value.startswith("/") else value


def _key_ref(doc, xref: int, name: str) -> int | None:
    kind, value = _key(doc, xref, name)
    m = re.match(r"(\d+) 0 R", value) if kind == "xref" else None
    return int(m.group(1)) if m else None


def read_annotations(src: str | Path, *, cycle: int = 1) -> ReadResult:
    """Every markup of a PDF as a ReviewComment, with replies and status folded in. Comments are ordered by page then position."""
    doc = pymupdf.open(str(src))
    res = ReadResult()
    if doc.needs_pass:
        raise ValueError("the PDF is encrypted and needs a password; unlock it first")
    items: dict[int, dict] = {}
    for page in doc:
        try:
            annots = list(page.annots() or [])
        except Exception as exc:
            res.warnings.append(f"page {page.number + 1}: annotations unreadable ({type(exc).__name__})")
            continue
        for a in annots:
            res.annotations_seen += 1
            try:
                kind = a.type[1]
                if kind in SKIP_TYPES:
                    continue
                info = a.info
                rect = a.rect
                colours = a.colors or {}
                xref = a.xref
                rec = {"xref": xref, "kind": kind, "page": page.number + 1, "rect": [round(v, 2) for v in tuple(rect)],
                       "info": info, "colour": _hex(colours.get("stroke") or colours.get("fill") or ()),
                       "irt": _key_ref(doc, xref, "IRT"), "state": _key_str(doc, xref, "State"),
                       "model": _key_str(doc, xref, "StateModel"), "rpid": _key_str(doc, xref, "RPId"),
                       "role": _key_str(doc, xref, "RPRole"), "unlocated": _key_str(doc, xref, "RPUnlocated") == "true",
                       "rpjson": _key_str(doc, xref, "RPJson"), "rpstate": _key_str(doc, xref, "RPState"),
                       "cloud": "/C" in _key(doc, xref, "BE")[1].replace(" ", "") and kind in ("Polygon", "Square", "Circle", "PolyLine"),
                       "quote": ""}
                if kind in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
                    rec["quote"] = " ".join(page.get_textbox(rect).split())
                if kind == "Polygon" or kind == "PolyLine":
                    rec["vertices"] = len(a.vertices or [])
                items[xref] = rec
            except Exception as exc:
                res.warnings.append(f"page {page.number + 1}: one annotation skipped ({type(exc).__name__}: {exc})")
    # resolve each reply to its top level parent (no loops, no dangling references)
    def top(x: int) -> int | None:
        seen = set()
        while items[x]["irt"] is not None:
            if x in seen:
                return None
            seen.add(x)
            parent = items[x]["irt"]
            if parent not in items:
                return None
            x = parent
        return x

    roots: dict[int, dict] = {}
    children: dict[int, list[dict]] = {}
    for x, rec in items.items():
        if rec["irt"] is None:
            roots[x] = rec
            continue
        t = top(x)
        if t is None:
            res.warnings.append(f"annotation {x} replies to something unreadable; kept as a comment of its own")
            roots[x] = rec
        else:
            children.setdefault(t, []).append(rec)
    # one comment per /RPId group, else one per root
    by_id: dict[str, list[dict]] = {}
    singles: list[dict] = []
    for rec in roots.values():
        if rec["rpid"]:
            by_id.setdefault(rec["rpid"], []).append(rec)
        else:
            singles.append(rec)
    built: list[tuple[tuple, ReviewComment]] = []

    def build(group: list[dict], cid: str | None) -> ReviewComment:
        order = {"primary": 0, "pin": 1, "callout": 2}
        group = sorted(group, key=lambda r: order.get(r["role"], 3))
        lead = group[0]
        info = lead["info"]
        kids = [k for r in group for k in children.get(r["xref"], [])]
        kids.sort(key=lambda k: _iso(k["info"].get("creationDate", "")))
        history, replies = [], []
        for k in kids:
            ki = k["info"]
            if k["state"] or k["model"]:
                word = k["rpstate"] if k["rpstate"] in STATES else FROM_REVIEW.get(k["state"].lower(), "open")
                note = ki.get("content", "").strip()
                if k["model"] not in ("Review", ""):
                    note = (f"{k['model']}: {k['state']} " + note).strip()
                history.append(StatusEntry(state=word, by=ki.get("title", ""), at=_iso(ki.get("creationDate", "")), note=note))
            else:
                replies.append(Reply(author=ki.get("title", ""), at=_iso(ki.get("creationDate", "")),
                                     text=ki.get("content", "").strip()))
        state = history[-1].state if history else (lead["rpstate"] if lead["rpstate"] in STATES else "open")
        subject = info.get("subject", "")
        text = info.get("content", "").strip() or lead["quote"]
        facts = {"annotation_type": lead["kind"]}
        if lead["cloud"]:
            facts["cloud"] = True
        if lead.get("vertices"):
            facts["vertices"] = lead["vertices"]
        if lead["quote"] and lead["quote"] != text:
            facts["text_under_markup"] = lead["quote"]
        text = text.split("\nEvidence:")[0] if cid else text
        evidence = ""
        if cid and "\nEvidence:" in info.get("content", ""):
            evidence = info["content"].split("\nEvidence:", 1)[1].strip()
        citation = ""
        m = re.search(r"\n\[([^\]]+)\]\s*$", text) if cid else None
        if m:
            citation, text = m.group(1), text[: m.start()]
        kept: dict = {}
        if lead["rpjson"]:
            try:
                kept = json.loads(lead["rpjson"])
            except ValueError:
                res.warnings.append(f"{cid}: stored ReviewPulse data unreadable, using the markup only")
        located = not lead["unlocated"]
        return ReviewComment(
            id=cid or f"pdf-{lead['page']}-{lead['xref']}", number=int(subject) if subject.isdigit() else kept.get("number", 0),
            text=text.strip(), subject=subject, citation=citation or kept.get("citation", ""),
            citation_doc=kept.get("citation_doc", ""), discipline=kept.get("discipline", ""), sheet=kept.get("sheet", ""),
            severity=kept.get("severity", ""), page=lead["page"] if located else None, bbox=lead["rect"] if located else None,
            located=located, state=state, evidence_quote=evidence or lead["quote"] or kept.get("evidence_quote", ""),
            source_facts={**kept.get("source_facts", {}), **facts}, cycle=kept.get("cycle", cycle),
            author=info.get("title", ""), created=_iso(info.get("creationDate", "")),
            modified=_iso(info.get("modDate", "")), color=lead["colour"], status_history=history, replies=replies,
            origin="pdf")

    for cid, group in by_id.items():
        c = build(group, cid)
        built.append(((c.page or 0, c.bbox[1] if c.bbox else 0, c.bbox[0] if c.bbox else 0), c))
    for rec in singles:
        c = build([rec], None)
        built.append(((c.page or 0, c.bbox[1] if c.bbox else 0, c.bbox[0] if c.bbox else 0), c))
    res.comments = [c for _, c in sorted(built, key=lambda t: t[0])]
    doc.close()
    return res


def render_crop(src: str | Path, page: int, bbox: list[float], *, zoom: float = 2.0, pad: float = 24.0) -> bytes:
    """PNG of the area around a box (used as the snapshot of a BCF topic)."""
    doc = pymupdf.open(str(src))
    p = doc[page - 1]
    clip = (pymupdf.Rect(*bbox) + (-pad, -pad, pad, pad)) & p.rect
    png = p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, annots=False).tobytes("png")
    doc.close()
    return png
