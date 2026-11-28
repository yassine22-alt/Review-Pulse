"""The correction list: what a plan reviewer actually delivers.

The findings of a project become a numbered list grouped by discipline, then by code chapter. Each item quotes the
requirement as the clause words it (nothing is paraphrased, no model is called), shows the citation in brackets as the
source document gives it, says on which sheet and where the evidence is, lists the facts used with their source, gives the
state in the reviewer's words, and, for an item that could not be decided, the one question that settles it.

Pure functions: ``build`` turns records into one dictionary, ``render_html`` / ``render_text`` / ``to_json`` write it,
``write_markup_pdf`` copies the submitted PDF and adds standard annotations that open in Bluebeam Revu.
"""

from __future__ import annotations

import difflib
import html
import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import disciplines as disc
from . import reviewer_states as rs

CITATION = re.compile(r"\[([^\[\]\n]{2,60})\]")
MAX_LOCATIONS = 6
MAX_FACTS = 6
QUADRANT = {(0, 0): "lower left", (1, 0): "lower right", (0, 1): "upper left", (1, 1): "upper right"}


def _norm(text: str | None) -> str:
    return " ".join((text or "").split())


def citation_of(clause_id: str, clause_text: str) -> str:
    """The citation in brackets as the source document gives it ('[CRC R311.6]'); the clause number when it gives none."""
    found = CITATION.findall(clause_text or "")
    if found:
        return f"[{found[-1].strip()}]"
    return f"[{clause_id}]" if clause_id else ""


PRIVATE_USE = re.compile(f"[{chr(0xE000)}-{chr(0xF8FF)}]")      # a symbol font's bullets and tick boxes


def _from_elsewhere(source: dict, document: dict) -> bool:
    """A finding whose rule names a source document other than the one uploaded here. Its words must not be shown as quoted."""
    named, uploaded = str(source.get("doc") or ""), str(document.get("name") or "")
    return bool(named and uploaded) and Path(named).name != Path(uploaded).name


def _quote(clause_id: str, clause_text: str, interpreted: dict) -> str:
    """The words of the requirement: the sentence the rule cites when there is one, else the clause, without its citation."""
    program = (interpreted.get(clause_id) or {}).get("approved_program") or (interpreted.get(clause_id) or {}).get("program") or {}
    quote = _norm(next((s.get("quote") for s in program.get("sources", []) if s.get("quote")), ""))
    text = quote if quote and quote in _norm(clause_text) else _norm(clause_text)
    return _norm(CITATION.sub("", PRIVATE_USE.sub(" ", text))).rstrip()


def _bbox(evidence: dict) -> list[float] | None:
    pts: list = []
    for poly in evidence.get("polygons", []) or []:
        pts += [tuple(p) for p in poly]
    for pl in evidence.get("polylines", []) or []:
        pts += [tuple(p) for p in pl]
    pts += [tuple(p) for p in evidence.get("points", []) or [] if p]
    pts += [tuple(lab["at"]) for lab in evidence.get("labels", []) or [] if lab.get("at")]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]


def _place(bbox: list[float] | None, sheet: dict | None) -> str:
    """Where on the sheet, in words: which quarter. Sheet y grows upward."""
    if not bbox or not sheet or not sheet.get("width") or not sheet.get("height"):
        return ""
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return QUADRANT[(int(cx > sheet["width"] / 2), int(cy > sheet["height"] / 2))]


def _subject_name(message: str, title: str) -> str:
    rest = message[len(title) + 2:] if title and message.startswith(title + ": ") else message
    parts = rest.split(": ")
    return parts[0] if len(parts) >= 2 else ""


def _severity_key(verdict: str) -> tuple[int, int]:
    verdicts = list(rs.config()["verdicts"])
    return rs.rank(rs.rollup(rs.status_of_verdict(verdict))), -verdicts.index(verdict) if verdict in verdicts else 0


SEVERITIES = ("critical", "major", "minor", "info")


def _severity_of(findings: list[dict]) -> str:
    """The most severe rating among the findings behind one item; empty when none is rated."""
    rated = [f["severity"] for f in findings if f.get("severity") in SEVERITIES]
    return min(rated, key=SEVERITIES.index) if rated else ""


def _family(from_document: bool, findings: list[dict]) -> str:
    """Where the rule behind an item comes from: the reviewer's document, or a family of the built-in rules."""
    if from_document:
        return "document"
    found = re.match(r"([CKPQ])-", str(findings[0].get("rule_id", ""))) if findings else None
    return found.group(1) if found else "other"


