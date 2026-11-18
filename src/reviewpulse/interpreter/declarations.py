"""Source-grounded declarations add names and types, never measured values."""
from __future__ import annotations

import copy

from .schema import Binding, Fact, FactDeclaration, Inputs


class DeclarationError(ValueError):
    def __init__(self, stage: str, detail: str):
        self.stage = stage
        super().__init__(detail)


def declaration_catalogue(catalogue: dict, declarations: list[FactDeclaration]) -> dict:
    result = copy.deepcopy(catalogue)
    seen = set()
    for declaration in declarations:
        name, entity = declaration.name, declaration.entity
        if name in seen or name == "id":
            raise DeclarationError("declaration", "duplicate proposed fact name")
        seen.add(name)
        if name in result["bindings"]:
            raise DeclarationError("declaration", "a proposal cannot replace an existing binding")
        if entity == (result.get("whole") or "building"):
            owner = result["building"]
        elif entity in result["collections"]:
            owner = result["collections"][entity]["facts"]
        else:
            raise DeclarationError("entity_binding", "proposed fact has no known entity or collection")
        binding = Binding(kind=declaration.kind, unit=declaration.unit, description=declaration.definition,
                          declaration=declaration)
        result["bindings"][name] = binding.model_dump(mode="json")
        owner.append(name)
    return result


def apply_declarations(inputs: Inputs, declarations: list[FactDeclaration]) -> Inputs:
    """Create missing-value ledger slots. No value or provenance is inferred."""
    if not declarations:
        return inputs
    data = inputs.model_dump()
    seen = set()
    for declaration in declarations:
        if declaration.name in seen or declaration.name == "id":
            raise DeclarationError("declaration", "duplicate proposed fact name")
        seen.add(declaration.name)
        existing = inputs.bindings.get(declaration.name)
        if existing and existing.declaration != declaration:
            raise DeclarationError("declaration", "declaration conflicts with the existing binding")
        if declaration.entity in inputs.collections:
            targets = inputs.collections[declaration.entity].items
        elif declaration.entity == "building" or declaration.entity in inputs.facts:
            targets = [declaration.entity]
        else:
            raise DeclarationError("entity_binding", "declaration refers to an unknown entity or collection")
        data["bindings"][declaration.name] = Binding(
            kind=declaration.kind, unit=declaration.unit, description=declaration.definition,
            declaration=declaration).model_dump(mode="json")
        data["evidence_locations"].setdefault(
            declaration.name, f"Reviewer evidence for {declaration.source.clause}: {declaration.definition}")
        for entity in targets:
            data["facts"].setdefault(entity, {}).setdefault(
                declaration.name, Fact(source="Declared; needs reviewer evidence").model_dump())
    return Inputs.model_validate(data)

