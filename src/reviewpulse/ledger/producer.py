"""The producer protocol: something that can answer fact requests, declared by meaning."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from ..interpreter.schema import Binding
from ..interpreter.units import compatible
from .candidate import Candidate
from .request import KIND_OF_BINDING, FactRequest

_UNIT_WORDS = {"m", "m2", "mm", "cm", "min", "count", "ratio", "of", "the", "a", "an", "in", "is", "to", "and", "or", "for", "from",
               "its", "by", "at", "on", "with", "per"}


@runtime_checkable
class Producer(Protocol):
    """`holds(request)` says how well the request matches something this producer can answer (0 means nothing), judged by
    meaning, so a producer is never limited to the names a requirement happens to use. `answer(request)` returns every
    candidate it has for the request, each with its source; an empty list means it cannot answer."""

    name: str
    family: str

    def holds(self, request: FactRequest) -> float: ...

    def answer(self, request: FactRequest) -> list[Candidate]: ...


def tokens(text: str) -> set[str]:
    words = re.split(r"[^a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "").lower())
    return {w.rstrip("s") if len(w) > 3 else w for w in words if w and w not in _UNIT_WORDS}


def meaning_score(request: FactRequest, name: str, binding: Binding) -> float:
    """How well a declared property (name, kind, unit, description) answers a request: 1.0 for the same name, otherwise the
    share of the request's own words found in the property's name and description, and 0 when the kind of value or its
    dimension differs (an area never answers a length)."""
    if KIND_OF_BINDING[binding.kind] != request.kind:
        return 0.0
    if request.kind == "number" and not compatible(binding.unit, request.unit):
        return 0.0
    if name == request.fact:
        return 1.0
    wanted = tokens(request.fact) - tokens(request.entity_kind or "")
    if not wanted:
        return 0.0
    # the property may not say more than the request does: "area" is not "window_area", whatever the description holds
    if not tokens(name) <= wanted | tokens(request.entity_kind or ""):
        return 0.0
    held = tokens(name) | tokens(binding.description)
    return round(len(wanted & held) / len(wanted), 4) if wanted <= held else 0.0
