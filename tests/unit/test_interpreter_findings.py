"""An approved rule becomes findings with the failing element, the measured value, the limit and the place on the plan."""

import handmade

from reviewpulse.factgraph.convert import to_graph, to_inputs
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.findings import to_findings
from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.synth import binary, fact, lit, logic, setop

SRC = [{"clause": "Art. 6.1", "start": 10, "end": 40, "quote": "Every door has a clear width"}]


def rule(requirement, title="Door width", **extra):
    return Program.model_validate({"id": "I-6.1", "title": title, "document": "doc.md", "requirement": requirement,
                                   "sources": SRC, "status": "approved", "approved_by": "Khaoula", **extra})


def run(program, narrow=True, tier="T1"):
    model = handmade.build(narrow_door=narrow, tier=tier)
    fg = from_building(model, complete=True)
    return to_findings(program, to_inputs(fg), to_graph(fg), model, tier)


def test_a_violation_names_the_element_the_value_the_limit_and_draws_it():
    program = rule(setop("forall", "doors", binary("ge", fact("width_m"), lit(0.8, "m"))))
    findings, explained = run(program)
    assert explained.outcome == "VIOLATED"
    (f,) = findings
    assert f.verdict == "FAIL" and f.subject_ids == ["d1"]
    assert f.detected == "0.7 m" and f.required == ">= 0.8 m"
    assert "P2" in f.message and f.evidence["polygons"] and f.evidence["labels"][0]["text"] == "0.7 m"
    assert f.source == {"doc": "doc.md", "clause": "Art. 6.1", "span": [10, 40]}
    assert f.evidence["approved_by"] == "Khaoula"


def test_a_satisfied_rule_is_one_pass_that_counts_what_was_checked():
    program = rule(setop("forall", "doors", binary("ge", fact("width_m"), lit(0.8, "m"))))
    findings, explained = run(program, narrow=False)
    assert explained.outcome == "SATISFIED"
    (f,) = findings
    assert f.verdict == "PASS" and f.evidence["checked"] == 5


def test_unknown_values_are_never_a_pass():
    program = rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(100, "m2"))))
    findings, explained = run(program, tier="T3")          # lower tier: room measurements are not trusted
    assert explained.outcome == "UNRESOLVED"
    (f,) = findings
    assert f.verdict == "NOT_EVALUATED" and f.evidence["missing"]


def test_a_rule_that_does_not_apply_makes_no_finding():
    program = rule(setop("forall", "doors", binary("ge", fact("width_m"), lit(0.8, "m"))),
                   applicability=lit(False))
    findings, explained = run(program)
    assert explained.outcome == "NOT_APPLICABLE" and findings == []


def test_two_failed_conditions_are_both_reported_for_the_element():
    body = logic("all", binary("ge", fact("area_m2"), lit(20, "m2")), binary("ge", fact("min_width_m"), lit(4, "m")))
    program = rule(setop("forall", "rooms", body, binary("eq", fact("room_type"), lit("bedroom"))), title="Bedroom size")
    findings, _ = run(program)
    assert {f.subject_ids[0] for f in findings} == {"bedA", "bedB"}
    assert all("m2" in f.detected and "m" in f.detected and "; " in f.detected for f in findings)


def test_a_route_rule_is_allowed_but_the_reviewer_is_told_to_read_it():
    from reviewpulse.xeval.verify import verify

    route = {"node": "path_exists", "origin": "$r", "destination": "EXIT"}
    program = rule(setop("forall", "rooms", route))
    issues = verify(program, "Every room reaches an exit.", {"collections": {"rooms": {"facts": []}}})
    assert [i.code for i in issues if i.code == "route_unchecked"] and not any(i.blocking for i in issues if i.code == "route_unchecked")


def test_two_failures_are_said_one_by_one_with_their_limits():
    body = logic("all", binary("ge", fact("area_m2"), lit(20, "m2")), binary("ge", fact("min_width_m"), lit(4, "m")))
    program = rule(setop("forall", "rooms", body, binary("eq", fact("room_type"), lit("bedroom"))), title="Bedroom size")
    findings, _ = run(program)
    text = findings[0].message
    assert "measured net floor area is 9 m2 (>= 20 m2 required)" in text and "(>= 4 m required)" in text


def test_findings_carry_the_shared_assessment_and_an_unconfirmed_inventory_is_a_warning_not_a_pass():
    program = rule(setop("forall", "doors", binary("ge", fact("width_m"), lit(0.5, "m"))))
    model = handmade.build()
    fg = from_building(model, complete=False)              # nobody confirmed the plan reader found every door
    findings, explained = to_findings(program, to_inputs(fg), to_graph(fg), model, "T1")
    assert explained.outcome == "UNRESOLVED"
    (f,) = findings
    assert f.verdict == "WARNING" and "not confirmed" in f.message
    assert f.assessment.outcome == "UNRESOLVED" and f.assessment.rule_authority == "APPROVED_REQUIREMENT"
    assert "INCOMPLETE_INVENTORY" in {i.code.value for i in f.assessment.evidence_issues}
    assert f.assessment.dependencies, "the facts the answer rests on are recorded"