def _location(finding: dict, sheets: dict[str, dict]) -> dict | None:
    ev = finding.get("evidence", {})
    sid = ev.get("sheet")
    sheet = sheets.get(sid) if sid is not None else None
    box = _bbox(ev)
    if sid is None and box is None:
        return None
    name = _subject_name(finding.get("message", ""), (ev.get("title") or ""))
    where = _place(box, sheet)
    text = f"sheet {sid}" if sid is not None else "the drawings"
    if where:
        text += f", {where} of the sheet"
    if name:
        text += f", at {name}"
    return {"sheet": sid, "page": (sheet["page"] + 1) if sheet and sheet.get("page") is not None else None, "bbox": box,
            "where": text, "subjects": finding.get("subject_ids", [])[:6], "note": None}


def _question(findings: list[dict]) -> str:
    for f in findings:
        for a in f.get("evidence", {}).get("unsettled", []) or []:
            if a.get("question"):
                return a["question"]                          # the ledger's follow up request, as a sentence
    for f in findings:
        if f.get("evidence", {}).get("advisory"):
            return "Does this requirement apply to this building? If it does, on which sheet do the plans show it?"
    for f in findings:
        found = re.search(r"list of (.{2,40}?) is complete", f.get("message", ""))
        if found:
            return f"Confirm that every one of the {found.group(1)} on the plan was found: no person has checked the list yet."
    for f in findings:
        names = []
        for m in f.get("evidence", {}).get("missing", []) or []:
            if not str(m).startswith("incomplete"):
                name = str(m).split(".")[-1].split(" (")[0].replace("_", " ").strip()
                if name and name not in names:
                    names.append(name)
        if names:
            return "What do the plans state for " + ", ".join(names[:2]) + "? Show it on a sheet, or answer with a source and your name."
    return "Which sheet shows this, and what does it state?"


def _facts(findings: list[dict], sheets: dict[str, dict]) -> list[dict]:
    out = []
    measured: set[tuple] = set()
    for f in findings:
        ev = f.get("evidence", {})
        sheet = sheets.get(ev.get("sheet")) or {}
        title = ev.get("title") or ""
        name = _subject_name(f.get("message", ""), title)
        said = f.get("message", "")
        said = said[len(title) + 2:] if title and said.startswith(title + ": ") else said
        if f["verdict"] == "FAIL" and (f.get("detected") or f.get("required")):
            who = (ev.get("sheet"), tuple(sorted(f.get("subject_ids", []))))
            if f.get("subject_ids") and who in measured:          # two rules read the same element: one fact
                continue
            measured.add(who)
            scale = sheet.get("scale_method")
            out.append({"subject": name, "statement": f"detected {f.get('detected') or 'not stated'}, required {f.get('required') or 'not stated'}",
                        "source": f"measured on sheet {ev.get('sheet')}" + (f", scale from {scale}" if scale else "") + f", reading tier {f.get('tier')}"})
        for a in ev.get("unsettled", []) or []:
            out.append({"subject": a.get("entity", name), "statement": a.get("explain", ""), "source": "evidence ledger, sources named in the statement"})
        if not out or (f["verdict"] != "FAIL" and not ev.get("unsettled")):
            out.append({"subject": name, "statement": said, "source": "rule result on this plan"})
    seen, unique = set(), []
    for fact in out:
        key = (fact["subject"], fact["statement"])
        if key not in seen:
            seen.add(key)
            unique.append(fact)
    return unique[:MAX_FACTS]


def _wording(status: str, quote: str, citation: str, facts: list[dict], question: str, located: bool) -> str:
    t = rs.config()["templates"]
    line = t["revision_required" if status == "revision_required" else "information_requested"].format(quote=quote, citation=citation).strip()
    if status == "revision_required":
        for fact in facts[:3]:
            if fact["statement"].startswith("detected"):
                said = fact["statement"].replace(">=", "at least").replace("<=", "at most")      # words, for the applicant
                line += f" {fact['subject']}: {said}." if fact["subject"] else f" {said.capitalize()}."
    else:
        line += f" {t['question_prefix']} {question}"
        if not located:
            line += f" {t['not_shown']}"
    return _norm(line)


