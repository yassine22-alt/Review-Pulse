"""Slot filling: for the commonest requirement, a limit on one measured quantity, the model only chooses and a program writes.

"Every bedroom shall have an area of at least 9 m2" has four parts: what kind of thing (rooms), which of them (bedrooms), which
quantity (area), and the limit (at least 9 m2). A small model is poor at writing the whole rule in one go and good at choosing
one item from a short list. So:

  number and comparison   read from the sentence by program: one quantity with a known unit, and the wording before or after it
                          ("at least", "au moins", "mindestens") from the wording tables, in any language that has one
  kind of thing           the model chooses among the plan's collections (or "the whole"), or "none"
  quantity                the model chooses among that collection's numeric facts, or "none" (interpreter/grounding.py)
  which of them           the model picks the category values the sentence names, from the declared values and the groups the
                          document defines; none means all of them

The rule text is then built from the choices and goes through the same compile, validate and sentence checks as a rule the model
wrote itself, so a wrong choice is caught by the same deterministic checks. The arm declines (returns no program) whenever the
sentence is not this shape: several quantities, a condition or an exception, a negation, an unknown comparison, no unit. The
free-form arm then reads it. The arm never guesses a shape it does not recognise.
"""

from __future__ import annotations

import json
import re
import time

from ..interpreter.grounding import NONE, pick
from .drafters import Draft, citation, context_for
from .expr_arms import _build, _stage
from .verify import (
    _after_regexes,
    _cue_regexes,
    _decimal_comma,
    _expected_operator,
    blocking,
    detect_language,
    number_spans,
    prepare,
    quantities,
    verify,
    wording,
)
from .world import bindings_of

SLOT_ARMS = ("expr_slots",)
OPS = {"ge": ">=", "le": "<=", "gt": ">", "lt": "<"}
# a sentence with a condition or an exception is not a plain limit: the free-form arm reads it
CONDITION = re.compile(
    r"\b(if|when|where|unless|except|excepted|provided|whereas|lorsque|lorsqu|quand|sauf|excepté|si|dès lors|wenn|falls|sofern|"
    r"außer|ausser|cuando|salvo|excepto|si\s|quando|tranne|behalve|indien|als)\b", re.I)
NEGATION = re.compile(r"\b(no|not|never|none|nor|neither|aucun|aucune|ne|n|pas|jamais|ni|kein|keine|keiner|nicht|nie|nunca|"
                      r"ningún|ninguna|nessun|nessuna|geen|niet)\b", re.I)


SILENT = "?"                         # the sentence states a figure but no direction: the model is asked, and the rule says so


def plan_limit(text: str, allow_silent: bool = False) -> tuple[str, str, float, str] | None:
    """(operator, number with unit as written, value, unit) for a sentence with exactly one limit, else None. With `allow_silent`, a
    sentence with no comparison wording at all ("must have 8 % window area") gives the operator SILENT instead of None."""
    flat = prepare(text)
    lang = detect_language(flat)
    if lang is None or lang not in wording():
        return None
    if CONDITION.search(flat):
        return None
    comma = _decimal_comma(lang, flat)
    qs = [q for q in quantities(flat, comma) if q.unit not in ("ratio",)]
    spans = number_spans(flat, comma)
    if len(qs) != 1 or len(spans) != 1:
        return None
    q = qs[0]
    op = _expected_operator(flat, q.span[0], q.span[1], lang)
    if op is None:           # "largeur minimale ... doit être de 0,80 m": the wording is not next to the number
        found = {o for pattern, o in _cue_regexes(lang) for _ in pattern.finditer(flat.lower())}
        op = found.pop() if len(found) == 1 else (SILENT if allow_silent and not found else None)
    if op not in OPS and op != SILENT:
        return None
    # a negation that is not part of the comparison wording ("no door shall be narrower than") turns the rule around
    bare = flat
    for pattern, _ in _cue_regexes(lang) + _after_regexes(lang):
        bare = re.sub(pattern.pattern, " ", bare, flags=re.I)
    for cue in sum((wording()[lang].get(k, []) for k in ("ge", "le", "gt", "lt", "after_le", "after_ge")), []):
        bare = re.sub(re.escape(cue), " ", bare, flags=re.I)
    if NEGATION.search(bare):
        return None
    value = f"{q.value:g}"
    return op, f"{value} {q.unit}".strip(), q.value, q.unit


