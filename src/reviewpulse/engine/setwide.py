"""What one sheet cannot show about a whole building.

The rules run sheet by sheet. When a set has several plan sheets, each shows only a part: another floor, an enlarged room, the
electrical layout of the same floor. So the findings are read as an open world: **something not found on one sheet is not
something the building lacks**, while something found stays found.

    * A count that must reach a minimum: if any sheet reaches it, the building does (sheets can only add; they are not summed,
      because two sheets may draw the same door). If no sheet does, there is one result for the whole set, undecided, that says
      which sheets were read.
    * A route out, or separate routes, for a room: on a sheet a route can leave (it shows no exit to the outside, or it shows a
      way to another level) a route not found may continue on another sheet, so it is undecided. A sheet with its own exit and
      no way to another level holds all its routes: a violation there stays one (two separate buildings in one file).
    * A limit that must not be exceeded, and a forbidden thing that was found, are decided by the sheet that shows them.

Which rules depend on the whole building is declared on the function in ``rules/registry.py``, not guessed from the findings."""

from __future__ import annotations

import re

from ..outcomes import EvidenceIssue, IssueCode
from ..rules.registry import REGISTRY
from ..rules.schema import Rule
from ..schema import BuildingModel, Finding
from .policy import compare

LOWER = (">=", ">", "==")
ROUTE_REASON = "the route may continue on another sheet of the set, and sheets are read one at a time"


# marks a drawing puts at a stair that goes to another level, and words that name a stair, in the languages of the lexicons
LEVEL_MARKS = {"up", "dn", "down", "monte", "montee", "montée", "desc", "descente", "auf", "ab", "sube", "baja"}
STAIR_WORD = re.compile(r"\b(stair|stairs|stairwell|stairway|escalier|treppe|treppenhaus|escalera|scala)\b", re.I)


def leads_elsewhere(model: BuildingModel) -> bool:
    """Whether a route on this sheet may go on somewhere the sheet does not show."""
    if not any(end in ("EXIT", "EXTERIOR") for e in model.edges for end in (e.a, e.b)):
        return True
    if any(e.cls == "stair" for e in model.elements):
        return True
    if any(r.type == "stairs" or STAIR_WORD.search(r.label or "") for r in model.rooms):
        return True
    return any(t.text.strip().strip(".").casefold() in LEVEL_MARKS for t in model.sheet.texts)


def _undecided(f: Finding, reason: str) -> Finding:
    assessment = f.assessment.model_copy(update={
        "outcome": "UNRESOLVED",
        "evidence_issues": [*f.assessment.evidence_issues,
                            EvidenceIssue(code=IssueCode.MISSING_INPUT, detail=reason)]})
    return f.model_copy(update={"verdict": "WARNING", "assessment": assessment})


def _number(text: str | None) -> float | None:
    found = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(found.group()) if found else None


def _count(rule: Rule, group: list[Finding], sheets: int) -> list[Finding]:
    """One building-wide count with a minimum, from what each sheet showed."""
    op, limit = rule.check.op or ">=", float(rule.check.value if rule.check.value is not None else 1)
    counted = [(n, f) for f in group if (n := _number(f.detected)) is not None]
    reached = [f for n, f in counted if not compare(n, op, limit, 0)[0]] if op != "==" else []
    if reached:                                          # shown on a sheet: the other sheets' shortfalls say nothing
        passed = [f for f in reached if f.verdict == "PASS"]
        return passed[:1] or reached[:1]
    best, base = max(counted, key=lambda c: c[0]) if counted else (None, group[0])
    read = [str(f.evidence.get("sheet")) for f in group]
    most = "none could be counted" if best is None else f"the most on one sheet is {best:g}"
    message = (f"{rule.title}: not decided for the whole building. {len(group)} of the {sheets} plan sheets were read one at a "
               f"time and {most}; required {op} {limit:g}.")
    merged = _undecided(base, "the sheets of a set are not combined, so a shortfall on one sheet does not show the building lacks it")
    evidence = {**merged.evidence, "sheets_read": read, "set_wide": True}
    return [merged.model_copy(update={"message": message, "evidence": evidence, "subject_ids": []})]


def combine(findings: list[Finding], rules: list[Rule], plan_sheets: int, open_sheets: set[str]) -> list[Finding]:
    """The findings of every sheet, with those about the whole building read across the set. One plan sheet: unchanged.
    ``open_sheets``: the sheets a route can leave (``leads_elsewhere``)."""
    if plan_sheets < 2:
        return findings
    by_id = {r.id: r for r in rules}
    counts: dict[str, list[Finding]] = {}
    out: list[Finding] = []
    for f in findings:
        rule = by_id.get(f.rule_id)
        fn = REGISTRY.get(rule.check.fn) if rule else None
        if fn is None or not fn.whole_building:
            out.append(f)
        elif fn.whole_building == "count" and (rule.check.op or ">=") in LOWER:
            counts.setdefault(f.rule_id, []).append(f)
        elif fn.whole_building == "route" and f.verdict == "FAIL" and f.evidence.get("sheet") in open_sheets:
            routed = _undecided(f, ROUTE_REASON)
            out.append(routed.model_copy(update={"message": f"{f.message} [{ROUTE_REASON}]"}))
        else:
            out.append(f)
    for rule_id, group in counts.items():
        out += _count(by_id[rule_id], group, plan_sheets)
    return out
