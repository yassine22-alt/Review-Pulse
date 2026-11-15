"""Relations: for requirements about how spaces connect, the model only chooses and a program writes the rule.

"No door or opening connects a garage directly to a bedroom." "Every habitable room reaches an exit without passing through a
bathroom." "Every enclosed room has at least one door." These are the other common family of plan requirements, next to a
limit on one measured quantity (slot_arm.py). A small model writes them badly when it has to produce the whole rule: it invents
quantities, restricts to categories the sentence never names, or loses the direction of a "not". It chooses well from a short list.

  relation   the model chooses one of a few kinds of relation, or none (no_link, must_link, route, has_passage)
  kinds      the model chooses which categories of space the sentence means for each side of the relation
  boundary   where a route must lead, when the plan offers more than one (an exit, an outlet)

The rule is then written from templates and goes through exactly the same compile, validate and sentence checks as a rule the
model wrote itself, so a wrong choice is caught by the same deterministic checks. The arm declines (returns no program) when the
sentence carries a figure or a condition, or when the plan offers no connections to reason about; the free-form arm then reads it.
Nothing here knows a domain: the node collection, its category fact and its boundaries come from the fact graph.
"""

from __future__ import annotations

import json
import re
import time

from ..interpreter.grounding import NONE
from .drafters import Draft, citation, context_for
from .expr_arms import _build, _stage
from .slot_arm import CONDITION
from .verify import _decimal_comma, blocking, detect_language, number_spans, prepare, quantities, verify
from .world import bindings_of

RELATIONS = {
    "no_link": "Two kinds of space must NOT be joined directly by a door or an opening",
    "must_link": "A kind of space must be joined directly to another kind of space by a door or an opening",
    "route": "A kind of space must have a route, over doors and openings, to a place such as the exit, perhaps without passing "
             "through certain kinds of space",
    "has_passage": "A kind of space must have at least one door or opening",
    "has_property": "A kind of space must have a property the plan records (a window, a name that shows its use), or the drawing "
                    "itself must have one (drawn to scale, dimensioned)",
}


def _node_collection(cat: dict) -> tuple[str, str] | None:
    """(collection of spaces that connect, its category fact): the collection with connection facts and a category fact."""
    for name, coll in cat["collections"].items():
        facts = coll.get("facts", [])
        if any(f.startswith(("links_", "reaches_")) for f in facts):
            kinds = [f for f in facts if f in (cat.get("kinds") or {})]
            if kinds:
                return name, kinds[0]
    return None


def _prompt(question: str, sentence: str) -> str:
    """One shape for every question put to the model: the question, the instruction to answer in JSON, then the sentence."""
    return "\n".join([question + " Reply with JSON only.", "Sentence: " + sentence[:600]])


def _choose(client, system: str, payload: dict, ids: list[str], key: str = "choice") -> str | None:
    schema = {"type": "object", "properties": {key: {"type": "string", "enum": ids}}, "required": [key]}
    try:
        out = client.complete(system, json.dumps(payload, ensure_ascii=False), schema)
    except Exception:  # noqa: BLE001 - no answer: the arm declines
        return None
    got = out.get(key) if isinstance(out, dict) else None
    return got if got in ids else None


def _choose_many(client, system: str, payload: dict, ids: list[str]) -> list[str] | None:
    schema = {"type": "object", "properties": {"values": {"type": "array", "items": {"type": "string", "enum": ids}}},
              "required": ["values"]}
    try:
        out = client.complete(system, json.dumps(payload, ensure_ascii=False), schema)
    except Exception:  # noqa: BLE001
        return None
    got = out.get("values") if isinstance(out, dict) else None
    return [v for v in got if v in ids] if isinstance(got, list) else None


def _test(var: str, fact: str, values: list[str]) -> str:
    return "(" + " or ".join(f"{var}.{fact} == '{v}'" for v in sorted(set(values))) + ")"


def names_spaces(text: str, cat: dict) -> bool:
    """A sentence that names rooms, doors or any kind of space is about them, not about the sheet: "label all rooms" must not
    become "the sheet has dimensions"."""
    from .verify import _names, fold_accents, named_categories

    low = fold_accents(text.lower())
    return any(_names(name.rstrip("s"), low) for name in cat["collections"] if len(name) > 3) or any(
        named_categories(text, cat, fact) for fact in cat.get("kinds", {}))


