"""Stateless interpreter endpoints; reuse the same operations and approval policy as the CLI."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from ..factgraph.schema import FactGraph
from ..rules.clauses import split_text
from ..schema import BuildingModel
from .building import building_graph
from .checked import checked_draft
from .context import ContextBundle, assemble_context
from .draft import draft_program
from .review import ReviewArtifact, approve_program, review_program
from .runtime import run_program
from .schema import Inputs, Model, Program


class ContextRequest(Model):
    document: str
    text: str
    target: str
    links: dict[str, list[str]] | None = None


class DraftRequest(Model):
    context: ContextBundle
    inputs: Inputs


class CheckedDraftRequest(DraftRequest):
    factgraph: FactGraph | None = None


class ReviewRequest(DraftRequest):
    program: Program


class ApprovalRequest(ReviewRequest):
    report: ReviewArtifact
    reviewer: str


class CheckRequest(Model):
    program: Program
    inputs: Inputs
    preview: bool = False
    building: BuildingModel | None = None


def _execute(operation: Callable, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def interpreter_router(llm_factory: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/interpreter", tags=["compound regulations"])

    def client():
        value = llm_factory()
        if value is None:
            raise HTTPException(503, "The drafting model is not available")
        return value

    @router.post("/context")
    def context(body: ContextRequest):
        return _execute(
            assemble_context, body.document, body.text, split_text(body.text), body.target, body.links
        )

    @router.post("/draft")
    def draft(body: DraftRequest):
        return _execute(
            draft_program, body.context, body.inputs.bindings, list(body.inputs.collections), client()
        )

    @router.post("/draft_checked")
    def draft_checked(body: CheckedDraftRequest):
        """The measured-best drafting path: expression format, sentence and catalogue checks, UNRESOLVED with a reason."""
        return _execute(checked_draft, body.context, body.inputs, body.factgraph, client())

    @router.post("/review")
    def review(body: ReviewRequest):
        return _execute(review_program, body.program, body.context, body.inputs, client())

    @router.post("/approve")
    def approve(body: ApprovalRequest):
        return _execute(approve_program, body.program, body.context, body.inputs, body.report, body.reviewer)

    @router.post("/check")
    def check(body: CheckRequest):
        graph = building_graph(body.building) if body.building else None
        return _execute(run_program, body.program, body.inputs, include_drafts=body.preview, graph=graph)

    return router
