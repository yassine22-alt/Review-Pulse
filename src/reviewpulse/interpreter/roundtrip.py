"""Round trip: does the rule, read back in plain words, say what the sentence says?

The checks of xeval/verify.py compare the rule with the sentence by words and numbers. They cannot tell that "Residential Zoning
Compliance Form or Information on Plans" is not the requirement "every room is labelled", because nothing in the rule contradicts a
sentence that has no figures. A person reviewing the rule would see it at once, by reading the rule in plain words next to the
sentence. This does that reading with the model, as a multiple choice, and is deliberately cautious:

  - the rule is described by a program (xeval/readback.py), never by the model, so the description cannot flatter the rule;
  - what the rule does NOT check (`not_checked`) is part of what the model reads;
  - the choice is asked twice with the options in both orders, and a rule is refused only when BOTH answers say the rule is about
    something different. A model that cannot decide, or has a position bias, never costs a rule.

The result is one of "same", "partial" (checks only a part: shown as a note), "different" (refused). Any failure to get an answer
is "same": this gate only ever removes a rule that two answers agree is wrong.
"""

from __future__ import annotations

import json

OPTIONS = {
    "same": "The rule checks what the sentence requires (it may leave out details the plan cannot show).",
    "partial": "The rule checks only one part of what the sentence requires; another requirement of the sentence is missing from it.",
    "different": "The rule is about something else than the sentence, or requires something the sentence does not say.",
}

SYSTEM = ("A sentence from a requirements document (in any language) was turned into a rule that is checked against a building "
          "plan. Compare the sentence with the rule as it is written in words. Choose the option that describes the rule. "
          "Reply with JSON only.")


def _ask(client, sentence: str, rule: str, order: list[str]) -> str | None:
    options = {k: OPTIONS[k] for k in order}
    schema = {"type": "object", "properties": {"choice": {"type": "string", "enum": order}}, "required": ["choice"]}
    user = json.dumps({"sentence": sentence[:700], "rule": rule[:700], "options": options}, ensure_ascii=False)
    try:
        out = client.complete(SYSTEM, user, schema)
    except Exception:  # noqa: BLE001 - no answer is not a verdict
        return None
    got = out.get("choice") if isinstance(out, dict) else None
    return got if got in OPTIONS else None


def compare(client, sentence: str, rule_in_words: str, not_checked: list[str] | None = None) -> str:
    """"same", "partial" or "different". "different" only when both orders of the options say so; "partial" likewise."""
    rule = rule_in_words + (" The rule does not check: " + "; ".join(not_checked) + "." if not_checked else "")
    first = _ask(client, sentence, rule, ["same", "partial", "different"])
    second = _ask(client, sentence, rule, ["different", "partial", "same"])
    if first is not None and first == second and first in ("partial", "different"):
        return first
    return "same"
