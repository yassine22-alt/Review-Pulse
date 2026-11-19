import pytest

from reviewpulse.interpreter.focused_request import finite_strict_schema, focus_catalogue
from reviewpulse.llm.openai_compat import _strict


def test_focus_uses_type_vocabulary_and_reports_missing_candidates_without_guessing():
    catalogue = {"whole": "building", "building": ["thermal_loss", "unrelated"],
                 "bindings": {"thermal_loss": {"description": "Thermal heat transfer", "kind": "number"},
                              "unrelated": {"description": "Door operation", "kind": "boolean"}},
                 "collections": {}, "kinds": {}, "kind_labels": {}}
    selected, trace = focus_catalogue(catalogue, "Thermal heat requirements")
    assert selected["building"] == ["thermal_loss"]
    assert trace["omitted"] == ["unrelated"]
    assert set(catalogue["bindings"]) == {"thermal_loss", "unrelated"}
    empty, trace = focus_catalogue(catalogue, "Unrecognized vocabulary")
    assert empty["bindings"] == {}
    assert trace["selected"] == []


def test_strict_contract_inlines_finite_refs_and_does_not_force_optional_filter_meaning():
    schema = {"type": "object", "properties": {"title": {"type": "string"}, "node": {"$ref": "#/$defs/Node"}},
              "required": ["node"], "$defs": {"Node": {"type": "object", "properties": {
                  "id": {"type": "string"}, "where": {"type": "string"},
                  "unit": {"type": "string", "enum": ["m", "1"], "default": "1"}}, "required": ["id"]}}}
    result = finite_strict_schema(schema)
    assert "$defs" not in result
    assert result["properties"]["title"] == {"type": "string"}
    assert "title" in _strict(result)["properties"]
    node = result["properties"]["node"]
    assert set(node["required"]) == {"id", "where", "unit"}
    assert node["properties"]["where"]["anyOf"][-1] == {"type": "null"}
    assert node["properties"]["unit"]["enum"] == ["m", "1"]
    assert _strict(result) is not None


def test_recursive_or_external_schema_is_rejected_offline():
    for ref in ("#/$defs/Loop", "https://invalid.test/schema"):
        with pytest.raises(ValueError):
            finite_strict_schema({"$ref": ref, "$defs": {"Loop": {"$ref": "#/$defs/Loop"}}})


def test_oneof_conversion_requires_provably_disjoint_required_operation_enums():
    def branch(op):
        return {"type": "object", "properties": {"op": {"type": "string", "enum": [op]}}, "required": ["op"]}
    assert "anyOf" in finite_strict_schema({"oneOf": [branch("literal"), branch("fact")]})
    with pytest.raises(ValueError, match="overlapping"):
        finite_strict_schema({"oneOf": [branch("fact"), branch("fact")]})


def test_number_union_includes_integer_without_ambiguous_strict_alternatives():
    scalar = {"anyOf": [{"type": "integer"}, {"type": "number"}, {"type": "string"}]}
    assert finite_strict_schema(scalar) == {"anyOf": [{"type": "number"}, {"type": "string"}]}


def test_string_union_preserves_literal_owners_and_variable_pattern():
    import re

    result = finite_strict_schema({"anyOf": [{"type": "string", "enum": ["whole", "OUT"]},
        {"type": "string", "pattern": r"^\$[A-Za-z]+$"}, {"type": "null"}]})
    strings = [choice for choice in result["anyOf"] if choice.get("type") == "string"]
    assert len(strings) == 1
    pattern = strings[0]["pattern"]
    assert all(re.search(pattern, value) for value in ("whole", "OUT", "$member"))
    assert not any(re.search(pattern, value) for value in ("other", "whole_extra", "$12"))
