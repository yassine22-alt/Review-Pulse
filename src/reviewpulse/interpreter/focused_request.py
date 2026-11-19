"""Bounded catalogue retrieval and finite strict wire schemas, without gold labels."""
from __future__ import annotations

import copy
import re
import unicodedata


def words(text: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return {word for word in re.findall(r"[^\W_]+", folded) if len(word) >= 3}


def focus_catalogue(catalogue: dict, text: str, top_k: int = 6) -> tuple[dict, dict]:
    """Lexical recall is finite: a missed fact must be declared/reviewed, never guessed.

    The returned catalogue contains types/descriptions only; callers compile
    against the full authoritative catalogue. No plan values or gold are used.
    """
    result = copy.deepcopy(catalogue)
    query = words(text)
    scored = [(len(query & words(name + " " + spec.get("description", ""))), name)
              for name, spec in catalogue["bindings"].items()]
    selected = {name for score, name in sorted(scored, key=lambda row: (-row[0], row[1]))[:top_k] if score}
    result["bindings"] = {name: spec for name, spec in result["bindings"].items() if name in selected}
    result["building"] = [name for name in result.get("building", []) if name in selected]
    result["collections"] = {name: {**spec, "facts": [fact for fact in spec.get("facts", []) if fact in selected]}
                             for name, spec in result.get("collections", {}).items()}
    result["collections"] = {name: spec for name, spec in result["collections"].items() if spec["facts"]}
    result["kinds"] = {name: values for name, values in result.get("kinds", {}).items() if name in selected}
    result["kind_labels"] = {name: {kind: [alias for alias in aliases if words(alias) & query]
                                  for kind, aliases in values.items()}
                             for name, values in result.get("kind_labels", {}).items() if name in selected}
    return result, {"method": "lexical type-vocabulary overlap, no gold or plan values", "top_k": top_k,
                    "selected": sorted(selected), "omitted": sorted(set(catalogue["bindings"]) - selected),
                    "risk": "Retrieval can omit relevant facts; declarations or review required on gaps"}


def finite_strict_schema(schema: dict) -> dict:
    """Inline finite local refs. Make nullable optional node references explicit.

    Non-null optional values (e.g. a literal's unit) become required explicitly,
    so no new null/default meaning is introduced. Recursive refs are refused.
    """
    definitions = schema.get("$defs", {})

    def expand(value, trail=()):
        if isinstance(value, list):
            return [expand(item, trail) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            ref = value["$ref"]
            if not ref.startswith("#/$defs/") or ref in trail:
                raise ValueError("strict wire contract needs finite local references")
            base = definitions[ref.rsplit("/", 1)[-1]]
            return expand({**base, **{key: item for key, item in value.items() if key != "$ref"}}, (*trail, ref))
        result = {key: ({name: expand(spec, trail) for name, spec in item.items()}
                        if key == "properties" else expand(item, trail)) for key, item in value.items()
                  if key not in ("$defs", "title", "description", "examples", "default")}
        if "anyOf" in result and {"type": "number"} in result["anyOf"]:
            # JSON Schema number includes integers. This union is losslessly
            # simplified; Groq rejects the overlapping scalar alternatives.
            result["anyOf"] = [choice for choice in result["anyOf"] if choice != {"type": "integer"}]
        if "anyOf" in result:
            strings = [choice for choice in result["anyOf"] if choice.get("type") == "string"]
            if len(strings) > 1:
                if any(set(choice) - {"type", "pattern", "enum"} for choice in strings):
                    raise ValueError("Cannot losslessly merge constrained string alternatives")
                if {"type": "string"} in strings:
                    merged = {"type": "string"}
                else:
                    patterns = []
                    for choice in strings:
                        pattern = choice.get("pattern")
                        if "enum" in choice:
                            values = [value for value in choice["enum"] if pattern is None or re.search(pattern, value)]
                            patterns.append("^(?:" + "|".join(re.escape(value) for value in values) + ")$")
                        elif pattern is not None:
                            patterns.append(pattern)
                    merged = {"type": "string", "pattern": "|".join("(?:" + pattern + ")" for pattern in patterns)}
                result["anyOf"] = [choice for choice in result["anyOf"] if choice.get("type") != "string"] + [merged]
        if "oneOf" in result:
            # Provider strict schemas support anyOf. It is equivalent here only
            # because required operation enums make node alternatives disjoint.
            seen = set()
            for choice in result["oneOf"]:
                operations = set(choice.get("properties", {}).get("op", {}).get("enum", []))
                if "op" not in choice.get("required", []) or not operations or seen & operations:
                    raise ValueError("Cannot losslessly convert overlapping strict-schema alternatives")
                seen.update(operations)
            result["anyOf"] = result.pop("oneOf")
        if result.get("type") == "object":
            properties = result.get("properties", {})
            required = set(value.get("required", []))
            for name, spec in properties.items():
                if name not in required and name in ("where", "node_filter", "edge_filter"):
                    properties[name] = {"anyOf": [spec, {"type": "null"}]}
            result.update(required=list(properties), additionalProperties=False)
        return result

    return expand(schema)
