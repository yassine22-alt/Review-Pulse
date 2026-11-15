"""Does the quantity a rule measures belong to the sentence it came from?

A rule can be valid, carry the sentence's number and comparison direction, and still measure the wrong thing ("sockets less
than 1.30 m above the floor" became "travel distance to the outside is less than 1.3 m"). The deterministic checks compare
numbers, units and directions; words of a sentence in any language cannot be compared with fact names by rule, and measured
alternatives (sentence embeddings, an entailment model) separate such a swap poorly (scripts/grounding_swap.py).

What a small model does reliably is choose. So the question is put as a multiple choice, independent of the rule that was
drafted: "which of these facts is the quantity this sentence limits, or none of them?". The answer is compared with the fact
the rule actually measures. A different fact, or "none" (the plan provides nothing the sentence is about), rejects the rule.
The answer for a given sentence and fact list never depends on the draft, so the draft cannot talk the check into agreeing.

The check only ever removes a draft; it never creates a rule. Any failure to get an answer leaves the draft as it was.
"""

from __future__ import annotations

import json

NONE = "none"
SYSTEM = """A sentence from a requirements document limits one measurable quantity. Below is the list of facts a plan drawing
provides, each with an id and a description. The sentence can be in any language.

Choose the fact whose value the sentence limits (a size, a distance, an area, a count, a height, a ratio ...).
If no fact in the list is that quantity, answer "none". Do not choose a fact that merely has the same unit or the same kind of
number: a height above the floor is not a distance to an exit, a width is not a length, a door is not a window.
Reply with JSON only: {"fact": "<id or none>"}."""


def measured_facts(node, out: list | None = None) -> list[str]:
    """Names of the facts a rule compares with a number: the quantities it measures, in order, without repeats."""
    out = [] if out is None else out
    if isinstance(node, dict):
        if node.get("node") in ("ge", "le", "gt", "lt", "eq", "ne"):
            sides = [node.get("left"), node.get("right")]
            facts = [s for s in sides if isinstance(s, dict) and s.get("node") == "fact"]
            lits = [s for s in sides if isinstance(s, dict) and s.get("node") == "literal"
                    and isinstance(s.get("value"), (int, float)) and not isinstance(s.get("value"), bool)]
            if facts and lits and facts[0]["name"] not in out:
                out.append(facts[0]["name"])
        for v in node.values():
            measured_facts(v, out)
    elif isinstance(node, list):
        for v in node:
            measured_facts(v, out)
    return out


def choices(bindings: dict, only: set[str] | None = None) -> dict[str, str]:
    """{fact id: description} for the numeric facts a sentence could be limiting."""
    return {n: b.get("description") or n for n, b in bindings.items()
            if b.get("kind") == "number" and (only is None or n in only)}


def pick(client, sentence: str, options: dict[str, str], system: str = SYSTEM) -> str | None:
    """The fact id the model chooses, "none", or None when no usable answer came back."""
    if not options:
        return None
    ids = list(options) + [NONE]
    schema = {"type": "object", "properties": {"fact": {"type": "string", "enum": ids}}, "required": ["fact"]}
    user = json.dumps({"sentence": sentence[:1000], "facts": options}, ensure_ascii=False)
    try:
        out = client.complete(system, user, schema)
    except Exception:  # noqa: BLE001 - no answer leaves the draft alone
        return None
    got = out.get("fact") if isinstance(out, dict) else None
    return got if got in ids else None


def agrees(client, sentence: str, options: dict[str, str], fact: str, system: str = SYSTEM) -> tuple[bool, str | None]:
    """(the model's choice is `fact`, what it chose). A disagreement is asked once more with the options in the opposite order:
    a small model has a position bias, and a rule should not be refused because of where its fact sat in a list."""
    first = pick(client, sentence, options, system)
    if first is None or first == fact:
        return True, first
    second = pick(client, sentence, dict(reversed(list(options.items()))), system)
    if second is None or second == fact:
        return True, second
    return False, first if first != NONE else second


def _family(fact: str) -> str:
    """Counts of connections (doors, openings, windows, any passable link) are one kind of fact: a sentence about "doors or openings"
    may be answered with either, and a rule counting the other is not a different quantity. Anything else is its own family."""
    return "links" if fact.startswith("links_") and not fact.startswith("links_to_") else fact


def check_measured(client, sentence: str, requirement: dict, bindings: dict) -> str | None:
    """None when the rule measures what the sentence limits (or no answer was possible); else the reason it does not."""
    options = choices(bindings)
    several = [f for f in measured_facts(requirement) if f in options]
    if len(several) > 1:
        # a sentence with several limits has no single quantity to point at: the model's pick, in both orders of the list, must
        # be one of the quantities the rule measures (a pick of anything else means the sentence is about something other)
        members = {_family(f) for f in several}
        for listed in (options, dict(reversed(list(options.items())))):
            got = pick(client, sentence, listed)
            if got is not None and (got == NONE or _family(got) not in members):
                what = "none of the quantities this plan provides" if got == NONE else f"'{options[got]}'"
                return f"the rule measures {' and '.join(repr(options[f]) for f in several)} but the sentence limits {what}"
        return None
    for fact in measured_facts(requirement):
        if fact not in options:
            continue
        ok, got = agrees(client, sentence, options, fact)
        if ok or (got and _family(got) == _family(fact)):
            continue
        if got in (None, NONE):
            return (f"the rule measures '{options[fact]}' but none of the quantities this plan provides is what the "
                    "sentence limits")
        return f"the rule measures '{options[fact]}' but the sentence limits '{options[got]}'"
    return None


