"""Checks and normalisations that need no sentence: they use only the declared catalogue.

  check_owners    a member fact must belong to the collection of its variable; a building fact to the building
  check_values    a text value compared with a category fact must be one of that fact's declared values
  hoist           a condition that mentions no member (e.g. "building.storeys > 2") belongs in applies_when, not
                  inside the filter of a forall: the result then reads NOT_APPLICABLE instead of a vacuous pass

These are properties of any rule over any catalogue. Nothing here knows about a project type or a language.
"""

from __future__ import annotations

import copy

from ..interpreter.schema import Program
from .verify import Issue

SETS = ("forall", "exists", "count", "sum", "min", "max")


def _walk(node, scope: dict, out: list):
    """Visit every node with the variable-to-collection scope in force at that point."""
    if isinstance(node, list):
        for child in node:
            _walk(child, scope, out)
        return
    if not isinstance(node, dict):
        return
    out.append((node, scope))
    inner = scope
    if node.get("node") == "path_exists" and node.get("node_filter"):
        # the room being passed through is a member of the same collection as the room the route starts from
        _walk(node["node_filter"], {**scope, "$node": scope.get(node.get("origin", ""))}, out)
    if node.get("node") in SETS:
        inner = {**scope, node["variable"]: node["collection"]}
    for key, child in node.items():
        if key == "node_filter":
            continue                      # walked above, with the passed-through room in scope
        if key == "where" or key == "body":
            _walk(child, inner, out)
        elif isinstance(child, (dict, list)):
            _walk(child, scope if node.get("node") not in SETS else inner, out)


def _nodes(program: Program) -> list:
    out: list = []
    data = program.model_dump(mode="json", exclude_none=True)
    for key in ("applicability", "exemption", "requirement"):
        if key in data:
            _walk(data[key], {}, out)
    return out


def check_owners(program: Program, cat: dict) -> list[Issue]:
    issues = []
    if "collections" not in cat:           # a catalogue that does not declare its members cannot be checked
        return issues
    building = set(cat.get("building", []))
    for node, scope in _nodes(program):
        if node.get("node") != "fact":
            continue
        entity, name = node.get("entity", ""), node.get("name", "")
        if entity.startswith("$"):
            coll = scope.get(entity)
            facts = set(cat["collections"].get(coll, {}).get("facts", [])) if coll else None
            if facts is not None and name not in facts:
                where = "a fact of the whole" if name in building else "not a fact of it"
                issues.append(Issue("fact_wrong_owner", f"'{name}' is {where}, but it is read from a member of "
                                                        f"{coll}; use {cat.get('whole') or 'the whole'}.{name} or one of {sorted(facts)}"))
        elif name not in building and entity not in ("", "$"):
            issues.append(Issue("fact_wrong_owner", f"'{name}' is not a fact of {entity}"))
    return issues


def check_values(program: Program, cat: dict) -> list[Issue]:
    issues, kinds = [], cat.get("kinds", {})
    for node, _ in _nodes(program):
        if node.get("node") not in ("eq", "ne"):
            continue
        sides = [node.get("left", {}), node.get("right", {})]
        for fact, lit in (sides, sides[::-1]):
            if fact.get("node") == "fact" and lit.get("node") == "literal" and isinstance(lit.get("value"), str) \
                    and fact.get("name") in kinds and lit["value"] not in kinds[fact["name"]]:
                issues.append(Issue("value_undeclared", f"'{lit['value']}' is not a declared value of "
                                                        f"{fact['name']}: {sorted(kinds[fact['name']])}"))
    return issues


def _mentions_member(node) -> bool:
    if isinstance(node, dict):
        if node.get("node") == "fact" and str(node.get("entity", "")).startswith("$"):
            return True
        return any(_mentions_member(v) for v in node.values())
    if isinstance(node, list):
        return any(_mentions_member(v) for v in node)
    return False


def hoist(tree: dict) -> dict:
    """Move member-free conjuncts of the root forall's filter into applicability. `tree` is a program as a dict."""
    req = tree.get("requirement") or {}
    where = req.get("where")
    if req.get("node") != "forall" or not where:
        return tree
    parts = where["args"] if where.get("node") == "all" else [where]
    moved = [p for p in parts if not _mentions_member(p)]
    if not moved:
        return tree
    tree = copy.deepcopy(tree)
    keep = [p for p in parts if _mentions_member(p)]
    if keep:
        tree["requirement"]["where"] = keep[0] if len(keep) == 1 else {"node": "all", "args": keep}
    else:
        del tree["requirement"]["where"]
    existing = tree.get("applicability")
    if existing and not (existing.get("node") == "literal" and existing.get("value") is True):
        moved = [existing] + moved
    tree["applicability"] = moved[0] if len(moved) == 1 else {"node": "all", "args": moved}
    return tree


# ---- is the rule about what the sentence is about? (words, no model) -------------------------------------------

import re  # noqa: E402

FILLER = {"the", "of", "a", "an", "and", "or", "m", "m2", "count", "entity", "number", "total", "clear", "net", "measured",
          "minimum", "maximum", "min", "max", "building", "is", "has", "per", "each", "for", "to", "in", "by", "with"}


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[^\W\d_]+", text.lower().replace("_", " ")) if len(w) > 2 and w not in FILLER}


def check_grounding_words(program: Program, text: str, cat: dict) -> list[Issue]:
    """Each fact the requirement measures must share a word stem with the sentence (its own name or description).

    Catches a rule that bounds an unrelated quantity because it was the nearest available fact: "the tread is at least
    270 mm" written as "every door is at least 0.27 m wide". It only runs for sentences in the language the catalogue
    is described in, and it errs towards UNRESOLVED: a sentence that uses a synonym is sent back, never passed.
    """
    sentence = _stems(text)
    issues = []
    for name in _requirement_facts(program):
        if name in cat.get("kinds", {}):
            continue
        desc = cat.get("bindings", {}).get(name, {}).get("description", "")
        words = _stems(name) | _stems(desc.replace("(", " ").replace(")", " "))
        if words and not (words & sentence):
            issues.append(Issue("not_grounded", f"the rule measures '{desc or name}', but the sentence never mentions "
                                                f"it (no shared word): the sentence may be about something this plan "
                                                f"does not provide"))
    return issues


def _requirement_facts(program: Program) -> list[str]:
    from ..interpreter.schema import FactExpr, walk

    names: list[str] = []
    for node in walk(program.requirement):
        if isinstance(node, FactExpr) and node.name not in names and str(node.entity).startswith("$"):
            names.append(node.name)
    return names
