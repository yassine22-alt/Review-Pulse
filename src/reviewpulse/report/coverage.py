"""The compliance coverage report: for every clause of the requirement document, what was done with it and why.

Most tools report only what they checked. This report accounts for every clause, so a reader can see what the review did
NOT cover and the reason, which is as important as what it found. Each line is traceable: the clause text, the rule as a
person can read it, who approved it and what the second reader noted, the outcome on this plan, and the elements involved.

Pure functions: `build` turns the project's records into one dictionary, `render_html` turns that into a standalone page
that prints well. Nothing here runs a model.
"""

from __future__ import annotations

import html
from datetime import datetime

# outcome of an approved rule on the plan -> the label a reader sees
OUTCOME_LABEL = {
    "VIOLATED": "Violated",
    "SATISFIED": "Satisfied",
    "NOT_APPLICABLE": "Does not apply",
    "EXEMPT": "Exempt",
    "UNRESOLVED": "Could not be decided",
}
# order the report groups clauses in
STATUS_ORDER = ["violated", "undecided", "satisfied", "not_applicable", "awaiting_approval", "not_run", "rejected",
                "not_checked", "not_read"]
STATUS_LABEL = {
    "violated": "Violated",
    "satisfied": "Satisfied",
    "not_applicable": "Does not apply on this plan",
    "undecided": "Could not be decided from the plan",
    "awaiting_approval": "Rule written, waiting for a reviewer",
    "not_run": "Approved, check not run yet",
    "rejected": "Rejected by a reviewer",
    "not_checked": "Not checked: no rule could be written",
    "not_read": "Not read yet",
}
DECIDED = {"violated", "satisfied", "not_applicable"}


def _every(kinds: list[str] | None) -> str:
    """The phrase "every room, door and window" from the kinds a producer looked for; "every member" otherwise."""
    if not kinds:
        return "every member"
    kinds = [k.replace("_", " ") for k in kinds]
    return "every " + (kinds[0] if len(kinds) == 1 else ", ".join(kinds[:-1]) + " and " + kinds[-1])


def _status(entry: dict | None, result: dict | None, looked_for: str = "every member") -> tuple[str, str]:
    """(status, reason) for one clause."""
    if entry is None:
        return "not_read", "this clause has not been read yet"
    decision = (entry.get("decision") or {}).get("state")
    if decision == "rejected":
        return "rejected", (entry.get("decision") or {}).get("note") or "a reviewer rejected the rule written for it"
    if entry.get("status") != "DRAFTED":
        return "not_checked", entry.get("reason", "")
    if decision != "approved":
        return "awaiting_approval", "a rule was written and passed the automatic checks; a person must approve it"
    if result is None:
        return "not_run", "run the check to apply the approved rule to the plan"
    outcome = result["outcome"]
    if outcome == "VIOLATED":
        return "violated", ""
    if outcome == "SATISFIED":
        return "satisfied", ""
    if outcome in ("NOT_APPLICABLE", "EXEMPT"):
        return "not_applicable", "the rule's condition does not hold on this plan" if outcome == "NOT_APPLICABLE" else "an exemption applies"
    missing = ", ".join(x for x in result.get("missing", []) if not x.startswith("incomplete"))[:200]
    if "INCOMPLETE_INVENTORY" in result.get("issues", []) and not missing:
        return "undecided", (f"no violation was found among what was found, but a person has not confirmed that "
                             f"{looked_for} was found")
    return "undecided", f"missing: {missing or 'facts the plan does not provide'}"