def build(project: dict, findings: list[dict], document: dict, interpreted: dict, sheets: list[dict],
          states: dict | None = None, edits: dict | None = None, signoffs: list[dict] | None = None,
          uncovered: int = 0, cycle: int = 1, locate_note: Callable[[str, str], list[float] | None] | None = None) -> dict:
    """One dictionary with everything an export needs. ``findings``: findings.json dicts. ``document``: {name, clauses:[{id, text,
    scope}]}. ``sheets``: [{id, page, width, height, scale_method, discipline}]. ``states``: what reviewers decided per clause {clause:
    {state, by, at, note, evidence}}; a decision replaces the tool's result for that clause. ``edits``: {item key: {action, wording, by, at}}. ``signoffs``: [{reviewer, cycle, discipline, result, note, at}]."""
    states, edits, signoffs = states or {}, edits or {}, signoffs or []
    sheet_by_id = {s["id"]: s for s in sheets}
    clauses = {c["id"]: (i, c) for i, c in enumerate(document.get("clauses", []))}
    scopes = {c.get("scope", "") for _, c in clauses.values() if c.get("scope")}
    use_scope = len(scopes) >= 2                           # one heading above everything (the document's title) groups nothing
    groups: dict[str, list[dict]] = {}
    foreign: set[str] = set()        # groups of rules that do not come from the uploaded document (a built in pack)
    for f in findings:
        source = f.get("source") or {}
        clause_id = source.get("clause") or ""
        if _from_elsewhere(source, document):          # its clause numbers are another document's: never matched to this one
            key = f["rule_id"]
            foreign.add(key)
        else:
            key = clause_id if clause_id and (clause_id in clauses or len(clause_id) <= 40) else f["rule_id"]
        groups.setdefault(key, []).append(f)

    records, dismissed = [], []
    for clause_id, group in groups.items():
        live = [f for f in group if not f.get("evidence", {}).get("dismissed")]
        if not live:
            dismissed.append({"key": clause_id, "reasons": sorted({str(f["evidence"]["dismissed"]) for f in group})})
            continue
        rule_id = clause_id
        own = clause_id not in foreign
        order, clause = clauses.get(clause_id, (len(clauses) + 1, {})) if own else (len(clauses) + 1, {})
        title0 = next((f["evidence"].get("title") for f in live if f.get("evidence", {}).get("title")), "") or ""
        text = clause.get("text") or title0 or live[0].get("message", "")
        if not own:
            text = title0 or clause_id
        quote = _quote(clause_id, text, interpreted) if own else _norm(text)
        worst = max(live, key=lambda f: _severity_key(f["verdict"]))["verdict"]
        status = rs.status_of_verdict(worst)
        title = next((f["evidence"].get("title") for f in live if f.get("evidence", {}).get("title")), "") or ""
        shown = [f for f in live if f["verdict"] == worst] if status != "approved" else live
        discipline = disc.discipline_of(f"{title} {text}")
        chapter_key, chapter_label = disc.chapter_of(clause_id, clause.get("scope", "") if use_scope else "")
        records.append({"key": rule_id, "clause": clause_id, "status": status, "findings": shown, "order": order,
                        "from_document": own, "text": text, "quote": quote,
                        "citation": citation_of(clause_id, text) if own else f"[built-in rule {clause_id}]", "title": title,
                        "discipline": discipline, "chapter": chapter_key, "chapter_label": chapter_label,
                        "doc": (shown[0].get("source") or {}).get("doc")})

    cover = {"deferred": [], "not_applicable": []}
    open_records = []
    tool_said: dict[str, str] = {}      # what the tool had concluded on clauses a person then decided
    for r in records:
        st = states.get(r["clause"]) or states.get(r["key"])
        if st and st.get("state") in ("shown", "correction"):
            if r["from_document"]:
                tool_said[r["clause"]] = r["status"]
                continue
        if st and st.get("state") in ("deferred", "not_applicable"):
            c = clauses.get(r["clause"], (0, {}))[1]
            cover[st["state"]].append({"clause": r["clause"], "citation": r["citation"], "quote": r["quote"],
                                       "discipline": r["discipline"], "by": st.get("by"), "at": st.get("at"), "note": st.get("note", ""),
                                       "scope": c.get("scope", "")})
        else:
            open_records.append(r)
    covered = {x["clause"] for k in cover.values() for x in k}
    for clause_id, st in states.items():                                # a clause set by hand that produced no finding
        if st.get("state") in cover and clause_id not in covered and clause_id in clauses:
            c = clauses[clause_id][1]
            quote = _quote(clause_id, c["text"], interpreted)
            cover[st["state"]].append({"clause": clause_id, "citation": citation_of(clause_id, c["text"]), "quote": quote,
                                       "discipline": disc.discipline_of(c["text"]), "by": st.get("by"), "at": st.get("at"),
                                       "note": st.get("note", ""), "scope": c.get("scope", "")})

    items = []
    for r in open_records:
        if r["status"] == "approved":
            continue
        facts = _facts(r["findings"], sheet_by_id)
        question = _question(r["findings"]) if r["status"] == "information_requested" else ""
        locations: list[dict] = []
        for f in r["findings"]:
            loc = _location(f, sheet_by_id)
            if loc and not any(o["sheet"] == loc["sheet"] and o["bbox"] == loc["bbox"] for o in locations):
                locations.append(loc)
        entry = interpreted.get(r["clause"]) or {}
        chosen = (entry.get("evidence") or {}).get("chosen") or {}
        if chosen.get("text") and chosen.get("sheet") is not None:
            sid = chosen["sheet"]
            box = chosen.get("box") or (locate_note(sid, chosen["text"]) if locate_note else None)    # older readings: no box
            sheet = sheet_by_id.get(sid)
            locations.append({"sheet": sid, "page": (sheet["page"] + 1) if sheet else None, "bbox": box,
                              "where": f"sheet {sid}" + (f", {_place(box, sheet)} of the sheet" if box else "") + ", note: " + _norm(chosen["text"])[:140],
                              "subjects": [], "note": _norm(chosen["text"])[:300]})
        more = max(0, len(locations) - MAX_LOCATIONS)
        located = bool(locations)
        default = _wording(r["status"], r["quote"], r["citation"], facts, question, located)
        items.append({"key": r["key"], "clause": r["clause"], "citation": r["citation"], "quote": r["quote"], "title": r["title"],
                      "discipline": r["discipline"], "discipline_label": disc.label(r["discipline"]),
                      "chapter": r["chapter"], "chapter_label": r["chapter_label"],
                      "status": r["status"], "status_label": rs.label(r["status"]),
                      "outcome": "Violated" if r["status"] == "revision_required" else "Could not be decided",
                      "verdicts": sorted({f["verdict"] for f in r["findings"]}),
                      "wording_default": default, "question": question, "facts": facts,
                      "locations": locations[:MAX_LOCATIONS], "more_locations": more,
                      "from_document": r["from_document"], "severity": _severity_of(r["findings"]),
                      "family": _family(r["from_document"], r["findings"]),
                      "finding_ids": [f["evidence"]["finding_id"] for f in r["findings"] if f.get("evidence", {}).get("finding_id")],
                      "count": len(r["findings"]), "_order": r["order"]})

    shown_by_hand: list[dict] = []
    for clause_id, st in states.items():
        if st.get("state") not in ("shown", "correction") or clause_id not in clauses:
            continue
        order, clause = clauses[clause_id]
        quote = _quote(clause_id, clause["text"], interpreted)
        citation = citation_of(clause_id, clause["text"])
        discipline = disc.discipline_of(clause["text"])
        chapter_key, chapter_label = disc.chapter_of(clause_id, clause.get("scope", "") if use_scope else "")
        place = st.get("evidence") or {}
        sid = place.get("sheet")
        sheet = sheet_by_id.get(sid)
        overrode = tool_said.get(clause_id)
        if st["state"] == "shown":
            shown_by_hand.append({"clause": clause_id, "citation": citation, "quote": quote, "discipline": discipline, "by": st.get("by"),
                                  "at": st.get("at"), "note": st.get("note", ""), "evidence": place or None,
                                  "overrode": rs.label(overrode) if overrode and overrode != "approved" else None})
            continue
        locations = []
        if sid is not None:
            where = f"sheet {sid}" + (f", {_place(place.get('box'), sheet)} of the sheet" if place.get("box") and sheet else "")
            locations.append({"sheet": sid, "page": (sheet["page"] + 1) if sheet else None, "bbox": place.get("box"),
                              "where": where, "subjects": [], "note": place.get("text") or None})
        comment = _norm(st.get("note", ""))
        wording = rs.config()["templates"]["reviewer_correction"].format(
            comment=comment if comment.endswith((".", "?", "!")) else comment + ".", quote=quote, citation=citation)
        facts = [{"subject": "", "statement": place["text"], "source": f"pointed at by {st.get('by')}"}] if place.get("text") else []
        items.append({"key": clause_id, "clause": clause_id, "citation": citation, "quote": quote, "title": "",
                      "discipline": discipline, "discipline_label": disc.label(discipline), "chapter": chapter_key,
                      "chapter_label": chapter_label, "status": "revision_required", "status_label": rs.label("revision_required"),
                      "outcome": "Found by the reviewer", "verdicts": [], "wording_default": _norm(wording), "question": "",
                      "facts": facts, "locations": locations, "more_locations": 0, "from_document": True, "finding_ids": [],
                      "severity": "", "family": "reviewer",
                      "decided_by": st.get("by"), "overrode": rs.label(overrode) if overrode else None, "count": 1, "_order": order})

    d_order = disc.order()
    first: dict[tuple, int] = {}
    for it in items:
        k = (it["discipline"], it["chapter"])
        first[k] = min(first.get(k, it["_order"]), it["_order"])
    items.sort(key=lambda i: (d_order.index(i["discipline"]) if i["discipline"] in d_order else len(d_order),
                              first[(i["discipline"], i["chapter"])], i["chapter"], i["_order"], i["key"]))
    n = 0
    for it in items:
        e = edits.get(it["key"]) or {}
        if not e and it.get("decided_by"):          # the reviewer wrote it: it already has their decision
            e = {"action": "accept", "by": it["decided_by"], "at": states[it["clause"]].get("at")}
        action = e.get("action", "pending")
        it["review"] = {"action": action, "by": e.get("by"), "at": e.get("at"),
                        **({"reason": e.get("reason", "")} if action == "drop" else {})}
        it["wording"] = _norm(e["wording"]) if action == "edit" and e.get("wording") else it["wording_default"]
        it["dropped"] = action == "drop"
        if it["dropped"]:
            it["n"] = None
        else:
            n += 1
            it["n"] = n
        it.pop("_order")

    live_items = [i for i in items if not i["dropped"]]
    approved = [r for r in open_records if r["status"] == "approved"] + shown_by_hand
    by_disc: dict[str, dict] = {}
    for did in {i["discipline"] for i in live_items} | {r["discipline"] for r in approved}:
        stat_ids = [i["status"] for i in live_items if i["discipline"] == did] + ["approved" for r in approved if r["discipline"] == did]
        by_disc[did] = {"label": disc.label(did), "items": sum(i["discipline"] == did for i in live_items),
                        "proposed": rs.overall(stat_ids, reviewed=len(stat_ids))["result"]}
    for did in {x["discipline"] for k in cover.values() for x in k} - set(by_disc):
        by_disc[did] = {"label": disc.label(did), "items": 0, "proposed": rs.overall(["deferred"], reviewed=1)["result"]}
    all_status = [i["status"] for i in live_items] + ["approved"] * len(approved) \
        + ["deferred"] * len(cover["deferred"]) + ["not_applicable"] * len(cover["not_applicable"])
    overall = rs.overall(all_status, uncovered=uncovered, reviewed=len(all_status))

    latest: dict[str, dict] = {}
    for s in signoffs:
        if s.get("cycle") == cycle:
            latest[s["discipline"]] = s                          # a later sign off replaces an earlier one; the audit trail keeps both
    for did, d in by_disc.items():
        s = latest.get(did)
        d["signed"] = {"reviewer": s["reviewer"], "result": s["result"], "at": s["at"], "note": s.get("note", "")} if s else None
        d["differs"] = bool(s and s["result"] != d["proposed"])
    unsigned = sorted(did for did, d in by_disc.items() if d["signed"] is None)
    signed_results = [d["signed"]["result"] for d in by_disc.values() if d["signed"]]
    final = rs.most_severe(signed_results) if by_disc and not unsigned else None

    proposed = [i for i in items if not i.get("decided_by")]           # the edit burden is about what the tool proposed
    edited = [i for i in proposed if i["review"]["action"] == "edit"]
    distance = [1 - difflib.SequenceMatcher(None, i["wording_default"], i["wording"]).ratio() for i in edited]
    burden = {"items": len(proposed), "accepted": sum(i["review"]["action"] == "accept" for i in proposed), "edited": len(edited),
              "dropped": sum(i["dropped"] for i in proposed), "unreviewed": sum(i["review"]["action"] == "pending" for i in proposed),
              "written_by_reviewer": len(items) - len(proposed)}
    burden["edit_count"] = burden["edited"] + burden["dropped"]
    burden["edit_share"] = round(burden["edit_count"] / len(proposed), 3) if proposed else 0.0
    burden["mean_text_change"] = round(sum(distance) / len(distance), 3) if distance else 0.0

    return {"generated": datetime.now().isoformat(timespec="seconds"), "project": project.get("name"), "plan": project.get("plan"),
            "occupancy": project.get("occupancy") or "", "location": project.get("location") or "",
            "document": document.get("name"), "cycle": cycle,
            "overall": {**overall, "signed": final, "unsigned_disciplines": [disc.label(d) for d in unsigned]},
            "disciplines": by_disc, "items": items, "deferred": cover["deferred"], "not_applicable": cover["not_applicable"],
            "dismissed": dismissed, "approved_count": len(approved), "uncovered_clauses": uncovered, "shown": shown_by_hand,
            "edit_burden": burden, "signoffs": list(latest.values())}


