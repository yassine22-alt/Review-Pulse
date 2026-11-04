"""Explicit clause dependencies; unresolved references remain visible to the drafter."""

from __future__ import annotations

import re

from pydantic import Field, model_validator

from ..rules.clauses import Clause
from .schema import Model, Span

REFERENCE = re.compile(
    r"\b(?:article|art\.?|paragraph|section|table)\s+(\d+(?:\.\d+)*)(?:\(([a-z0-9]+)\))?", re.I
)


class ContextBundle(Model):
    document: str
    text: str
    clauses: list[Clause]
    target: str
    missing: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_sources(self):
        ids = [clause.id for clause in self.clauses]
        if len(ids) != len(set(ids)) or self.target not in ids:
            raise ValueError("context requires unique clause ids and a present target")
        for clause in self.clauses:
            if self.text[clause.start : clause.end] != clause.text:
                raise ValueError(f"source offsets do not match text for {clause.id}")
        return self

    def check_span(self, span: Span) -> None:
        clause = next((c for c in self.clauses if c.id == span.clause), None)
        if (
            clause is None
            or not clause.start <= span.start < span.end <= clause.end
            or self.text[span.start : span.end] != span.quote
        ):
            raise ValueError(f"unsupported source quote/span: {span.clause}")


def assemble_context(
    document: str,
    text: str,
    clauses: list[Clause],
    target: str,
    links: dict[str, list[str]] | None = None,
    max_clauses: int = 40,
) -> ContextBundle:
    """Follow parent, child, explicit links and numbered references, preserving cycles safely.

    Definitions and non-numbered references should be supplied in links by the caller. This is
    deliberately not fuzzy retrieval: missing or ambiguous links must not be guessed.
    """
    by_id = {clause.id: clause for clause in clauses}
    if len(by_id) != len(clauses):
        raise ValueError("duplicate clause ids: resolve them before interpretation")
    if target not in by_id:
        raise ValueError(f"unknown clause {target}")
    selected, missing, queue = {}, set(), [target]
    while queue:
        cid = queue.pop(0)
        if cid in selected:
            continue
        if cid not in by_id:
            missing.add(f"unresolved reference:{cid}")
            continue
        if len(selected) >= max_clauses:
            missing.add(f"context limit reached:{cid}")
            continue
        clause = selected[cid] = by_id[cid]
        if clause.parent:
            queue.append(clause.parent)
        queue.extend(c.id for c in clauses if c.parent == cid)
        queue.extend((links or {}).get(cid, []))
        for match in REFERENCE.finditer(clause.text):
            number, subitem = match.groups()
            candidates = [number, f"Art. {number}"]
            if subitem:
                candidates = [f"{candidate} {subitem})" for candidate in candidates]
            matches = [candidate for candidate in candidates if candidate in by_id]
            if len(matches) == 1:
                queue.append(matches[0])
            else:
                missing.add(f"unresolved reference:{match.group(0)}")
    return ContextBundle(
        document=document,
        text=text,
        clauses=sorted(selected.values(), key=lambda c: c.start),
        target=target,
        missing=sorted(missing),
    )
