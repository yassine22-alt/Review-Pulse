"""The evidence ledger: candidates from every producer are fused into one resolution per question.

Rules, in this order, each one visible in the result:

1. A candidate whose kind of value or dimension does not fit the request is rejected and listed (never converted into
   something it is not). Numbers in another compatible unit are converted to the unit of the request.
2. Reviewer attestations (a name and a source are required) outrank everything else. Two attestations that disagree are a
   conflict. Other candidates that disagree with an attestation stay listed as overridden, with their sources.
3. Without attestation, candidates that agree (numbers within the request's tolerance) form a cluster. Producers of one
   family count once; independent families combine as 1 - prod(1 - score), so agreement raises trust.
4. Two clusters that disagree are a conflict: no value is chosen, both sources are shown. A conflict is never resolved by
   score, by order or by majority.
5. A value whose fused trust is below `min_trust` is unverified: kept, shown, never used as a pass.
6. No candidate with a value is unknown. Unknown is never a pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from ..interpreter.schema import Fact, Scalar, scalar_kind
from ..interpreter.units import UnitError, convert
from .candidate import Candidate
from .producer import Producer
from .request import FactRequest

Status = Literal["resolved", "attested", "unverified", "conflict", "unknown"]
MIN_TRUST = 0.8
KIND_OF_SCALAR = {"boolean": "bool", "string": "category", "number": "number"}


@dataclass
class Resolution:
    request: FactRequest
    entity: str
    status: Status
    value: Scalar | None = None
    trust: float = 0.0
    source: str = ""
    accepted: list[Candidate] = field(default_factory=list)
    overridden: list[Candidate] = field(default_factory=list)
    rejected: list[tuple[Candidate, str]] = field(default_factory=list)
    note: str = ""

    @property
    def decided(self) -> bool:
        return self.status in ("resolved", "attested")

    def fact(self) -> Fact | None:
        """The interpreter's fact for this resolution; None when no producer answered at all (the fact stays absent)."""
        if self.status == "unknown" and not self.source:
            return None
        if self.status == "conflict":
            return Fact(value=None, source=self.source, trusted=False, conflicting=True)
        return Fact(value=self.value, source=self.source, trusted=self.decided)

    def followup(self) -> FactRequest | None:
        """The question that would settle it, for the reviewer, when producers could not."""
        if self.decided:
            return None
        reason = {"conflict": "conflicting", "unverified": "unverified"}.get(self.status, "missing")
        return self.request.model_copy(update={"entity": self.entity, "reason": reason, "why": self.explain()})

    def explain(self) -> str:
        """One line for a person: the value and every source, or the sources that disagree."""
        q = f"{self.entity}.{self.request.fact}"
        if self.status == "conflict":
            return f"{q}: sources disagree: " + "; ".join(
                f"{c.value} {c.unit if c.unit != '1' else ''}".strip() + f" ({c.kind}, {c.source})" for c in self.accepted)
        if self.status == "unknown":
            return f"{q}: no producer could answer" + (f" ({self.note})" if self.note else "")
        return f"{q} = {self.value} (trust {self.trust:.2f}, {self.status}): {self.source}"


def _same(a: Scalar, b: Scalar, tol: float) -> bool:
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a.strip().casefold() == b.strip().casefold()
    if type(a) is bool or type(b) is bool:
        return type(a) is type(b) and a == b
    return math.isclose(a, b, rel_tol=tol, abs_tol=1e-9)


def _clusters(cands: list[Candidate], tol: float) -> list[list[Candidate]]:
    out: list[list[Candidate]] = []
    for c in cands:
        for cluster in out:
            if _same(cluster[0].value, c.value, tol):
                cluster.append(c)
                break
        else:
            out.append([c])
    return out


def _trust(cluster: list[Candidate]) -> float:
    per_family: dict[str, float] = {}
    for c in cluster:
        key = c.family or c.producer or c.source
        per_family[key] = max(per_family.get(key, 0.0), c.score)
    miss = 1.0
    for s in per_family.values():
        miss *= 1.0 - s
    return round(1.0 - miss, 6)


def _cite(cluster: list[Candidate]) -> str:
    return " + ".join(dict.fromkeys(c.source for c in cluster))