# ---------------------------------------------------------------------------------------------------------------------
# Rules with no measured number: a route, a direct link, a count, a yes/no fact. The same question, one level up: which KIND
# of requirement does the sentence state? A sentence about the clearance of an amusement ride must not become "every room has
# a route to the exit", and nothing in the structure of that rule says it is wrong.

KIND_SYSTEM = """A sentence from a requirements document imposes one requirement on a building plan. Below is a list of the
kinds of requirement a plan can be checked for, each with an id and a description. The sentence can be in any language.

Choose the kind the sentence states. If the sentence is about something else, or about something a plan does not show,
answer "none". Do not choose a kind only because a word of the sentence looks related: choose it only when the sentence
really requires that.
Reply with JSON only: {"fact": "<id or none>"}."""

KINDS = {
    "route": "A room, or something in it, must (or must not) be reachable over doors and openings from another place, such as "
             "the exit or a certain kind of room",
    "link": "Two kinds of room must (or must not) be joined directly by a door or an opening",
    "count": "A number of items (doors, exits, windows, rooms) is required, at least or at most",
    "measure": "A size, distance, width, area, height or ratio is limited by a number",
}


LABELS = {"route": "a route from a room to another place", "link": "a direct door or opening between two kinds of room",
          "count": "a required number of items", "measure": "a limit on a size, distance or area"}


def _label(menu: dict, kind: str) -> str:
    return LABELS.get(kind) or menu[kind].rstrip(".")


def concerns(node, out: list | None = None) -> list[str]:
    """The kinds of requirement a rule states, as ids of `kind_choices`: route, link, count, a yes/no fact. A numeric limit on
    a measured quantity is not listed here: `check_measured` asks about it with the precise quantity."""
    out = [] if out is None else out
    if isinstance(node, dict):
        kind = node.get("node")
        if kind == "path_exists" and "route" not in out:
            out.append("route")
        elif kind == "linked" and "link" not in out:
            out.append("link")
        elif kind == "count" and "count" not in out:
            out.append("count")
        elif kind in ("eq", "ne"):
            sides = [node.get("left"), node.get("right")]
            facts = [x for x in sides if isinstance(x, dict) and x.get("node") == "fact"]
            bools = [x for x in sides if isinstance(x, dict) and x.get("node") == "literal" and isinstance(x.get("value"), bool)]
            if facts and bools and facts[0]["name"] not in out:
                out.append(facts[0]["name"])
        for v in node.values():
            concerns(v, out)
    elif isinstance(node, list):
        for v in node:
            concerns(v, out)
    return out


def kind_choices(bindings: dict) -> dict[str, str]:
    menu = dict(KINDS)
    for n, b in bindings.items():
        if b.get("kind") == "boolean":
            menu[n] = b.get("description") or n
    return menu


def _same_kind(menu: dict, kind: str) -> set[str]:
    """The menu entries that state the same requirement as `kind`: the generic "route" and the plan's own reaches_* facts are one
    kind, as are "link" and links_* (a model that picks the specific fact has understood the sentence)."""
    families = [{"route"} | {k for k in menu if k.startswith("reaches_")}, {"link"} | {k for k in menu if k.startswith("links_")}]
    for family in families:
        if kind in family:
            return family
    return {kind}


def _also_requires(client, sentence: str, what: str) -> bool:
    """The sentence names a different requirement than the rule states; does it ALSO require what the rule states? A yes that is the
    same with the answers listed in both orders (a position bias is not an answer)."""
    from ..xeval.slot_arm import _yes

    return _yes(client, f"A sentence (in any language) may state several requirements. Does it require this: {what}?\n"
                        f"Sentence: {sentence[:600]}")


def check_concern(client, sentence: str, requirement: dict, bindings: dict) -> str | None:
    """None when the sentence states the kind of requirement the rule states (or no answer was possible), else the reason."""
    menu = kind_choices(bindings)
    for c in concerns(requirement):
        if c not in menu:
            continue
        same = _same_kind(menu, c)
        ok, got = agrees(client, sentence, menu, c, KIND_SYSTEM)
        if ok or got in same:
            continue
        if got not in (None, NONE) and _also_requires(client, sentence, _label(menu, c)):
            continue                 # "Dimension and label all rooms": two requirements, and the pick named only one of them
        if got in (None, NONE):
            return f"the rule requires {_label(menu, c)}, but the sentence does not state that"
        return f"the rule requires {_label(menu, c)}, but the sentence states {_label(menu, got)}"
    return None