def _sheet_requirement(client, text: str, cat: dict) -> list[str]:
    """The yes or no properties of the drawing as a whole that the sentence requires ("to scale", "dimensioned"), as the model chooses
    them from the list the plan offers; only the ones it names in both orders of the list count. Empty when none."""
    props = {f: cat["bindings"][f].get("description", f) for f in cat.get("building", [])
             if cat["bindings"].get(f, {}).get("kind") == "boolean"}
    if not props:
        return []
    if names_spaces(text, cat):
        return []
    ask = ("A sentence (in any language) is a requirement. Does it require the DRAWING ITSELF (the plan sheet as a whole, not its "
           "rooms or doors) to have some of these properties? Choose those it requires; an empty list if it is about something "
           "else. Reply with JSON only.\nSentence: " + text[:600])
    first = _choose_many(client, ask, {"properties": props}, list(props))
    second = _choose_many(client, ask, {"properties": dict(reversed(list(props.items())))}, list(props))
    if not first or second is None:
        return []
    chosen = [f for f in props if f in first and f in second]
    if not chosen:
        return []
    # the sentence must be ABOUT the drawing: "Show all access openings, calling out sizes" and "Attic access located with opening
    # dimensions" mention dimensions, but what they require is something shown on the drawing, not that the drawing be dimensioned
    from .slot_arm import _choose

    kinds = {"whole": "The drawing itself (the floor plan, site plan or plan sheet as a whole) must be dimensioned, drawn to scale, "
                      "or have some property of the drawing",
             "thing": "Particular things shown on the drawing (openings, doors, rooms, stairs, access panels, notes) must be shown, "
                      "with their sizes or labelled"}
    question = "A sentence (in any language) is a requirement. What does it require?\nSentence: " + text[:600]
    both = (_choose(client, question, kinds, none=False), _choose(client, question, dict(reversed(list(kinds.items()))), none=False))
    return chosen if both == ("whole", "whole") else []       # measured on 7 real lines: all separated, in both orders


def _assemble(arm: str, item, cat: dict, require: str, label: str, t0: float) -> Draft:
    """The checks every written rule goes through, for a rule a program wrote from a requirement (a Draft, ok or refused)."""
    ctx = getattr(item, "ctx", None) or context_for(item)
    raw = {"title": label, "applies_when": None, "unless": None, "require": require,
           "sources": [{"clause": ctx.target, "quote": citation(item)}], "unresolved": []}
    whole = cat.get("whole") or "building"
    bindings, collections = bindings_of(cat), list(cat["collections"])

    def check(prog):
        return verify(prog, item.text, cat, getattr(item, "lang", None), grounding_words=False)

    try:
        program = _build(raw, ctx, bindings, collections, {whole}, check, cat.get("kinds"), cat.get("passable"), cat)
    except Exception as exc:  # noqa: BLE001 - a wrong choice is caught by the same checks as any draft; the free-form arm follows
        return Draft(arm, None, _stage(exc), f"{type(exc).__name__}: {str(exc)[:250]}", time.time() - t0, raw)
    if blocking(check(program)):
        return Draft(arm, None, "skip", "the checks refused the assembled rule", time.time() - t0)
    return Draft(arm, program, "ok", f"relation:{label}", time.time() - t0, raw)


def _about_spaces(client, text: str) -> bool:
    """Is the sentence about every room or space of a building, rather than about doors, windows, walls or equipment? A multiple choice
    with the options in both orders; only an answer that is the same both times counts (a yes or no is too easy for a small model)."""
    options = {"spaces": "the rooms or spaces of a building, all of them",
               "something_else": "doors, windows, walls, floors, materials, equipment or anything that is not a room"}
    ask = ("A sentence (in any language) states a requirement. Is the requirement about every room or space of a building, or about "
           "something else? Choose one. Reply with JSON only.\nSentence: " + text[:500])
    first = _choose(client, ask, {"options": options}, list(options))
    second = _choose(client, ask, {"options": dict(reversed(list(options.items())))}, list(options))
    return first == "spaces" and second == "spaces"


