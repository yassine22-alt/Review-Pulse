"""A rule in plain words, built only from the rule and the facts' own descriptions.

A reviewer approves what they understand. The one-line expression is exact but reads like code; this renders the same rule
as a sentence ("For every room where room type is bedroom: floor area is at least 9 m2 and minimum width is at least 2.2
m") using the description each fact carries in the fact graph. Nothing here knows a domain: a network reads "For every
component where type is tank: volume is at least 500 L".

  plain(rule_expr, bindings, whole)   the sentence for one expression (a dict as in Program.model_dump)
"""

from __future__ import annotations

OPS = {"ge": "is at least", "le": "is at most", "gt": "is more than", "lt": "is less than", "eq": "is", "ne": "is not"}


def _singular(collection: str) -> str:
    return collection[:-1] if collection.endswith("s") and len(collection) > 3 else collection


def _fact_words(name: str, bindings: dict) -> str:
    desc = (bindings.get(name) or {}).get("description") or name.replace("_", " ")
    return desc.split(" (")[0].strip().lower()


def _value(node: dict) -> str:
    v, unit = node["value"], node.get("unit", "1")
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    text = f"{v:g}"
    return text + (f" {unit}" if unit not in ("1", "count") else "")


def plain(node: dict, bindings: dict, whole: str = "building") -> str:
    kind = node["node"]
    if kind == "literal":
        return _value(node)
    if kind == "fact":
        words = _fact_words(node["name"], bindings)
        owner = node["entity"].lstrip("$")
        if owner == whole:
            return f"the {whole}'s {words}" if not words.startswith(("the ", "number", "total")) else words
        return words
    if kind in ("all", "any"):
        parts = [plain(a, bindings, whole) for a in node["args"]]
        return (" and " if kind == "all" else " or ").join(parts if len(parts) < 3 else [f"({p})" for p in parts])
    if kind == "not":
        return f"it is not true that {plain(node['args'][0], bindings, whole)}"
    if kind in OPS:
        left, right = node["left"], node["right"]
        if kind in ("eq", "ne") and right.get("node") == "literal" and isinstance(right["value"], bool):
            text = plain(left, bindings, whole)
            return text if right["value"] == (kind == "eq") else f"it is not true that {text}"
        return f"{plain(left, bindings, whole)} {OPS[kind]} {plain(right, bindings, whole)}"
    if kind in ("add", "sub", "mul", "div"):
        sign = {"add": "plus", "sub": "minus", "mul": "times", "div": "divided by"}[kind]
        return f"{plain(node['left'], bindings, whole)} {sign} {plain(node['right'], bindings, whole)}"
    if kind in ("forall", "exists", "count", "sum", "min", "max"):
        what = _singular(node["collection"])
        where = f" where {plain(node['where'], bindings, whole)}" if node.get("where") else ""
        if kind == "forall":
            return f"for every {what}{where}: {plain(node['body'], bindings, whole)}"
        if kind == "exists":
            return f"there is at least one {what}{where} where {plain(node['body'], bindings, whole)}"
        if kind == "count":
            return f"the number of {node['collection']}{where}"
        label = {"sum": "the total", "min": "the smallest", "max": "the largest"}[kind]
        return f"{label} {plain(node['body'], bindings, whole)} of the {node['collection']}{where}"
    if kind == "path_exists":
        text = f"{node['origin'].lstrip('$')} has a route to {node['destination'].lstrip('$').lower()}"
        flt = node.get("node_filter")
        if flt:
            args = flt["args"] if flt.get("node") == "all" else [flt]
            avoided = [a["right"]["value"] for a in args if a.get("node") == "ne" and a["right"].get("node") == "literal"]
            if len(avoided) == len(args):
                text += f" without passing through {', '.join(avoided)}"
            else:
                text += f" passing only through those where {plain(flt, bindings, whole)}"
        return text
    if kind == "linked":
        return f"{node['a'].lstrip('$')} and {node['b'].lstrip('$')} are joined directly"
    return kind


def describe_rule(requirement: dict, applicability: dict | None, exemption: dict | None, bindings: dict,
                  whole: str = "building") -> dict:
    """{plain, applies_when, unless}: each as a sentence, or None when the condition is the trivial true / false."""
    def trivial(n, value):
        return n is None or (n.get("node") == "literal" and n.get("value") is value)

    text = plain(requirement, bindings, whole)
    return {"plain": text[:1].upper() + text[1:] + ".",
            "plain_applies_when": None if trivial(applicability, True) else plain(applicability, bindings, whole),
            "plain_unless": None if trivial(exemption, False) else plain(exemption, bindings, whole)}