def included(cl: dict) -> list[dict]:
    return [i for i in cl["items"] if not i["dropped"]]


def grouped(cl: dict) -> list[tuple[str, str, list[tuple[str, list[dict]]]]]:
    """[(discipline id, label, [(chapter label, items)])] in list order, dropped items left out."""
    out: list = []
    for it in included(cl):
        if not out or out[-1][0] != it["discipline"]:
            out.append((it["discipline"], it["discipline_label"], []))
        chapters = out[-1][2]
        if not chapters or chapters[-1][0] != it["chapter_label"]:
            chapters.append((it["chapter_label"], []))
        chapters[-1][1].append(it)
    return out


def to_json(cl: dict) -> str:
    return json.dumps(cl, indent=1, ensure_ascii=False)


def _where(it: dict) -> list[str]:
    lines = [loc["where"] for loc in it["locations"]]
    if it["more_locations"]:
        lines.append(f"and {it['more_locations']} more place(s)")
    return lines or ["not shown on any sheet"]


def render_text(cl: dict) -> str:
    about = [f"{label}: {cl[key]}" for label, key in (("Building use", "occupancy"), ("Location", "location")) if cl.get(key)]
    out = [f"CORRECTION LIST, cycle {cl['cycle']}", f"Project: {cl['project']}    Plan: {cl['plan']}    Requirements: {cl['document']}",
           *(["    ".join(about)] if about else []), f"Proposed result: {cl['overall']['label']} ({cl['overall']['reason']})", ""]
    if cl["deferred"]:
        out.append("DEFERRED SUBMITTALS (neither missing nor failing; review them when submitted)")
        out += [f"  - {d['quote']} {d['citation']} (set by {d['by']})" for d in cl["deferred"]] + [""]
    for _did, label, chapters in grouped(cl):
        out += [label.upper(), "=" * len(label)]
        for chapter, items in chapters:
            out += ["", chapter]
            for it in items:
                out += [f"{it['n']}. {it['wording']}", "     Where: " + "; ".join(_where(it)),
                        f"     State: {it['status_label']} ({it['outcome']})"]
                for fact in it["facts"][:3]:
                    out.append(f"     Fact: {fact['subject'] + ': ' if fact['subject'] else ''}{fact['statement']} [source: {fact['source']}]")
        out.append("")
    if not included(cl):
        out.append("No corrections.")
    return "\n".join(out).rstrip() + "\n"


