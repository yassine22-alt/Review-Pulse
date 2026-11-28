"""The last arm: a requirement about something the drawing can only SAY, checked as "the drawing set says it".

Many lines of a plan-review checklist are about things a plan view does not draw to measure: smoke alarms, fire ratings, handrails,
safety glazing. A reviewer first checks that the set calls the thing out at all (a note, a legend entry, a callout), and that is
decidable from the text of the sheets. When every other arm has declined a sentence, and the sentence names a kind of note the plan
reader counts (see annotate/lexicon/notes.yaml), this arm writes the rule "the set mentions it at least once".

What the rule is, and is not:
  - It does not hold only when the whole set was read and never mentions the thing. That is something a reviewer wants to know
    ("no smoke alarm is called out anywhere"), and it is reported as a warning, never as a failure: many such sentences apply
    only in some cases ("townhouses require a sprinkler system", "handrails on stairs with four or more risers", "if applicable"),
    and nothing here knows whether the case holds. On the four real checklists about 9 of 20 such rules were conditional.
  - It never passes: where the thing is, how many there are and whether it is of the right kind are listed as not checked, and a
    rule with an unchecked part cannot report "satisfied".
  - It is built by a program from the same word lists the plan reader counts with, so it calls no model and cannot invent a
    figure. A sentence that negates or excuses ("no sprinkler is required", "except", "unless") is left declined: a missing
    mention would then not be a fault.
"""

from __future__ import annotations

import re
import time

from ..annotate.notes import DESCRIPTIONS, kinds_named
from .drafters import Draft, citation, context_for
from .expr_arms import _build, _stage
from .world import bindings_of

ARM = "expr_mention"
NEGATION = re.compile(
    r"\b(?:no|not|never|without|except|unless|exempt\w*|waive\w*|n'|ne|pas|sans|sauf|aucun\w*|kein\w*|nicht|ohne|au(?:ss|ß)er|"
    r"sin|excepto|salvo|ning[úu]n\w*|senza|eccetto|nessun\w*)\b", re.I)


def draft_mention(item) -> Draft:
    t0 = time.time()
    ctx, cat = (getattr(item, "ctx", None) or context_for(item)), item.catalogue

    def skip(why: str) -> Draft:
        return Draft(ARM, None, "skip", why, time.time() - t0)

    whole = cat.get("whole") or "building"
    available = [k for k in kinds_named(item.text) if k in (cat.get("building") or [])]
    if not available:
        return skip("the sentence names nothing the drawing's notes are searched for")
    if NEGATION.search(item.text):
        return skip("the sentence negates or excuses something: a missing mention would not be a fault")
    require = " and ".join(f"{whole}.{k} >= 1" for k in available)
    things = ", ".join(DESCRIPTIONS[k] for k in available)
    raw = {"title": f"The drawings mention {things}"[:120], "applies_when": None, "unless": None, "require": require,
           "not_checked": [f"where the {things} are, how many there are and whether they meet the rest of the sentence: this rule only "
                           "checks that the drawing set mentions them"],
           "sources": [{"clause": ctx.target, "quote": citation(item)}], "unresolved": []}
    try:
        program = _build(raw, ctx, bindings_of(cat), list(cat["collections"]), {whole}, None, cat.get("kinds"), cat.get("passable"), cat)
    except Exception as exc:  # noqa: BLE001 - a rule that does not compile is not kept
        return Draft(ARM, None, _stage(exc), f"{type(exc).__name__}: {str(exc)[:250]}", time.time() - t0, raw)
    program.advisory = True            # whether the sentence applies to this building is not known: a miss asks a person to look
    return Draft(ARM, program, "ok", "mention:" + ",".join(available), time.time() - t0, raw)
