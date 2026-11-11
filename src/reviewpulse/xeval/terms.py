"""How a document names categories: synonyms, other languages, and groups the document itself defines.

A rule may only compare a category fact with a declared value. Documents rarely use the declared value itself: they write
"WC" for a bathroom, "living room", "chambre", and they define their own groups ("habitable room (bedroom, living room,
kitchen)") and then use the group's name in later clauses. This module maps those words to declared values, using only
data: the producer's label table (`value_labels`, any language) and the document's own text. Nothing here knows a domain.

  normalise_value   a word -> the declared value whose labels contain it (or None)
  document_groups   parenthesised enumerations in the text whose items all name values of one category fact:
                    "habitable room (bedroom, living room, kitchen)" -> {"habitable room": ["bedroom", "kitchen", "living"]}
  resolve_terms     rewrites a compiled rule: synonyms become declared values, a group becomes the set of its values
"""

from __future__ import annotations

import re

LIST_SPLIT = re.compile(r"\s*(?:,|;|/|\band\b|\bor\b|\bet\b|\bou\b|\bund\b|\boder\b|\by\b|\bo\b|\be\b|\ben\b|\boch\b|\beller\b)\s*",
                        re.I)
ENUMERATION = re.compile(r"([^\W\d_][^\W\d_'’-]*(?:\s+[^\W\d_][^\W\d_'’-]*){0,3})\s*\(([^()]{3,200})\)")


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().strip(".:;,"))


def normalise_value(word: str, fact: str, kinds: dict, labels: dict) -> str | None:
    """The declared value of `fact` that `word` names, through the value itself or any of its labels."""
    declared = kinds.get(fact, [])
    w = _key(word)
    for value in declared:
        if w == _key(value) or w == _key(value.replace("_", " ")):
            return value
    hits = {value for value in declared for label in labels.get(fact, {}).get(value, [])
            if w == _key(label) or w.rstrip("s") == _key(label)}
    return hits.pop() if len(hits) == 1 else None


def document_groups(text: str, kinds: dict, labels: dict) -> dict[str, dict[str, list[str]]]:
    """Per category fact, the groups the document defines by enumeration: {fact: {term: [values]}}."""
    out: dict[str, dict[str, list[str]]] = {}
    for m in ENUMERATION.finditer(text):
        items = [i for i in LIST_SPLIT.split(m.group(2)) if i and i.strip()]
        if len(items) < 2:
            continue
        for fact in kinds:
            values = [normalise_value(i, fact, kinds, labels) for i in items]
            if all(values) and len(set(values)) >= 2:
                term = _strip_function_words(_key(m.group(1)))
                if term:
                    out.setdefault(fact, {})[term] = sorted(set(values))
                break
    return out


def _strip_function_words(term: str) -> str:
    """"every habitable room" -> "habitable room": leading function words of any language with a wording table go."""
    from .verify import wording

    common = {w for spec in wording().values() for w in spec.get("words", [])}
    words = term.split()
    while words and words[0] in common:
        words.pop(0)
    return " ".join(words)


def _group_values(word: str, fact: str, groups: dict) -> list[str] | None:
    w = _key(word)
    for term, values in groups.get(fact, {}).items():
        words = term.split()
        # "habitable room" is also written "habitable", and in the plural "habitable rooms"
        if w in (term, term + "s", words[0]) or (len(words) > 1 and w == " ".join(words[:-1])):
            return values
    return None


def resolve_terms(node, kinds: dict, labels: dict, groups: dict) -> None:
    """Rewrite comparisons of a category fact with a word, in place: synonym -> value, group -> its values."""
    if isinstance(node, list):
        for child in node:
            resolve_terms(child, kinds, labels, groups)
        return
    if not isinstance(node, dict):
        return
    for child in list(node.values()):
        if isinstance(child, (dict, list)):
            resolve_terms(child, kinds, labels, groups)
    if "_avoid" in node:
        expanded: list[str] = []
        for word in node["_avoid"]:
            for fact in kinds:
                value = normalise_value(word, fact, kinds, labels)
                group = _group_values(word, fact, groups)
                if value or group:
                    expanded += [value] if value else group
                    break
            else:
                expanded.append(word)              # left as written: the compiler refuses an undeclared value
        node["_avoid"] = sorted(set(expanded), key=expanded.index)
    if node.get("node") not in ("eq", "ne"):
        return
    for fact_side, lit_side in (("left", "right"), ("right", "left")):
        fact, lit = node.get(fact_side, {}), node.get(lit_side, {})
        if fact.get("node") != "fact" or lit.get("node") != "literal" or not isinstance(lit.get("value"), str):
            continue
        name = fact.get("name")
        if name not in kinds or lit["value"] in kinds[name]:
            return
        value = normalise_value(lit["value"], name, kinds, labels)
        if value:
            lit["value"] = value
            return
        group = _group_values(lit["value"], name, groups)
        if group:
            op = node["node"]
            tests = [{"node": op, "left": fact, "right": {"node": "literal", "value": v, "unit": "1"}} for v in group]
            node.clear()
            node.update(tests[0] if len(tests) == 1 else {"node": "any" if op == "eq" else "all", "args": tests})
        return
