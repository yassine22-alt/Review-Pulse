"""A fact request: the typed question a requirement asks of the drawing set.

A request names what is wanted by meaning (an entity, a property, a kind of value, a unit and therefore a dimension),
never a value and never a fixed fact name that some producer must happen to use. It keeps the words of the clause it
comes from so a producer can match by meaning and a reviewer can see why the question was asked.

Field names follow `EvidenceRequest` and `FactDeclaration` of origin/rule-interpreter where the idea is the same
(entity, fact, unit, reason, why, clause).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ..interpreter.schema import Model, Unit
from ..interpreter.units import Unit as SIUnit
from ..interpreter.units import parse_unit, symbol_of

ValueKind = Literal["number", "bool", "category"]
KIND_OF_BINDING = {"number": "number", "boolean": "bool", "string": "category"}
BINDING_OF_KIND = {v: k for k, v in KIND_OF_BINDING.items()}


class FactRequest(Model):
    entity: str | None = Field(default=None, description="The entity id asked about; None asks about every entity of the kind")
    entity_kind: str | None = Field(default=None, description="door, room, building ... or a collection name")
    fact: str = Field(min_length=1, description="The property wanted, by name or by meaning (door_width, area)")
    kind: ValueKind = "number"
    unit: Unit = "1"
    dimension: str = Field(default="", description="The coherent SI unit of the quantity (m, m2, s); derived from the unit")
    words: str = Field(default="", description="The words of the clause the request comes from")
    clause: str = ""
    reason: Literal["needed", "missing", "conflicting", "unverified"] = "needed"
    why: str = ""
    tolerance: float = Field(default=0.005, ge=0, description="Relative difference below which two numbers agree")

    @model_validator(mode="after")
    def typed(self):
        if self.kind != "number" and self.unit != "1":
            raise ValueError("only numbers have units")
        if self.kind == "number":
            self.dimension = symbol_of(SIUnit(1.0, parse_unit(self.unit).dims))
        return self

    @property
    def key(self) -> tuple[str | None, str]:
        return self.entity, self.fact
