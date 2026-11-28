import pytest

from reviewpulse.engine.policy import Measurement, Raw, decide
from reviewpulse.engine.run import run
from reviewpulse.eval.acceptance import verdict_metrics
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Inputs, Program
from reviewpulse.outcomes import IssueCode


def test_unverified_compliant_measurement_cannot_pass_without_bounds():
    result = decide(Raw(["x"], False, metric=True), "T3", guidance=False,
                    scale_verified=False, all_confirmed=True)
    assert result.verdict == "WARNING"


@pytest.mark.parametrize("value,op,verified,expected", [
    (0.81, ">=", False, "UNRESOLVED"),
    (0.40, ">=", False, "VIOLATED"),
    (0.81, ">=", True, "SATISFIED"),
    (1.20, ">=", False, "SATISFIED"),
    (0.79, "<=", False, "UNRESOLVED"),
    (1.20, "<=", False, "VIOLATED"),
    (0.40, "<=", False, "SATISFIED"),
    (0.80, ">", True, "VIOLATED"),
    (0.80, "<", True, "VIOLATED"),
])
def test_interval_policy(value, op, verified, expected):
    raw = Raw(["x"], value < 0.8, metric=True, measurement=Measurement(value, op, 0.8))
    result = decide(raw, "T1" if verified else "T3", guidance=False, scale_verified=verified)
    assert result.outcome == expected
    assert "scale" in result.dependencies


def test_uncertainty_and_tolerance_are_separate():
    raw = Raw(["x"], True, metric=True, measurement=Measurement(0.795, ">=", 0.8, 0.01))
    result = decide(raw, "T1", guidance=False)
    assert result.interval == (0.795, 0.795)
    assert result.outcome == "UNRESOLVED"
    assert Measurement(4, ">=", 3, scale_power=2).interval(False, 0.25) == (2.25, 6.25)
    with pytest.raises(ValueError):
        raw.measurement.interval(False, float("nan"))


def test_isolated_room_reason_is_connectivity(pack):
    import handmade

    model = handmade.build(tier="T3")
    model.sheet.mode = "raster"
    model.edges = []
    rule = next(r for r in pack if r.check.fn == "isolated_rooms")
    findings = run(model, [rule])
    assert findings
    for finding in findings:
        codes = {i.code for i in finding.assessment.evidence_issues}
        assert IssueCode.MISSING_CONNECTION in codes
        assert IssueCode.POSSIBLE_TEXT_OMISSION not in codes
        assert finding.assessment.outcome == "UNRESOLVED"


def test_ocr_absence_and_guidance_authority(pack):
    import handmade

    model = handmade.build(tier="T3")
    model.sheet.mode = "raster"
    model.sheet.texts = []
    rule = next(r for r in pack if r.check.fn == "present" and r.params.get("what") == "title_block")
    rule = rule.model_copy(update={"severity": "critical"})
    finding = run(model, [rule])[0]
    assert finding.assessment.severity == "CRITICAL"
    assert finding.severity == "critical"  # legacy report field
    assert IssueCode.POSSIBLE_TEXT_OMISSION in {i.code for i in finding.assessment.evidence_issues}
    assert finding.assessment.dependencies
    result = decide(Raw(["x"], True), "T1", guidance=True)
    assert result.outcome == "VIOLATED" and result.verdict == "WARNING"


def test_observed_annotation_is_not_a_missing_connection(pack):
    import handmade

    model = handmade.build(tier="T3")
    rule = next(r for r in pack if r.check.fn == "present" and r.params.get("what") == "room_labels")
    findings = run(model, [rule])
    for finding in findings:
        codes = {i.code for i in finding.assessment.evidence_issues}
        assert IssueCode.MISSING_CONNECTION not in codes
        assert IssueCode.UNVERIFIED_ANNOTATION in codes


def test_absent_forbidden_connection_needs_complete_inventory(pack):
    import handmade

    model = handmade.build(tier="T3")
    model.edges = model.edges[:1]
    next(r for r in model.rooms if r.id == "bath").type = "garage"
    rule = next(r for r in pack if r.check.fn == "forbidden_link")
    finding = run(model, [rule])[0]
    assert finding.assessment.outcome == "UNRESOLVED"
    assert IssueCode.INCOMPLETE_INVENTORY in {i.code for i in finding.assessment.evidence_issues}
    assert finding.message.startswith(rule.title) and "read none" not in finding.message
    assert finding.evidence["title"] == rule.title


