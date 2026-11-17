"""Limits: one sentence, several limits, an exception, "at least one", and parts the plan cannot show.

The slot arm (slot_arm.py) writes the rule for a sentence with exactly one limit on one quantity. Real requirements are rarely that
tidy: "Habitable rooms must be min. 70 sq ft except kitchens, also min. 7 ft in any dimension", "Risers max. 8 1/4 in, treads min.
9 in", "1 egress door required min. 32 in". This arm generalises the same method, so a small model only chooses and a program writes:

  limits       every quantity with its own comparison wording, read by program (never a range, an "or", a negation or a condition)
  exception    "except kitchens": the model names the excluded categories; they are removed from the rule's scope
  quantifier   every member, or at least one ("1 egress door"); asked twice, with the options in both orders, and only believed when
               both answers agree
  filter       a yes or no property that narrows the members ("exit door" is a door that leads to the outside), same double ask
  quantity     for each limit, the model chooses the fact it limits among the collection's numeric facts, or none

A limit whose quantity the plan does not provide (the riser height of a stair) is not guessed and does not sink the sentence: it is
listed in the rule's `not_checked` and the rule covers the rest. A violation of the covered part is a violation, and the rule never
reports "satisfied" while a part is unchecked (interpreter/runtime.py). Everything written goes through the same compile, validate
and sentence checks as a rule the model wrote itself.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from ..interpreter.grounding import NONE, pick
from .drafters import Draft, citation, context_for
from .expr_arms import _build, _stage
from .relation_arm import _choose_many
from .slot_arm import NEGATION, OPS, _categories, _choose, _describe_collection, confirm_named
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

LIMITS_ARMS = ("expr_limits",)
EXCEPTION = re.compile(r"\b(except|excepted|excluding|other than|sauf|excepté|hormis|ausgenommen|außer|ausser|excepto|salvo|tranne|"
                       r"behalve)\b", re.I)
CONDITION = re.compile(r"\b(if|when|where|unless|provided|whereas|lorsque|lorsqu|quand|si|dès lors|wenn|falls|sofern|cuando|quando|"
                       r"indien|als)\b", re.I)
DISJUNCTION = re.compile(r"\b(or|ou|oder|o|ovvero|bzw|ofwel)\b", re.I)


@dataclass
class Limit:
    op: str
    literal: str
    fragment: str
    count: bool = False             # a number of things, not a measure: it limits a count fact, whatever the unit-less number says


@dataclass
class Reading:
    limits: list[Limit]
    exception: str | None
    main: str
    existential: bool


def read_limits(text: str) -> Reading | None:
    """The limits of a sentence, each with its own comparison, an exception clause if any, and whether it asks for "at least one".
    None whenever the sentence is not this shape: the free-form arm then reads it."""
    flat = prepare(text)
    lang = detect_language(flat)
    if lang is None or lang not in wording():
        return None
    exception, main = None, flat
    m = EXCEPTION.search(flat)
    if m:
        end = next((i for i, ch in enumerate(flat[m.end():], m.end()) if ch in ",;."), len(flat))
        exception, main = flat[m.start():end], (flat[:m.start()] + " " + flat[end:]).strip()
    if CONDITION.search(main):
        return None
    comma = _decimal_comma(lang, main)
    qs = sorted((q for q in quantities(main, comma) if q.unit != "ratio"), key=lambda q: q.span)
    spans = number_spans(main, comma)
    if len({q.span for q in qs}) != len(qs):                  # a range ("between 0.9 and 1.3 m")
        return None
    covered = {q.span for q in qs}
    # counts: a number with no unit. With a comparison cue it is a limit on a count ("at least one exit", "no more than 3 storeys");
    # a bare 1 without one only says "one of them" ("1 egress door required"). A spelled number counts only with its cue, because in
    # several languages the word for one is also the indefinite article ("une porte").
    counts, existential = [], False
    candidates = [(s[0], s[1], s[2], False) for s in spans if not any(a <= s[1] and s[2] <= b for a, b in covered)]
    for word, n in wording()[lang].get("numbers", {}).items():
        for w in re.finditer(rf"(?<![^\W\d_]){re.escape(word)}(?![^\W\d_])", main, re.I):
            candidates.append((float(n), w.start(), w.end(), True))
    for value, start, end, spelled in sorted(candidates, key=lambda c: c[1]):
        op = _expected_operator(main, start, end, lang)
        if op in OPS:
            counts.append((start, end, op, f"{value:g}"))
        elif not spelled and abs(value - 1.0) < 1e-9 and not existential:
            existential = True
        elif not spelled:
            return None                  # a number the sentence states and no comparison explains
    if not qs and not counts:
        return None
    items = [(q.span[0], q.span[1], _expected_operator(main, q.span[0], q.span[1], lang), f"{q.value:g} {q.unit}".strip(), False)
             for q in qs] + [(a, b, op, lit, True) for a, b, op, lit in counts]
    items.sort(key=lambda t: t[0])
    if len({(a, b) for a, b, *_ in items}) != len(items):
        return None
    limits, prev_end = [], 0
    for start, end, op, literal, is_count in items:
        if op is None and len(items) == 1:
            found = {o for pattern, o in _cue_regexes(lang) for _ in pattern.finditer(main.lower())}
            op = found.pop() if len(found) == 1 else None
        if op not in OPS:
            return None
        if DISJUNCTION.search(main[prev_end:start]) and prev_end:            # two alternatives, not two limits
            return None
        limits.append(Limit(op, literal, main[prev_end:min(end + 14, len(main))].strip(" ,;."), is_count))
        prev_end = end
    bare = main
    for pattern, _ in _cue_regexes(lang) + _after_regexes(lang):
        bare = re.sub(pattern.pattern, " ", bare, flags=re.I)
    for cue in sum((wording()[lang].get(k, []) for k in ("ge", "le", "gt", "lt", "after_le", "after_ge")), []):
        bare = re.sub(re.escape(cue), " ", bare, flags=re.I)
    if NEGATION.search(bare):
        return None
    return Reading(limits, exception, main, existential)


def _stable(client, question: str, options: dict[str, str]) -> str | None:
    """A choice believed only when it is the same with the options in both orders (a small model has a position bias)."""
    first = _choose(client, question, options)
    second = _choose(client, question, dict(reversed(list(options.items()))))
    return first if first is not None and first == second and first != NONE else None


def _excluded(client, clause: str, values: list[str], groups: dict[str, list[str]]) -> list[str] | None:
    """The categories an exception clause leaves out ("except kitchens"). Asked as what is excluded: asked as "which things does it
    apply to", a model rightly answers that the clause names no thing the limit applies to."""
    options = {v: v.replace("_", " ") for v in values} | {g: f"{g} (a group: {', '.join(vs)})" for g, vs in groups.items()}
    ask = ("A requirement has an exception. The exception clause says which kinds of thing the requirement does NOT apply to. Which of "
           "these categories are excluded by the clause? Choose only categories it names or clearly means. Reply with JSON only.\n"
           "Exception clause: " + clause[:300])
    return _choose_many(client, ask, {"categories": options}, list(options))


