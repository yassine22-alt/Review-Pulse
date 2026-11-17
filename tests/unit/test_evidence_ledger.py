import pytest

from reviewpulse.interpreter.evidence import EvidenceEntry, apply_evidence
from reviewpulse.interpreter.findings import to_findings
from reviewpulse.interpreter.schema import Inputs, Program

RULE = Program.model_validate({
    "id": "capacity",
    "title": "Minimum water flow",
    "status": "approved",
    "approved_by": "rule reviewer",
    "document": "specification",
    "sources": [{"clause": "1.2", "start": 0, "end": 4, "quote": "flow"}],
    "requirement": {"node": "ge", "left": {"node": "fact", "entity": "building", "name": "flow"},
                    "right": {"node": "literal", "value": 0.002, "unit": "m3/s"}},
})


def entry(value, **updates):
    fields = {"entity": "building", "fact": "flow", "unit": "L/s", "value": value,
              "origin": "reviewer-attested", "source": "commissioning certificate p. 3",
              "reviewer": "M. Reviewer", "trusted": True}
    return EvidenceEntry.model_validate({**fields, **updates})


def inputs():
    return Inputs.model_validate({"bindings": {"flow": {"kind": "number", "unit": "m3/s"}},
                                  "evidence_locations": {"flow": "commissioning certificate"}})


@pytest.mark.parametrize("value,expected", [(1, "VIOLATED"), (3, "SATISFIED")])
def test_request_then_named_attestation(value, expected):
    original = inputs()
    findings, explanation = to_findings(RULE, original, None)
    assert explanation.outcome == "UNRESOLVED"
    request = findings[0].evidence["evidence_requests"][0]
    assert (request["fact"], request["unit"], request["clause"], request["where_to_look"]) == (
        "flow", "m3/s", "1.2", "commissioning certificate")
    filled = apply_evidence(original, [entry(value)])
    findings, explanation = to_findings(RULE, filled, None)
    assert explanation.outcome == expected
    provenance = findings[0].evidence["fact_provenance"][0]
    assert provenance["origin"] == "reviewer-attested"
    assert provenance["reviewer"] == "M. Reviewer"
    assert provenance["source"] == "commissioning certificate p. 3"
    assert original.facts == {}


def test_conflicting_values_stay_unresolved_on_further_imports():
    merged = apply_evidence(inputs(), [entry(3), entry(1, source="independent flow test p. 8")])
    merged = apply_evidence(merged, [entry(3)])
    findings, explanation = to_findings(RULE, merged, None)
    assert explanation.outcome == "UNRESOLVED"
    assert findings[0].evidence["evidence_requests"][0]["reason"] == "conflicting"
    assert "independent flow test p. 8" in findings[0].evidence["fact_provenance"][0]["source"]


@pytest.mark.parametrize("updates", [{"reviewer": " "}, {"unit": "m"}, {"fact": "undeclared"}, {"value": True}])
def test_invalid_evidence_is_rejected(updates):
    original = inputs()
    value = updates.get("value", 3)
    with pytest.raises(ValueError):
        apply_evidence(original, [entry(value, **{k: v for k, v in updates.items() if k != "value"})])
    assert original.facts == {}
