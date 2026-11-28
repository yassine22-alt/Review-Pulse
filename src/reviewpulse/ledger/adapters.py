"""Adapters: the fact sources that exist today, seen as producers.

The fact graph written by `factgraph/from_building.py` holds three kinds of value side by side: measured from geometry,
read from a schedule, counted in the sheet's notes. Here each kind becomes its own producer (its own family, its own kind of
evidence), all reading the same graph, so the ledger can later fuse them with producers that read other places (a
dimension string, a legend, a vision model) without any change to what exists.

A producer answers by meaning: it answers a request whose fact has the same name, or, failing that, a property of the same
kind and dimension whose name and description hold every word the request asks for (a lower score, because it is a guess
that the two mean the same). A reviewer's attestation store is a producer too.
"""

from __future__ import annotations

from ..factgraph.from_building import NOTE_BINDINGS
from ..factgraph.schema import FactGraph, Node, collection_name
from ..interpreter.schema import Binding
from .candidate import Candidate, EvidenceKind
from .producer import meaning_score
from .request import KIND_OF_BINDING, FactRequest

TRUSTED_SCORE = 0.95        # a value the plan reader marks trusted: above the ledger's acceptance threshold on its own
UNTRUSTED_SCORE = 0.5       # a value read but not trusted: kept, below the threshold until another family agrees
ALIAS_DISCOUNT = 0.8        # a property matched by meaning instead of by name: alone it stays below the threshold

SCHEDULE_FACTS = frozenset({"height_m", "sill_height_m", "fire_rating_min", "tag", "opening_area_m2", "window_area_m2",
                            "window_area_ratio"})
LABEL_FACTS = frozenset({"room_type", "has_label"})
NOTE_FACTS = frozenset(NOTE_BINDINGS) | {"scale_stated", "dimension_count", "is_dimensioned"}


class FactGraphProducer:
    """The values of a fact graph restricted to some attribute names, with the kind of evidence they are."""

    def __init__(self, fg: FactGraph, *, name: str, family: str, kind: EvidenceKind,
                 only: frozenset[str] | None = None, exclude: frozenset[str] = frozenset()):
        self.fg, self.name, self.family, self.kind = fg, name, family, kind
        self.names = {n for n in fg.bindings if (only is None or n in only) and n not in exclude}

    def _targets(self, request: FactRequest) -> list[Node]:
        if request.entity:
            return [n for n in self.fg.nodes if n.id == request.entity]
        wanted = request.entity_kind
        return [n for n in self.fg.nodes if wanted is None or wanted in (n.kind, collection_name(n.kind))]

    def _match(self, node: Node, request: FactRequest) -> tuple[str, float] | None:
        """The attribute of the node that answers the request and how well: its own name first, then by meaning."""
        if request.fact in self.names and request.fact in node.attrs:
            return (request.fact, 1.0) if meaning_score(request, request.fact, self.fg.bindings[request.fact]) else None
        best: tuple[str, float] | None = None
        for attr in node.attrs:
            if attr in self.names and attr != request.fact:
                score = meaning_score(request, attr, self.fg.bindings[attr])
                if score >= 1.0 and (best is None or len(attr) < len(best[0])):
                    best = (attr, ALIAS_DISCOUNT)
        return best

    def holds(self, request: FactRequest) -> float:
        return max((m[1] for n in self._targets(request) if (m := self._match(n, request))), default=0.0)

    def answer(self, request: FactRequest) -> list[Candidate]:
        out = []
        for node in self._targets(request):
            match = self._match(node, request)
            if match is None:
                continue
            attr, weight = match
            fact, binding = node.attrs[attr], self.fg.bindings[attr]
            score = (TRUSTED_SCORE if fact.trusted else UNTRUSTED_SCORE) * weight
            out.append(Candidate(
                entity=node.id, fact=attr, value=fact.value, unit=binding.unit, kind=self.kind, source=fact.source,
                sheet=self.fg.provenance.sheet, producer=self.name, family=self.family,
                score=score if fact.value is not None else 0.0))
        return out


def fact_graph_producers(fg: FactGraph) -> list[FactGraphProducer]:
    """Today's fact sources as three producers: schedule, notes, and geometry (everything the other two do not claim)."""
    claimed = SCHEDULE_FACTS | NOTE_FACTS | LABEL_FACTS
    return [
        FactGraphProducer(fg, name="schedule", family="schedule", kind="stated", only=SCHEDULE_FACTS),
        FactGraphProducer(fg, name="notes", family="text", kind="stated", only=NOTE_FACTS),
        FactGraphProducer(fg, name="labels", family="text", kind="stated", only=LABEL_FACTS),
        FactGraphProducer(fg, name="geometry", family="geometry", kind="measured", exclude=claimed),
    ]


class Attestations:
    """What reviewers have confirmed: a named person, a source, one value for one fact of one entity."""

    name, family = "attestation", "reviewer"

    def __init__(self):
        self.entries: list[Candidate] = []

    def attest(self, entity: str, fact: str, value, *, reviewer: str, source: str, unit: str = "1") -> Candidate:
        entry = Candidate(entity=entity, fact=fact, value=value, unit=unit, kind="attested", source=source,
                          reviewer=reviewer, score=1.0, producer=self.name, family=self.family)
        self.entries.append(entry)
        return entry

    def holds(self, request: FactRequest) -> float:
        return 1.0 if any(self._fits(e, request) for e in self.entries) else 0.0

    def _fits(self, e: Candidate, request: FactRequest) -> bool:
        return e.fact == request.fact and (request.entity is None or e.entity == request.entity)

    def answer(self, request: FactRequest) -> list[Candidate]:
        return [e for e in self.entries if self._fits(e, request)]


def binding_request(entity: str | None, name: str, binding: Binding, *, entity_kind: str | None = None, words: str = "",
                    clause: str = "") -> FactRequest:
    """The typed request for a property the interpreter already declares (kind and unit come from the binding)."""
    return FactRequest(entity=entity, entity_kind=entity_kind, fact=name, kind=KIND_OF_BINDING[binding.kind],
                       unit=binding.unit, words=words, clause=clause)