CSS = """
:root{--fg:#1a1d21;--muted:#5b6470;--line:#d9dde3;--bg:#fff;--soft:#f6f7f9;--fail:#b3261e;--warn:#8a5a00}
@media (prefers-color-scheme:dark){:root{--fg:#e8eaed;--muted:#9aa1ab;--line:#33383f;--bg:#15171a;--soft:#1d2024;--fail:#ff8a80;--warn:#f0b34a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:900px;margin:0 auto;padding:28px 20px 60px}h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:30px 0 4px;border-bottom:2px solid var(--line)}
h3{font-size:14px;margin:18px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}.muted{color:var(--muted)}
.meta{display:flex;flex-wrap:wrap;gap:6px 22px;margin:10px 0 14px}ol{padding-left:0;list-style:none}
li.item{border:1px solid var(--line);border-radius:10px;margin:10px 0;padding:10px 14px;break-inside:avoid}
li.item .n{font-weight:700;margin-right:6px}.chip{font-size:12.5px;font-weight:650;border:1px solid currentColor;border-radius:99px;padding:1px 10px;white-space:nowrap}
.s-revision_required{color:var(--fail)}.s-information_requested{color:var(--warn)}.det{font-size:13.5px;color:var(--muted);margin:3px 0}
.cover{border:1px solid var(--line);border-left:4px solid var(--warn);border-radius:8px;padding:8px 14px;background:var(--soft)}
@media print{main{padding:0}}
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def render_html(cl: dict) -> str:
    parts = []
    for _did, label, chapters in grouped(cl):
        parts.append(f"<h2>{_e(label)}</h2>")
        for chapter, items in chapters:
            parts.append(f"<h3>{_e(chapter)}</h3><ol>")
            for it in items:
                facts = "".join(f'<div class="det">Fact: {_e(f["subject"] + ": " if f["subject"] else "")}{_e(f["statement"])} '
                                f'<span class="muted">(source: {_e(f["source"])})</span></div>' for f in it["facts"][:4])
                question = ""
                parts.append(
                    f'<li class="item"><span class="n">{it["n"]}.</span><span class="chip s-{it["status"]}">{_e(it["status_label"])}</span>'
                    f'<p>{_e(it["wording"])}</p><div class="det">Where: {_e("; ".join(_where(it)))}</div>{facts}{question}</li>')
            parts.append("</ol>")
    deferred = ""
    if cl["deferred"]:
        deferred = '<div class="cover"><b>Deferred submittals</b> (neither missing nor failing; listed here and reviewed when submitted)<ul>' + "".join(
            f'<li>{_e(d["quote"])} {_e(d["citation"])} <span class="muted">set by {_e(d["by"])}</span></li>' for d in cl["deferred"]) + "</ul></div>"
    sign = "".join(f'<li>{_e(d["label"])}: proposed {_e(d["proposed"])}'
                   + (f', signed {_e(d["signed"]["result"])} by {_e(d["signed"]["reviewer"])}' if d["signed"] else ", not signed") + "</li>"
                   for d in cl["disciplines"].values())
    body = "".join(parts) or "<p>No corrections.</p>"
    about = "".join(f"<span>{label} <b>{_e(cl[key])}</b></span>"
                    for label, key in (("Building use", "occupancy"), ("Location", "location")) if cl.get(key))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Correction list</title><style>{CSS}</style></head><body><main>
<h1>Correction list, cycle {cl["cycle"]}</h1>
<div class="meta"><span>Project <b>{_e(cl["project"])}</b></span><span>Plan <b>{_e(cl["plan"])}</b></span>
<span>Requirements <b>{_e(cl["document"])}</b></span>{about}<span>Generated <b>{_e(cl["generated"])}</b></span></div>
<p>Proposed result: <b>{_e(cl["overall"]["label"])}</b> <span class="muted">({_e(cl["overall"]["reason"])})</span></p><ul>{sign}</ul>{deferred}
{body}
<p class="muted">A requirement that could not be decided is listed as information requested, never as approved. The reviewer owns every item.</p>
</main></body></html>"""