def draft_limits(arm: str, item, client) -> Draft:
    t0 = time.time()
    ctx, cat = (getattr(item, "ctx", None) or context_for(item)), item.catalogue

    def skip(why: str) -> Draft:
        return Draft(arm, None, "skip", why, time.time() - t0)

    reading = read_limits(item.text)
    if reading is None:
        return skip("not a sentence of limits this arm can read")
    bindings, collections = bindings_of(cat), list(cat["collections"])
    whole = cat.get("whole") or "building"
    options = {c: _describe_collection(cat, c) for c in collections}
    if cat.get("building"):
        options["whole"] = f"the {whole} as a whole: " + "; ".join(
            cat["bindings"].get(f, {}).get("description", f) for f in cat["building"][:4])
    got = _choose(client, "A sentence from a requirements document (in any language) limits measured quantities. Which kind of thing "
                  "does it limit? Choose the option the sentence is about, or none if the plan provides no such thing.\nSentence: "
                  + reading.main[:600], options)
    if got is None or got == NONE:
        return skip("no kind of thing chosen")
    facts, owner = (list(cat["building"]), None) if got == "whole" else (list(cat["collections"][got].get("facts", [])), got)
    numeric = {f: cat["bindings"][f].get("description", f) for f in facts if cat["bindings"].get(f, {}).get("kind") == "number"}
    counted = {f: d for f, d in numeric.items() if cat["bindings"][f].get("unit") in ("count", "1")}     # numbers of things
    measured = {f: d for f, d in numeric.items() if f not in counted}
    covered, not_checked = [], []
    for limit in reading.limits:
        fact = pick(client, limit.fragment, counted if limit.count else measured)
        if fact is None or fact == NONE:
            not_checked.append(limit.fragment)
        else:
            covered.append((fact, limit))
    if not covered:
        return skip(f"the plan provides none of the quantities the sentence limits (read as {got}: "
                    f"{', '.join(counted if reading.limits[0].count else measured) or 'no numeric fact'})")
    where: list[str] = []
    if owner is not None:
        kind_facts = [f for f in facts if f in (cat.get("kinds") or {})]
        if kind_facts:
            kf = kind_facts[0]
            groups = ((cat.get("groups") or {}).get(kf)) or {}
            members = {g: list(v) for g, v in groups.items()}
            chosen = _categories(client, reading.main, list(cat["kinds"][kf]), groups)
            if chosen is None:
                return skip("categories not answered")
            chosen = confirm_named(client, reading.main, cat, kf, groups, chosen)
            chosen = [v for c in chosen for v in members.get(c, [c])]
            if chosen:
                where.append("(" + " or ".join(f"v.{kf} == '{c}'" for c in sorted(set(chosen))) + ")")
            if reading.exception:
                excluded = _excluded(client, reading.exception, list(cat["kinds"][kf]), groups)
                excluded = [v for c in (excluded or []) for v in members.get(c, [c])]
                if not excluded:
                    return skip("the exception was not understood")
                where += [f"v.{kf} != '{c}'" for c in sorted(set(excluded))]
        elif reading.exception:
            return skip("an exception, but the plan has no categories to exclude")
        flags = {f: cat["bindings"][f].get("description", f) for f in facts
                 if cat["bindings"].get(f, {}).get("kind") == "boolean" and not f.startswith(("reaches_", "links_"))}
        if flags:
            flag = _stable(client, "A sentence (in any language) is about some things. Does it narrow them by one of these yes or no "
                           "properties (for example an 'exit door' is a door that leads to the outside)? Choose none if it does "
                           f"not.\nSentence: {reading.main[:600]}", flags)
            if flag:
                where.append(f"v.{flag} == true")
        quantifier = "some" if reading.existential else (_stable(
            client, "Must every one of these things meet the requirement, or at least one of them? "
                    f"Sentence: {reading.main[:600]}", {"every": "every one of them", "some": "at least one of them"}) or "every")
    conj = " and ".join(f"{'v' if owner else whole}.{fact} {OPS[lim.op]} {lim.literal}" for fact, lim in covered)
    if owner is None:
        require = conj
    else:
        head = ("exists" if quantifier == "some" else "forall") + f" {owner} v"
        require = f"{head}{' where ' + ' and '.join(where) if where else ''}: {conj}"
    raw = {"title": "limits", "applies_when": None, "unless": None, "require": require, "not_checked": not_checked,
           "sources": [{"clause": ctx.target, "quote": citation(item)}], "unresolved": []}

    def check(prog):
        return verify(prog, item.text, cat, getattr(item, "lang", None), grounding_words=False)

    try:
        program = _build(raw, ctx, bindings, collections, {whole}, check, cat.get("kinds"), cat.get("passable"), cat)
    except Exception as exc:  # noqa: BLE001 - a wrong choice is caught by the same checks as any draft
        return Draft(arm, None, _stage(exc), f"{type(exc).__name__}: {str(exc)[:250]}", time.time() - t0, raw)
    if blocking(check(program)):
        return skip("the checks refused the assembled rule")
    return Draft(arm, program, "ok", f"limits:{len(covered)} of {len(reading.limits)}", time.time() - t0, raw)
