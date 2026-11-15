"""Shared verdict vocabulary for the compound interpreter and legacy checker."""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Outcome = Literal["SATISFIED", "VIOLATED", "UNRESOLVED", "NOT_APPLICABLE", "EXEMPT"]
Authority = Literal["APPROVED_REQUIREMENT", "ADVISORY_GUIDANCE"]


class IssueCode(StrEnum):
    UNCERTAIN_SCALE = "UNCERTAIN_SCALE"
    UNKNOWN_CLASS = "UNKNOWN_CLASS"
    INCOMPLETE_INVENTORY = "INCOMPLETE_INVENTORY"
    MISSING_CONNECTION = "MISSING_CONNECTION"
    POSSIBLE_TEXT_OMISSION = "POSSIBLE_TEXT_OMISSION"
    UNVERIFIED_GEOMETRY = "UNVERIFIED_GEOMETRY"
    MISSING_INPUT = "MISSING_INPUT"
    TOLERANCE_BAND = "TOLERANCE_BAND"


class EvidenceIssue(BaseModel):
    code: IssueCode
    detail: str


class Assessment(BaseModel):
    outcome: Outcome
    evidence_issues: list[EvidenceIssue] = Field(default_factory=list)
    severity: Literal["CRITICAL", "MAJOR", "MINOR"]
    rule_authority: Authority
    dependencies: list[str] = Field(default_factory=list)