# ---- the exchange model and the marked up PDF ---------------------------------------------------------------------------
# One neutral shape (connectors.model.ReviewComment) feeds every output: PDF annotations, BCF, CSV and JSON. This module only
# turns the correction list into that shape; the connectors package writes the files.

MM = 25.4 / 72
STATE_OF_STATUS = {"revision_required": "open", "information_requested": "information_requested"}


def _sheet_pages(models: list, source_pdf: Path | None, work: Path) -> tuple[Path, dict[str, tuple[int, Callable]]]:
    """The PDF the markup is written on and, per sheet id, (page number from 0, sheet space -> unrotated page points).
    A PDF submission is used as it is; any other source is redrawn as vector pages first."""
    import pymupdf

    from .pdf_overlay import _page_for

    src = source_pdf or (Path(models[0].sheet.source_file) if models else None)
    pages: dict[str, tuple[int, Callable]] = {}
    if src is not None and src.suffix.lower() == ".pdf" and src.exists():
        doc = pymupdf.open(src)
        for m in models:
            if 0 <= m.sheet.page < len(doc):
                page = doc[m.sheet.page]
                height, der = page.rect.height, page.derotation_matrix
                pages[m.sheet.id] = (m.sheet.page, lambda pt, height=height, der=der: pymupdf.Point(pt[0] / MM, height - pt[1] / MM) * der)
        doc.close()
        return src, pages
    doc = pymupdf.open()
    for m in models:
        page, to_page = _page_for(doc, m)
        pages[m.sheet.id] = (page.number, to_page)
    if not len(doc):
        doc.new_page()
    base = work / "base.pdf"
    doc.save(base)
    doc.close()
    return base, pages