def _describe_collection(cat: dict, name: str) -> str:
    """What a collection is, for a model that must say which kind of thing a sentence is about: its kinds, and every quantity or
    yes or no property it has. (Showing only the first few facts hid the minimum width of a room, so "hallways must be 3 ft wide"
    was taken for a sentence about doors, which have a width in plain view.)"""
    facts = cat["collections"][name].get("facts", [])
    kinds = [f"{f}: {', '.join(cat['kinds'][f])}" for f in facts if f in (cat.get("kinds") or {})]
    parts = [cat["bindings"].get(f, {}).get("description", f) for f in facts
             if cat["bindings"].get(f, {}).get("kind") in ("number", "boolean") and not f.startswith("links_")]
    return name + (f" ({'; '.join(kinds)})" if kinds else "") + ": " + "; ".join(parts[:14])


def _choose(client, question: str, options: dict[str, str], none: bool = True) -> str | None:
    ids = list(options) + ([NONE] if none else [])
    schema = {"type": "object", "properties": {"choice": {"type": "string", "enum": ids}}, "required": ["choice"]}
    try:
        out = client.complete(question, json.dumps({"options": options}, ensure_ascii=False), schema)
    except Exception:  # noqa: BLE001
        return None
    got = out.get("choice") if isinstance(out, dict) else None
    return got if got in ids else None


def _categories(client, text: str, values: list[str], groups: dict[str, list[str]]) -> list[str] | None:
    """The category values (or document defined group names) the sentence says the limit applies to; [] means all members."""
    options = {v: v.replace("_", " ") for v in values} | {g: f"{g} (a group: {', '.join(vs)})" for g, vs in groups.items()}
    if not options:
        return []
    schema = {"type": "object", "properties": {"values": {"type": "array", "items": {"type": "string", "enum": list(options)}}},
              "required": ["values"]}
    system = ("A sentence (in any language) limits a quantity for some kind of thing. Which of these categories does the "
              "sentence name as the things the limit applies to? Choose only categories the sentence actually names or "
              "clearly means. If it names none of them (it applies to all), answer an empty list. Reply with JSON only.")
    try:
        out = client.complete(system, json.dumps({"sentence": text[:800], "categories": options}, ensure_ascii=False), schema)
    except Exception:  # noqa: BLE001
        return None
    got = out.get("values") if isinstance(out, dict) else None
    return [v for v in got if v in options] if isinstance(got, list) else None


def _stable_direction(client, text: str) -> str | None:
    """The direction (ge or le) when the model says so with the options in both orders; otherwise None (a position bias is no answer)."""
    options = {"ge": "a minimum: at least this much is required", "le": "a maximum: no more than this is allowed"}
    ask = ("A sentence (in any language) states one figure for a requirement but does not say 'at least' or 'at most'. Is the "
           "figure a minimum or a maximum, judging by what is being required? Choose none if it could be either or is an exact "
           "value.\nSentence: " + text[:600])
    votes = [_choose(client, ask, options), _choose(client, ask, dict(reversed(list(options.items()))))]
    named = {v for v in votes if v in ("ge", "le")}
    # an order that answers "none" abstains; an order that names the opposite direction contradicts. Measured on a 7B model (asking
    # "would more comply? would less comply?" as well): both extra questions are answered "no" for every sentence, so they carry no
    # information and are not used
    return named.pop() if len(named) == 1 else None


def _yes(client, question: str) -> bool:
    """A yes that is the same with the two answers listed in either order (a position bias is not an answer)."""
    options = {"yes": "yes", "no": "no"}
    return _choose(client, question, options, none=False) == "yes" and _choose(
        client, question, dict(reversed(list(options.items()))), none=False) == "yes"