def build(project: dict, document: dict, interpreted: dict, results: list[dict], findings: list[dict],
          looked_for: list[str] | None = None) -> dict:
    """`document`: {name, clauses:[{id, text}]}. `interpreted`: per clause. `results`: one record per approved rule and sheet."""
    by_clause: dict[str, list[dict]] = {}
    for r in results:
        by_clause.setdefault(r.get("clause"), []).append(r)
    members: dict[str, list[dict]] = {}
    for f in findings:
        ev = f.get("evidence", {})
        if ev.get("interpreted") and f["verdict"] == "FAIL":
            members.setdefault(ev.get("program_id"), []).append(
                {"element": (f["subject_ids"] or [""])[0], "message": f["message"], "detected": f.get("detected"),
                 "required": f.get("required")})
    clauses = []
    for c in document["clauses"]:
        entry = interpreted.get(c["id"])
        rows = by_clause.get(c["id"], [])
        # several sheets: the worst outcome decides the line
        result = None
        for outcome in ("VIOLATED", "UNRESOLVED", "SATISFIED", "NOT_APPLICABLE", "EXEMPT"):
            result = next((r for r in rows if r["outcome"] == outcome), None)
            if result:
                break
        status, reason = _status(entry, result, _every(looked_for))
        decision = (entry or {}).get("decision") or {}
        program = (entry or {}).get("approved_program") or (entry or {}).get("program")
        line = {"id": c["id"], "text": c["text"], "status": status, "status_label": STATUS_LABEL[status], "reason": reason,
                "rule": (entry or {}).get("readback") if entry and entry.get("status") == "DRAFTED" else None,
                "plain": (entry or {}).get("plain") if entry and entry.get("status") == "DRAFTED" else None,
                "applies_when": (entry or {}).get("applies_when"), "unless": (entry or {}).get("unless"),
                "approved_by": decision.get("by") if decision.get("state") == "approved" else None,
                "approved_at": decision.get("at") if decision.get("state") == "approved" else None,
                "reviewer_notes": decision.get("acknowledged_notes", []),
                "outcome": OUTCOME_LABEL.get(result["outcome"]) if result else None,
                "checked": result.get("checked") if result else None,
                "elements": members.get(program["id"], []) if program else []}
        if status == "awaiting_approval" and entry and entry.get("preview"):
            line["preview"] = OUTCOME_LABEL.get(entry["preview"]["outcome"], entry["preview"]["outcome"])
        clauses.append(line)
    counts = {s: sum(1 for c in clauses if c["status"] == s) for s in STATUS_ORDER}
    total = len(clauses)
    decided = sum(counts[s] for s in DECIDED)
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "project": project.get("name"), "plan": project.get("plan"), "document": document.get("name"),
        "inventory_reviewed": bool(project.get("inventory_reviewed")),
        "looked_for": _every(looked_for),
        "summary": {"clauses": total, "decided": decided, "decided_share": round(decided / total, 3) if total else 0.0,
                    "counts": counts},
        "clauses": sorted(clauses, key=lambda c: (STATUS_ORDER.index(c["status"]), c["id"])),
    }


# ---- the page ------------------------------------------------------------------------------------------------------