def to_comments(cl: dict, pages: dict[str, tuple[int, Callable]] | None = None, author: str = "") -> list:
    """The included items as ``ReviewComment`` objects. ``pages``: sheet id -> (page from 0, to_page) places a box on its page;
    without it the comments carry the sheet and no box (CSV, JSON and an unplaced PDF note)."""
    from ..connectors.model import ReviewComment, stable_id

    out = []
    for it in included(cl):
        page_no, box = None, None
        for loc in it["locations"]:
            target = (pages or {}).get(loc["sheet"]) if loc["sheet"] is not None else None
            if target is not None:
                page_no = target[0] + 1
                if loc["bbox"]:
                    x0, y0, x1, y1 = loc["bbox"]
                    a, b = target[1]((x0, y0)), target[1]((x1, y1))
                    box = [round(min(a.x, b.x) - 4, 2), round(min(a.y, b.y) - 4, 2), round(max(a.x, b.x) + 4, 2), round(max(a.y, b.y) + 4, 2)]
                    break
        cite = it["citation"].strip("[]")
        sheet = next((loc["sheet"] for loc in it["locations"] if loc["sheet"] is not None), "")
        text = it["wording"].replace(it["citation"], "", 1).replace("  ", " ").strip() if it["citation"] else it["wording"]
        facts = {}
        for fact in it["facts"][:1]:
            if fact["statement"].startswith("detected"):
                m = re.match(r"detected (.*?), required (.*)$", fact["statement"])
                if m:
                    facts = {"detected": m.group(1), "required": m.group(2)}
        out.append(ReviewComment(
            id=stable_id("correction", it["key"]), number=it["n"], discipline=it["discipline_label"], citation=cite,
            citation_doc=cl.get("document") or "", text=text, sheet=str(sheet), page=page_no, bbox=box,
            located=box is not None, state=STATE_OF_STATUS.get(it["status"], "open"), severity="major",
            evidence_quote=it["quote"], source_facts=facts, cycle=cl["cycle"],
            author=it["review"].get("by") or author or "ReviewPulse"))
    return out