def confirm_named(client, text: str, cat: dict, kind_fact: str, groups: dict, chosen: list[str]) -> list[str]:
    """When the model chose no category ("applies to every member") but the sentence names some in words, each one is put to the model
    as a yes or no question: is the requirement about them? Refusing the rule outright, which the checks would do, loses a rule that
    the sentence plainly states; guessing the category would invent one. The categories the model confirms (twice, in both orders)
    are used; when none is confirmed the model's own choice stands. A category the sentence does not name is refused by the checks."""
    from .verify import named_categories

    out = []
    for name in named_categories(text, cat, kind_fact)[:4]:
        label = name.replace("_", " ")
        if _yes(client, f"A sentence (in any language) states a requirement. Is the requirement about '{label}' specifically, so that "
                        f"it applies to them and not to every kind of space?\nSentence: {text[:500]}"):
            out.append(name)
    return out or chosen


def draft_slots(arm: str, item, client) -> Draft:
    t0 = time.time()
    ctx, cat = (getattr(item, "ctx", None) or context_for(item)), item.catalogue

    def skip(why: str) -> Draft:
        return Draft(arm, None, "skip", why, time.time() - t0)

    limit = plan_limit(item.text, allow_silent=True)
    if limit is None:
        return skip("not a plain limit on one quantity")
    op, literal, _, _ = limit
    silent = op == SILENT
    if silent:
        # no "at least" or "at most" in the sentence: the model chooses, and the choice counts only when it is the same with the
        # options in both orders. The rule then carries a note that the direction was not written (see interpreter/checked.py)
        op = _stable_direction(client, item.text)
        if op is None:
            return skip("the sentence states a figure but not whether it is a minimum or a maximum")
    bindings, collections = bindings_of(cat), list(cat["collections"])
    whole = cat.get("whole") or "building"
    options = {c: _describe_collection(cat, c) for c in collections}
    if cat.get("building"):
        options["whole"] = f"the {whole} as a whole: " + "; ".join(
            cat["bindings"].get(f, {}).get("description", f) for f in cat["building"][:4])
    system = ("A sentence from a requirements document (in any language) limits one measured quantity. Which kind of thing does "
              "it limit? Choose the option the sentence is about, or none if the plan provides no such thing. ")
    got = _choose(client, system + "\nSentence: " + item.text[:600], options)
    if got is None or got == NONE:
        return skip("no kind of thing chosen")
    if got == "whole":
        facts, owner = list(cat["building"]), None
    else:
        facts, owner = list(cat["collections"][got].get("facts", [])), got
    numeric = {f: cat["bindings"][f].get("description", f) for f in facts
               if cat["bindings"].get(f, {}).get("kind") == "number"}
    fact = pick(client, item.text, numeric)
    if fact is None or fact == NONE:
        return skip("no quantity chosen")
    if owner is None:
        require = f"{whole}.{fact} {OPS[op]} {literal}"
    else:
        kind_facts = [f for f in facts if f in (cat.get("kinds") or {})]
        where = ""
        if kind_facts:
            kf = kind_facts[0]
            groups = ((cat.get("groups") or {}).get(kf)) or {}
            chosen = _categories(client, item.text, list(cat["kinds"][kf]), groups)
            if chosen is None:
                return skip("categories not answered")
            chosen = confirm_named(client, item.text, cat, kf, groups, chosen)
            members = {g: list(v) for g, v in groups.items()}
            chosen = sorted({v for c in chosen for v in members.get(c, [c])})
            if chosen:
                where = " where (" + " or ".join(f"v.{kf} == '{c}'" for c in chosen) + ")"
        require = f"forall {owner} v{where}: v.{fact} {OPS[op]} {literal}"
    raw = {"title": f"{fact} limit", "applies_when": None, "unless": None, "require": require,
           "sources": [{"clause": ctx.target, "quote": citation(item)}], "unresolved": []}

    def check(prog):
        return verify(prog, item.text, cat, getattr(item, "lang", None), grounding_words=False)

    try:
        program = _build(raw, ctx, bindings, collections, {whole}, check, cat.get("kinds"), cat.get("passable"), cat)
    except Exception as exc:  # noqa: BLE001 - a wrong choice is caught by the same checks as any draft; the free-form arm follows
        return Draft(arm, None, _stage(exc), f"{type(exc).__name__}: {str(exc)[:250]}", time.time() - t0, raw)
    if blocking(check(program)):
        return skip("the checks refused the assembled rule")
    return Draft(arm, program, "ok", "slots:silent_direction=" + op if silent else "slots", time.time() - t0, raw)
