"""Explicit clause dependencies; unresolved references remain visible to the drafter."""

from __future__ import annotations

import re

from pydantic import Field, model_validator

from ..rules.clauses import Clause
from .schema import Model, Span

REFERENCE = re.compile(
    r"\b(article|art\.?|paragraph|section|table|tableau|rule|regulation|clause|§)\s*(\d+(?:\.\d+)*)(?:\(([a-z0-9]+)\))?", re.I
)
TABLE_WORDS = {"table", "tableau"}


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


QUOTED = re.compile(r"[“\"«‘]\s*([^”\"»’\n]{3,60}?)\s*[”\"»’]")
MEANS = re.compile(r"([^\W\d_][\w'’ -]{2,50}?)\s+(?:means|shall mean|refers to|is defined as|are defined as|signifie|désigne|"
                   r"bedeutet|significa|si intende|betekent|se entiende)\b", re.I)


def defined_terms(text: str) -> list[str]:
    """The terms a definition clause defines: the quoted ones, else the words before "means"."""
    terms = [t.lower() for t in QUOTED.findall(text)]
    if not terms:
        terms = [m.group(1).lower() for m in MEANS.finditer(text)]
    return [t.strip(" .,:;") for t in terms if t.strip()]


def _uses_term(definition: Clause, used_text: str) -> bool:
    terms = defined_terms(definition.text)
    if not terms:
        return True                                         # cannot tell what it defines: keep it, as before
    return any(t in used_text or t.rstrip("s") in used_text for t in terms)


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
            word, number, subitem = match.groups()
            if word.lower() in TABLE_WORDS:                 # "Table 2" is the table, never clause 2
                candidates = [f"Table {number}", f"Tableau {number}"]
            else:
                candidates = [number, f"Art. {number}", f"§ {number}", f"{word.capitalize()} {number}"]
            if subitem:
                candidates = [f"{candidate} ({subitem})" if subitem.isdigit() else f"{candidate} {subitem})"
                              for candidate in candidates]
            matches = sorted({candidate for candidate in candidates if candidate in by_id})
            if len(matches) == 1:
                queue.append(matches[0])
            else:
                missing.add(f"unresolved reference:{match.group(0)}")
        # a clause that names another by its own code ("see REQ-002") is linked to it
        for other in clauses:
            if other.id != cid and re.search(r"[A-Za-z]", other.id) and re.search(r"[-_.\d]", other.id) \
                    and re.search(rf"(?<![\w-]){re.escape(other.id)}(?![\w-])", clause.text):
                queue.append(other.id)
    # a definition travels with the clauses that use its term ("a habitable room means ..."), not with every clause: a long
    # standard defines dozens of terms and a prompt full of unrelated definitions is slow and distracting
    grew = True
    while grew and len(selected) < max_clauses:
        grew = False
        used = " ".join(c.text for c in selected.values()).lower()
        for c in clauses:
            if c.kind == "definition" and c.id not in selected and _uses_term(c, used):
                selected[c.id] = c
                grew = True
    return ContextBundle(
        document=document,
        text=text,
        clauses=sorted(selected.values(), key=lambda c: c.start),
        target=target,
        missing=sorted(missing),
    )
