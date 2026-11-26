"""A candidate answer to a fact request, with where it came from and what kind of evidence it is."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ..interpreter.schema import Model, Scalar, Unit

EvidenceKind = Literal["measured", "stated", "inferred", "attested"]
# a bridge to origin/rule-interpreter's EvidenceOrigin, so a later merge can translate one into the other
ORIGIN_OF_KIND = {"measured": "computed", "stated": "extracted", "inferred": "extracted", "attested": "reviewer-attested"}


class Candidate(Model):
    entity: str = Field(min_length=1, description="The entity the value is about")
    fact: str = Field(min_length=1, description="The property, as the producer names it")
    value: Scalar | None = Field(default=None, description="None: the producer looked and could not read a value")
    unit: Unit = "1"
    kind: EvidenceKind
    source: str = Field(min_length=1, description="Citation a person can follow: sheet, element, row, line")
    sheet: str = ""
    view: str = ""
    region: tuple[float, float, float, float] | None = None
    words: str = Field(default="", description="The words or cells the value was read from")
    producer: str = ""
    family: str = Field(default="", description="Producers of one family share a cause (one text layer, one model) and count once")
    reviewer: str | None = None
    score: float = Field(default=0.5, ge=0, le=1, description="Probability the value is right, as the producer judges it")

    @model_validator(mode="after")
    def cited(self):
        if not self.source.strip():
            raise ValueError("a candidate requires a source citation")
        if self.kind == "attested" and not (self.reviewer or "").strip():
            raise ValueError("an attestation requires a named reviewer")
        if type(self.value) in (bool, str) and self.unit != "1":
            raise ValueError("text and booleans cannot have physical units")
        return self
