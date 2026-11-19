"""Auditable surface normalization; never link synonyms or invent missing scope."""
from __future__ import annotations

import copy
import re

from .expr_ir import SYMBOL

_PARTS = re.compile(r"('[^']*'|\"[^\"]*\")")
_IDENT = re.compile(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)(?![\w.])")


def normalize_expressions(raw: dict, catalogue: dict) -> tuple[dict, list[dict]]:
    """Qualify only catalogue facts owned exclusively by the global entity.

    No collection variable is invented. Quoted strings are opaque. Each changed
    field has a before/after trace; compilation, units, source grounding and
    round-trip verification remain the caller's responsibility.
    """
    result, trace = copy.deepcopy(raw), []
    local = {name for spec in catalogue.get("collections", {}).values() for name in spec.get("facts", [])}
    global_names = set(catalogue.get("building", [])) - local
    owner = catalogue.get("whole") or "building"
    for field in ("require", "applies_when", "unless"):
        original = result.get(field)
        if not isinstance(original, str):
            continue
        text, reasons = original, []
        fence = re.fullmatch(r"\s*```(?:text|expression)?\s*\n(.*?)\n```\s*", text, re.S)
        if fence:
            text = fence[1]
            reasons.append("outer_code_fence")
        parts = _PARTS.split(text)
        bound_names = set(re.findall(r"\b(?:forall|exists|count|sum|min|max)\s*\(?\s*\w+\s+(\w+)",
                                     " ".join(parts[::2])))
        for index in range(0, len(parts), 2):
            part = parts[index]
            replaced = part.translate(str.maketrans({"≥": ">=", "≤": "<=", "≠": "!="}))
            if replaced != part:
                reasons.append("unicode_comparator")
            part = replaced
            # Named binary comparison operators have the same supplied contract
            # meaning. Match only between operands, never qualified fact names.
            for name in ("ge", "gt", "le", "lt", "eq", "ne"):
                part, count = re.subn(r"(?<=[\w)\]])\s+" + name + r"\s+(?=[\w('\"])",
                                      " " + SYMBOL[name] + " ", part)
                if count:
                    reasons.append("named_comparator")

            def qualify(match, bound_names=bound_names, reasons=reasons):
                name = match[1]
                if name in global_names and name not in bound_names:
                    reasons.append("unique_global_fact_qualification")
                    return owner + "." + name
                return name

            parts[index] = _IDENT.sub(qualify, part)
        text = "".join(parts)
        if text != original:
            result[field] = text
            trace.append({"field": field, "before": original, "after": text,
                          "operations": sorted(set(reasons))})
    return result, trace