CSS = """
:root{--fg:#1a1d21;--muted:#5b6470;--line:#d9dde3;--bg:#fff;--soft:#f6f7f9;--fail:#b3261e;--pass:#1e7a3c;--warn:#8a5a00;--ne:#5b6470}
@media (prefers-color-scheme:dark){:root{--fg:#e8eaed;--muted:#9aa1ab;--line:#33383f;--bg:#15171a;--soft:#1d2024;--fail:#ff8a80;--pass:#6fd08c;--warn:#f0b34a;--ne:#9aa1ab}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:960px;margin:0 auto;padding:28px 20px 60px}h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
.muted{color:var(--muted)}.meta{display:flex;flex-wrap:wrap;gap:6px 22px;margin:10px 0 18px}.meta b{font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.card{border:1px solid var(--line);border-radius:10px;padding:10px 14px;background:var(--soft)}.card .n{font-size:26px;font-weight:650}
.note{border:1px solid var(--line);border-left:4px solid var(--warn);border-radius:8px;padding:10px 14px;background:var(--soft);margin:14px 0}
.clause{border:1px solid var(--line);border-radius:10px;margin:10px 0;overflow:hidden;break-inside:avoid}
.clause header{display:flex;justify-content:space-between;gap:12px;padding:10px 14px;background:var(--soft);border-bottom:1px solid var(--line)}
.id{font-weight:650}.chip{font-size:12.5px;font-weight:650;border:1px solid currentColor;border-radius:99px;padding:1px 10px;white-space:nowrap}
.s-violated{color:var(--fail)}.s-satisfied{color:var(--pass)}.s-undecided,.s-awaiting_approval,.s-not_run{color:var(--warn)}
.s-not_applicable,.s-rejected,.s-not_checked,.s-not_read{color:var(--ne)}
.body{padding:10px 14px}.body p{margin:4px 0}code{font:13px ui-monospace,Consolas,monospace;background:var(--soft);padding:1px 5px;border-radius:4px}
ul{margin:6px 0 6px 20px;padding:0}li{margin:2px 0}footer{margin-top:34px;color:var(--muted);font-size:13px}
@media print{main{padding:0}.clause{box-shadow:none}}
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def render_html(data: dict) -> str:
    s = data["summary"]
    cards = "".join(
        f'<div class="card"><div class="n">{s["counts"][k]}</div><div class="muted">{_e(STATUS_LABEL[k])}</div></div>'
        for k in STATUS_ORDER if s["counts"][k])
    note = ""
    if not data["inventory_reviewed"]:
        note = (f'<div class="note"><b>Satisfied is reported only after a person confirms that {_e(data["looked_for"])} '
                "was found.</b> Until then a rule over every member can show a violation but never a pass, because "
                "something that was missed could hide a problem.</div>")
    parts = []
    for c in data["clauses"]:
        lines = [f'<p>{_e(c["text"])}</p>']
        if c.get("plain"):
            lines.append(f'<p><b>Rule, in words:</b> {_e(c["plain"])}</p>')
        if c["rule"]:
            lines.append(f'<p class="muted">Exact form: <code>{_e(c["rule"])}</code>'
                         + (f' &middot; applies when <code>{_e(c["applies_when"])}</code>' if c["applies_when"] not in (None, "true") else "")
                         + (f' &middot; unless <code>{_e(c["unless"])}</code>' if c["unless"] not in (None, "false") else "") + "</p>")
        if c["approved_by"]:
            lines.append(f'<p class="muted">Approved by <b>{_e(c["approved_by"])}</b> on {_e(c["approved_at"])}.</p>')
        for n in c["reviewer_notes"]:
            lines.append(f'<p class="muted">Second reader noted, and the reviewer approved anyway: {_e(n)}</p>')
        if c["outcome"]:
            checked = f' ({c["checked"]} checked)' if c["checked"] else ""
            lines.append(f'<p><b>On this plan:</b> {_e(c["outcome"])}{checked}</p>')
        if c.get("preview"):
            lines.append(f'<p class="muted">Preview, not approved: {_e(c["preview"])}</p>')
        if c["elements"]:
            lines.append("<ul>" + "".join(f"<li>{_e(m['message'])}</li>" for m in c["elements"]) + "</ul>")
        if c["reason"]:
            lines.append(f'<p class="muted">{_e(c["reason"])}</p>')
        parts.append(f'<section class="clause"><header><span class="id">{_e(c["id"])}</span>'
                     f'<span class="chip s-{c["status"]}">{_e(c["status_label"])}</span></header>'
                     f'<div class="body">{"".join(lines)}</div></section>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Compliance coverage report</title><style>{CSS}</style></head><body><main>
<h1>Compliance coverage report</h1>
<div class="muted">Every clause of the requirement document, what was done with it, and why.</div>
<div class="meta"><span>Project <b>{_e(data["project"])}</b></span><span>Plan <b>{_e(data["plan"])}</b></span>
<span>Document <b>{_e(data["document"])}</b></span><span>Generated <b>{_e(data["generated"])}</b></span></div>
<p><b>{s["decided"]}</b> of <b>{s["clauses"]}</b> clauses were decided on this plan ({round(100 * s["decided_share"])}%). The others are listed below with the reason.</p>
<div class="cards">{cards}</div>{note}
<h2>Clauses</h2>{"".join(parts)}
<footer>A rule counts only after a named reviewer approves it. A clause that could not be decided is never counted as a pass.</footer>
</main></body></html>"""