@pytest.mark.parametrize("unknown,outcome", [(False, "SATISFIED"), (True, "UNRESOLVED")])
def test_without_a_garage_there_is_nothing_to_connect_unless_a_room_is_unknown(pack, unknown, outcome):
    import handmade

    model = handmade.build(tier="T3")
    model.edges = model.edges[:1]
    if unknown:                                   # it may be the garage
        next(r for r in model.rooms if r.id == "bath").type = None
    rule = next(r for r in pack if r.check.fn == "forbidden_link")
    assert run(model, [rule])[0].assessment.outcome == outcome


@pytest.mark.parametrize("quantifier,complete,value,expected", [
    ("forall", False, False, "VIOLATED"),
    ("forall", False, True, "UNRESOLVED"),
    ("forall", True, True, "SATISFIED"),
    ("exists", False, True, "SATISFIED"),
    ("exists", False, False, "UNRESOLVED"),
    ("exists", True, False, "VIOLATED"),
])
def test_incomplete_inventory_preserves_quantifier_semantics(quantifier, complete, value, expected):
    inputs = Inputs.model_validate({
        "bindings": {"meets": {"kind": "boolean"}},
        "facts": {"member": {"meets": {"value": value, "trusted": True, "source": "review"}}},
        "collections": {"members": {"items": ["member"], "complete": complete, "trusted": True}},
    })
    program = Program.model_validate({
        "id": "inventory", "title": "Inventory", "document": "test",
        "sources": [{"clause": "1", "start": 0, "end": 1, "quote": "x"}],
        "requirement": {"node": quantifier, "collection": "members", "variable": "$x",
                        "body": {"node": "fact", "entity": "$x", "name": "meets"}},
    })
    result = run_program(program, inputs, include_drafts=True)
    assert result["outcome"] == expected
    assert set(result["dependencies"]) == {"inventory:members", "member.meets"}
    assert bool(result["evidence_issues"]) == (not complete)
    if not complete:
        assert result["evidence_issues"][0]["code"] == "INCOMPLETE_INVENTORY"


def test_verdict_scoring_does_not_credit_warning_as_correct_failure():
    def finding(rule, outcome, issues=()):
        return {"rule_id": rule, "subject_ids": ["x"], "assessment": {
            "outcome": outcome, "evidence_issues": [{"code": c} for c in issues]}}
    findings = [finding("a", "VIOLATED"), finding("b", "SATISFIED"),
                finding("c", "UNRESOLVED", ["UNKNOWN_CLASS"]), finding("d", "VIOLATED")]
    truth = [{"rule_id": name, "subject_ids": ["x"], "outcome": outcome}
             for name, outcome in (("a", "VIOLATED"), ("b", "VIOLATED"), ("c", "UNRESOLVED"),
                                   ("d", "SATISFIED"))]
    truth[2]["evidence_issues"] = ["UNKNOWN_CLASS"]
    scores = verdict_metrics(findings, truth)
    assert scores["precision_violated"] == 0.5
    assert scores["false_pass_rate"] == 0.5
    assert scores["verdict_correctness"] == 0.5
    assert scores["decisive_coverage"] == 0.75
    assert scores["unresolved_reason_accuracy"] == 1
    assert verdict_metrics(findings, [])["precision_violated"] is None
    assert verdict_metrics([], truth)["verdict_correctness"] == 0
    ambiguous = verdict_metrics([findings[0], findings[0]], truth[:1])
    assert ambiguous["ambiguous_prediction_keys"] == 1
    assert ambiguous["matched_checks"] == 0
    with pytest.raises(ValueError):
        verdict_metrics(findings, [truth[0], truth[0]])


def test_acceptance_crash_reports_the_actual_problem(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from reviewpulse.eval.acceptance import Case, run_case

    monkeypatch.setattr("reviewpulse.eval.acceptance.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="reader failed", stdout=""))
    case = Case("failure", "vector", lambda directory: tmp_path / "input.dxf", {"T1"})
    result = run_case(case, tmp_path)
    assert result["ok"] is False
    assert result["problems"] == ["crash: reader failed"]
