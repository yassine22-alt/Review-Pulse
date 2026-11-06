"""What to tell the user about a clause that produced no usable rule. Never a silent drop, never a guess.

Every clause ends in one of: drafted (a rule that passed every check), UNRESOLVED (with the reason in plain words).
UNRESOLVED means "this clause is not being checked yet", which is different from a pass.
"""

from __future__ import annotations

import re


def clause_status(draft) -> tuple[str, str]:
    """(status, reason) for a Draft from any arm."""
    if draft.program is not None:
        return "DRAFTED", "a rule was written and passed the structure and sentence checks"
    raw = draft.raw if isinstance(draft.raw, dict) else {}
    if raw.get("unresolved"):
        return "UNRESOLVED", "needs something the plan does not provide: " + "; ".join(map(str, raw["unresolved"]))
    detail = draft.detail or ""
    missing = re.search(r"unsupported fact (\w+)|'(\w+)' is not a variable", detail)
    if missing:
        name = next(g for g in missing.groups() if g)
        return "UNRESOLVED", f"needs a quantity the plan does not provide (the rule would have needed '{name}')"
    if draft.stage == "verify":
        why = detail.split("verifier:", 1)[-1].strip()[:200]
        return "UNRESOLVED", f"every draft disagreed with the sentence: {why}"
    return "UNRESOLVED", "no rule that matches the sentence could be written automatically, so it is not being checked"