def write_markup_pdf(cl: dict, models: list, out: Path, source_pdf: Path | None = None) -> dict:
    """A copy of the submitted PDF with the connectors package's standard annotations (cloud, callout, note) per item, the item
    number in Subject. An item with no place gets a note at the top left of its sheet's page. Returns counts."""
    import tempfile

    from ..connectors.pdf_io import write_annotations

    with tempfile.TemporaryDirectory() as work:
        base, pages = _sheet_pages(models, source_pdf, Path(work))
        comments = to_comments(cl, pages)
        res = write_annotations(base, out, comments)
    return {"items": len(comments), "annotations": res.written, "fallback": res.unlocated, "warnings": res.warnings}


def export(cl: dict, fmt: str, out_dir: Path, models: list | None = None, source_pdf: Path | None = None) -> Path:
    """Write the list as ``pdf``, ``bcf``, ``json`` or ``csv`` into ``out_dir`` and return the file."""
    from ..connectors import filedrop
    from ..connectors.bcf import export_bcf
    from ..connectors.pdf_io import render_crop

    out_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "pdf":
        path = out_dir / "correction_markup.pdf"
        write_markup_pdf(cl, models or [], path, source_pdf)
        return path
    import tempfile

    with tempfile.TemporaryDirectory() as work:
        pages = None
        base = None
        if models:
            base, pages = _sheet_pages(models, source_pdf, Path(work))
        comments = to_comments(cl, pages)
        if fmt == "json":
            return filedrop.write_json(comments, out_dir / "correction_list.comments.json")
        if fmt == "csv":
            return filedrop.write_csv(comments, out_dir / "correction_list.csv")
        if fmt == "bcf":
            snaps = {}
            if base is not None:
                for c in comments:
                    if c.located:
                        snaps[c.id] = render_crop(base, c.page, c.bbox)
            return export_bcf(comments, out_dir / "correction_list.bcf", project_name=cl.get("project") or "ReviewPulse",
                              pdf_name=cl.get("plan") or "", snapshots=snaps)
    raise ValueError(f"unknown export format {fmt!r}")