def draft_relation(arm: str, item, client) -> Draft:
    t0 = time.time()
    ctx, cat = (getattr(item, "ctx", None) or context_for(item)), item.catalogue

    def skip(why: str) -> Draft:
        return Draft(arm, None, "skip", why, time.time() - t0)

    node = _node_collection(cat)
    if node is None:
        return skip("the plan offers no connections between spaces")
    owner, kind_fact = node
    flat = prepare(item.text)
    lang = detect_language(flat)
    if CONDITION.search(flat):
        return skip("a condition or an exception: the free-form arm reads it")
    if lang is not None and (quantities(flat, _decimal_comma(lang, flat)) or number_spans(flat, _decimal_comma(lang, flat))):
        return skip("the sentence carries a figure: not a plain relation")
    values = list(cat["kinds"][kind_fact])
    groups = ((cat.get("groups") or {}).get(kind_fact)) or {}
    options = {v: v.replace("_", " ") for v in values} | {g: f"{g} (a group: {', '.join(vs)})" for g, vs in groups.items()}
    members = {g: list(vs) for g, vs in groups.items()}

    def expand(chosen: list[str]) -> list[str]:
        out: list[str] = []
        for c in chosen:
            for v in members.get(c, [c]):
                if v not in out:
                    out.append(v)
        return out

    sheet = _sheet_requirement(client, item.text, cat)
    if sheet:
        whole = cat.get("whole") or "building"
        draft = _assemble(arm, item, cat, " and ".join(f"{whole}.{f} == true" for f in sheet), "sheet", t0)
        if draft.program is not None and len(re.findall(r"[^\W\d_]+", item.text)) > 8:
            # a long sentence ("Dimensions from grade to finished floor, and to the roof peak") asks for more than the drawing-level
            # property the rule tests; passing it would suggest that the specific items are there
            draft.program.not_checked = list(draft.program.not_checked) + [
                "any specific items the sentence names: the rule only tests the property of the drawing as a whole"]
        return draft
    system = ("A sentence from a requirements document (in any language) imposes one requirement on how the spaces of a "
              "building plan connect. Which kind of requirement is it? Choose none if it is about something else or about "
              "something a plan does not show. Reply with JSON only.\nSentence: " + item.text[:600])
    relation = _choose(client, system, {"options": RELATIONS}, list(RELATIONS) + [NONE])
    if relation is None or relation == NONE:
        return skip("no relation chosen")

    def kinds(role: str, allow_empty: bool = False) -> list[str] | None:
        ask = (f"A sentence (in any language) states a requirement about spaces. Which categories of space are {role}? Choose only "
               "categories the sentence names or clearly means. " + ("An empty list means every space. " if allow_empty else "")
               + "Reply with JSON only.\nSentence: " + item.text[:600])
        got = _choose_many(client, ask, {"categories": options}, list(options))
        if got is None:
            return None
        # a category the sentence does not name is refused by the scope check whatever the model meant, so it is dropped here: what is
        # left is what the sentence names, and an empty list means every space ("label all rooms")
        from .verify import named_categories

        named = set(named_categories(item.text, cat, kind_fact))
        chosen = expand([g for g in got if g in named])
        # every category chosen says "any space", whatever the model meant: that is no restriction at all
        if allow_empty and set(values) <= set(chosen):
            chosen = []
        # no restriction means "every room or space". That has to be what the sentence says: a requirement about doors, windows or
        # anything else is not one about every space, and applying it to all of them would be a rule the sentence never stated
        if allow_empty and not chosen and not _about_spaces(client, item.text):
            return None
        return chosen

    if relation in ("no_link", "must_link"):
        # two sides, each ONE category (or group): asked as a multiple choice so the model cannot name both kinds for both sides
        first = _choose(client, "A sentence (in any language) says how two kinds of space are connected. Which category is the "
                        "FIRST kind of space, the one the requirement is mainly about? Reply with JSON only.\nSentence: "
                        + item.text[:600], {"options": options}, list(options))
        if first is None:
            return skip("the first kind of space was not chosen")
        rest = {k: v for k, v in options.items() if k != first} | {"same": "another space of the same kind as the first"}
        second = _choose(client, "The same sentence connects the first kind of space (" + options[first] + ") with a second kind. Which "
                         "category is the SECOND kind? Choose 'same' only if the sentence connects spaces of one kind with each other. "
                         "Reply with JSON only.\nSentence: " + item.text[:600], {"options": rest}, list(rest))
        if second is None:
            return skip("the second kind of space was not chosen")
        a = expand([first])
        b = a if second == "same" else expand([second])
        if second != "same" and set(a) & set(b):
            return skip("the two sides overlap")
        where_a, where_b = f" where {_test('a', kind_fact, a)}", f" where {_test('b', kind_fact, b)}"
        if relation == "no_link":
            require = f"forall {owner} a{where_a}: forall {owner} b{where_b}: not linked(a, b)"
        else:
            require = f"forall {owner} a{where_a}: exists {owner} b{where_b}: linked(a, b)"
    elif relation == "route":
        a = kinds("the spaces that must have the route (the subject of the requirement)", allow_empty=True)
        if a is None:
            return skip("the subject spaces were not chosen")
        avoid = kinds("the spaces the route must NOT pass through (an empty list if the sentence names none)", allow_empty=True)
        if avoid is None:
            return skip("the spaces to avoid were not answered")
        # a small model lists the spaces to avoid among the subjects too. A category in both lists is asked about once, as a plain
        # yes or no: must spaces of that kind themselves have the route? ("a bedroom other than itself" says yes; a bathroom to avoid says no)
        had_subject = bool(a)
        for c in [x for x in a if x in avoid]:
            yes = _choose(client, "A sentence (in any language) requires some spaces to have a route to an exit, and forbids that route "
                          f"to pass through some spaces. Must spaces of the category '{options.get(c, c)}' THEMSELVES have the route? "
                          "Reply with JSON only.\nSentence: " + item.text[:600], {"options": {"yes": "yes", "no": "no"}}, ["yes", "no"])
            if yes is None:
                return skip("a space named twice could not be placed")
            if yes == "no":
                a = [x for x in a if x != c]
        if had_subject and not a:
            return skip("every subject space was also a space to avoid")
        where_a = f" where {_test('a', kind_fact, a)}" if a else ""
        boundaries = list(cat.get("boundaries") or [])
        if not boundaries:
            return skip("the plan offers no place a route can lead to")
        dest = boundaries[0] if len(boundaries) == 1 else _choose(
            client, "Where must the route lead? Reply with JSON only.\nSentence: " + item.text[:600],
            {"options": {x: x.lower() for x in boundaries}}, boundaries)
        if dest is None:
            return skip("no destination chosen")
        avoiding = (" , avoiding " + ", ".join(f"'{v}'" for v in sorted(avoid))).replace(" ,", ",") if avoid else ""
        require = f"forall {owner} a{where_a}: reaches(a, {dest}{avoiding})"
    elif relation == "has_property":
        props = {f: cat["bindings"][f].get("description", f) for f in cat["collections"][owner].get("facts", [])
                 if cat["bindings"].get(f, {}).get("kind") == "boolean" and not f.startswith("reaches_")}
        whole_props = {} if names_spaces(item.text, cat) else {
            f: cat["bindings"][f].get("description", f) for f in cat.get("building", [])
            if cat["bindings"].get(f, {}).get("kind") == "boolean"}
        if not props and not whole_props:
            return skip("the plan records no yes or no property")
        chosen = _choose(client, _prompt("A sentence (in any language) requires something to have a property: the spaces of a plan, or "
                                         "the drawing as a whole. Which property of the list does it require? Choose none if it is "
                                         "not one of them.", item.text),
                         {"options": props | whole_props}, list(props | whole_props) + [NONE])
        if chosen is None or chosen == NONE:
            return skip("no property chosen")
        if chosen in whole_props and chosen not in props:
            require = f"{cat.get('whole') or 'building'}.{chosen} == true"
        else:
            a = kinds("the subject of the requirement (the spaces it is about)", allow_empty=True)
            if a is None:
                return skip("the subject spaces were not chosen")
            where_a = f" where {_test('a', kind_fact, a)}" if a else ""
            require = f"forall {owner} a{where_a}: a.{chosen} == true"
    else:
        a = kinds("the subject of the requirement (the spaces it is about)", allow_empty=True)
        if a is None:
            return skip("the subject spaces were not chosen")
        where_a = f" where {_test('a', kind_fact, a)}" if a else ""
        passage = next((f for f in cat["collections"][owner].get("facts", []) if f == "links_passable"), None)
        if passage is None:
            return skip("the plan does not count doors and openings")
        require = f"forall {owner} a{where_a}: a.{passage} >= 1"
    raw = {"title": f"{relation.replace('_', ' ')}", "applies_when": None, "unless": None, "require": require,
           "sources": [{"clause": ctx.target, "quote": citation(item)}], "unresolved": []}
    whole = cat.get("whole") or "building"
    bindings, collections = bindings_of(cat), list(cat["collections"])

    def check(prog):
        return verify(prog, item.text, cat, getattr(item, "lang", None), grounding_words=False)

    try:
        program = _build(raw, ctx, bindings, collections, {whole}, check, cat.get("kinds"), cat.get("passable"), cat)
    except Exception as exc:  # noqa: BLE001 - a wrong choice is caught by the same checks as any draft; the free-form arm follows
        return Draft(arm, None, _stage(exc), f"{type(exc).__name__}: {str(exc)[:250]}", time.time() - t0, raw)
    if blocking(check(program)):
        return skip("the checks refused the assembled rule")
    return Draft(arm, program, "ok", f"relation:{relation}", time.time() - t0, raw)