def _normalise(request: FactRequest, c: Candidate) -> tuple[Candidate | None, str]:
    """The candidate in the request's kind and unit, or None and the reason it cannot be used."""
    if c.value is None:
        return c, ""
    kind = KIND_OF_SCALAR[scalar_kind(c.value)]
    if kind != request.kind:
        return None, f"wrong kind of value: {kind}, asked {request.kind}"
    if request.kind == "number" and c.unit != request.unit:
        try:
            return c.model_copy(update={"value": convert(c.value, c.unit, request.unit), "unit": request.unit}), ""
        except UnitError as exc:
            return None, f"unit {c.unit} does not measure {request.unit}: {exc}"
    return c, ""


class Ledger:
    def __init__(self, producers: list[Producer], *, min_trust: float = MIN_TRUST):
        self.producers = list(producers)
        self.min_trust = min_trust

    def collect(self, request: FactRequest) -> list[Candidate]:
        out: list[Candidate] = []
        for p in self.producers:
            if p.holds(request) > 0:
                out += [c.model_copy(update={"producer": c.producer or p.name, "family": c.family or p.family})
                        for c in p.answer(request)]
        return out

    def resolve_all(self, request: FactRequest) -> list[Resolution]:
        """One resolution per entity the producers name; a request that names an entity yields exactly that one."""
        cands = self.collect(request)
        entities = [request.entity] if request.entity else list(dict.fromkeys(c.entity for c in cands))
        return [self.fuse(request.model_copy(update={"entity": e}), [c for c in cands if c.entity == e]) for e in entities]

    def resolve(self, request: FactRequest) -> Resolution:
        if not request.entity:
            raise ValueError("resolve needs one entity; use resolve_all for a kind of entity")
        return self.resolve_all(request)[0]

    def fuse(self, request: FactRequest, cands: list[Candidate]) -> Resolution:
        res = Resolution(request, request.entity or "", "unknown")
        if any(c.fact == request.fact for c in cands):          # a property of the requested name outranks a guess by meaning
            res.rejected += [(c, f"matched by meaning, but {request.fact} exists by name") for c in cands if c.fact != request.fact]
            cands = [c for c in cands if c.fact == request.fact]
        usable: list[Candidate] = []
        silent: list[Candidate] = []
        for c in cands:
            norm, why = _normalise(request, c)
            if norm is None:
                res.rejected.append((c, why))
            elif norm.value is None:
                silent.append(norm)
            else:
                usable.append(norm)
        if not usable:
            res.source = " | ".join(dict.fromkeys(c.source for c in silent))
            res.note = "; ".join(f"{c.source}: {why}" for c, why in res.rejected) or ("read, no value" if silent else "")
            return res
        attested = [c for c in usable if c.kind == "attested"]
        if attested:
            clusters = _clusters(attested, request.tolerance)
            res.accepted = attested
            if len(clusters) > 1:
                res.status = "conflict"
                res.source = " | ".join(_cite(cl) + f" by {cl[0].reviewer}" for cl in clusters)
                return res
            top = clusters[0]
            res.status, res.value, res.trust = "attested", top[0].value, 1.0
            res.overridden = [c for c in usable if c.kind != "attested" and not _same(c.value, top[0].value, request.tolerance)]
            names = ", ".join(dict.fromkeys(c.reviewer for c in top))
            res.source = f"attested by {names}: {_cite(top)}"
            if res.overridden:
                res.source += " (overrides " + "; ".join(f"{c.value} from {c.source}" for c in res.overridden) + ")"
                res.note = "reviewer attestation disagrees with a producer"
            return res
        clusters = _clusters(usable, request.tolerance)
        if len(clusters) > 1:
            res.status = "conflict"
            res.accepted = [max(cl, key=lambda c: c.score) for cl in clusters]
            res.source = " | ".join(_cite(cl) for cl in clusters)
            res.note = "two or more producers give different values; no value is chosen"
            return res
        cluster = clusters[0]
        best = max(cluster, key=lambda c: c.score)
        res.accepted, res.value, res.trust = cluster, best.value, _trust(cluster)
        res.status = "resolved" if res.trust >= self.min_trust else "unverified"
        res.source = _cite(cluster)
        return res
