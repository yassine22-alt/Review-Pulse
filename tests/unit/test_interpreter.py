"""Behavioral cases are independent of the interpreter's own generated self-tests."""

import copy
import json

import networkx as nx
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from reviewpulse.interpreter.cli import app
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.interpreter.draft import draft_program
from reviewpulse.interpreter.examples import demonstrations, run_demonstration
from reviewpulse.interpreter.review import ReviewArtifact, approve_program, review_fingerprint, review_program
from reviewpulse.interpreter.runtime import Evaluator, run_program
from reviewpulse.interpreter.schema import Binding, Inputs, Program
from reviewpulse.interpreter.validate import validate_program
from reviewpulse.rules.clauses import split_text


def literal(value, unit="1"):
    return {"node": "literal", "value": value, "unit": unit}


def fact(name, entity="building"):
    return {"node": "fact", "entity": entity, "name": name}


def binary(node, left, right):
    return {"node": node, "left": left, "right": right}


def logical(node, *args):
    return {"node": node, "args": list(args)}


def program(requirement, **kwargs):
    return Program.model_validate(
        {
            "id": "test",
            "title": "Test rule",
            "document": "fixture",
            "requirement": requirement,
            "sources": [{"clause": "1", "start": 0, "end": 1, "quote": "1"}],
            **kwargs,
        }
    )


def evidence(values, *, bindings=None, collections=None):
    return Inputs.model_validate(
        {
            "bindings": bindings or {name: {"kind": "boolean"} for name in values},
            "facts": {
                "building": {
                    name: {"value": value, "source": name, "trusted": True} for name, value in values.items()
                }
            },
            "collections": collections or {},
        }
    )


def outcome(rule, inputs):
    return run_program(rule, inputs, include_drafts=True)["outcome"]


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(True, None, "SATISFIED"), (False, None, "UNRESOLVED"), (False, False, "VIOLATED")],
)
def test_alternative_compliance_with_missing_evidence(a, b, expected):
    rule = program(logical("any", fact("vision_panel"), fact("alarm")))
    assert outcome(rule, evidence({"vision_panel": a, "alarm": b})) == expected


@pytest.mark.parametrize(
    ("applies", "exempt", "meets", "expected"),
    [
        (False, None, False, "NOT_APPLICABLE"),
        (True, True, False, "EXEMPT"),
        (True, None, False, "UNRESOLVED"),
        (True, None, True, "SATISFIED"),
        (None, False, True, "UNRESOLVED"),
        (True, False, False, "VIOLATED"),
    ],
)
def test_applicability_and_exemptions(applies, exempt, meets, expected):
    rule = program(fact("meets"), applicability=fact("applies"), exemption=fact("exempt"))
    assert outcome(rule, evidence({"applies": applies, "exempt": exempt, "meets": meets})) == expected


def test_unknown_and_false_preserves_decisive_false():
    assert (
        outcome(program(logical("all", fact("a"), fact("b"))), evidence({"a": None, "b": False}))
        == "VIOLATED"
    )


def test_nested_exception_strict_boundary_and_multiple_conditions():
    # A simplified, explicitly scoped dining-area exemption: all its conditions must hold.
    ratio = binary("div", fact("mezzanine"), fact("total"))
    exemption = logical(
        "all", fact("vertical_exempt"), binary("lt", ratio, literal(0.25)), fact("same_services")
    )
    rule = program(fact("route"), exemption=exemption)
    bindings = {key: {"kind": "number", "unit": "m2"} for key in ("mezzanine", "total")}
    bindings.update({key: {"kind": "boolean"} for key in ("vertical_exempt", "same_services", "route")})
    values = {"mezzanine": 24, "total": 100, "vertical_exempt": True, "same_services": True, "route": False}
    assert outcome(rule, evidence(values, bindings=bindings)) == "EXEMPT"
    values["mezzanine"] = 25
    assert outcome(rule, evidence(values, bindings=bindings)) == "VIOLATED"
    values.update(mezzanine=24, same_services=None)
    assert outcome(rule, evidence(values, bindings=bindings)) == "UNRESOLVED"


def test_exit_capacity_excludes_largest_before_comparing_total():
    def aggregate(node):
        return {"node": node, "collection": "exits", "variable": "$exit", "body": fact("capacity", "$exit")}

    rule = program(binary("ge", binary("sub", aggregate("sum"), aggregate("max")), fact("occupants")))
    inputs = Inputs.model_validate(
        {
            "bindings": {
                "capacity": {"kind": "number", "unit": "count"},
                "occupants": {"kind": "number", "unit": "count"},
            },
            "facts": {
                "building": {"occupants": {"value": 150, "source": "brief", "trusted": True}},
                **{
                    key: {"capacity": {"value": value, "source": key, "trusted": True}}
                    for key, value in (("a", 200), ("b", 80), ("c", 80))
                },
            },
            "collections": {"exits": {"items": ["a", "b", "c"], "complete": True, "trusted": True}},
        }
    )
    assert outcome(rule, inputs) == "SATISFIED"
    inputs.facts["building"]["occupants"].value = 161
    assert outcome(rule, inputs) == "VIOLATED"
    inputs.collections["exits"].complete = False
    assert outcome(rule, inputs) == "UNRESOLVED"


@pytest.mark.parametrize(
    ("node", "complete", "values", "expected"),
    [
        ("forall", False, [True], "UNRESOLVED"),
        ("forall", False, [False], "VIOLATED"),
        ("exists", False, [True], "SATISFIED"),
        ("exists", False, [False], "UNRESOLVED"),
        ("forall", True, [], "UNRESOLVED"),
        ("exists", True, [], "VIOLATED"),
    ],
)
def test_quantifiers_and_inventory_completeness(node, complete, values, expected):
    rule = program({"node": node, "collection": "rooms", "variable": "$room", "body": fact("ok", "$room")})
    inputs = Inputs.model_validate(
        {
            "bindings": {"ok": {"kind": "boolean"}},
            "facts": {
                str(i): {"ok": {"value": value, "source": str(i), "trusted": True}}
                for i, value in enumerate(values)
            },
            "collections": {
                "rooms": {
                    "items": [str(i) for i in range(len(values))],
                    "complete": complete,
                    "trusted": True,
                }
            },
        }
    )
    assert outcome(rule, inputs) == expected


def test_unknown_filter_cannot_create_false_violation():
    rule = program(
        {
            "node": "forall",
            "collection": "rooms",
            "variable": "$r",
            "where": fact("selected", "$r"),
            "body": literal(False),
        }
    )
    inputs = Inputs.model_validate(
        {
            "bindings": {"selected": {"kind": "boolean"}},
            "collections": {"rooms": {"items": ["a"], "complete": True, "trusted": True}},
        }
    )
    assert outcome(rule, inputs) == "UNRESOLVED"


def test_unverified_members_do_not_establish_quantified_violation():
    rule = program({"node": "forall", "collection": "rooms", "variable": "$r", "body": literal(False)})
    inputs = evidence({}, collections={"rooms": {"items": ["possible-room"], "complete": False}})
    assert outcome(rule, inputs) == "UNRESOLVED"


def test_forall_ignores_members_outside_its_filter():
    rule = program(
        {
            "node": "forall",
            "collection": "rooms",
            "variable": "$r",
            "where": literal(False),
            "body": literal(False),
        }
    )
    inputs = evidence({}, collections={"rooms": {"items": ["irrelevant"], "complete": True, "trusted": True}})
    assert outcome(rule, inputs) == "SATISFIED"


def test_nonfinite_aggregate_does_not_certify_a_comparison():
    rule = program(
        binary(
            "ge", {"node": "sum", "collection": "rooms", "variable": "$r", "body": literal(1e308)}, literal(1)
        )
    )
    inputs = evidence({}, collections={"rooms": {"items": ["a", "b"], "complete": True, "trusted": True}})
    assert outcome(rule, inputs) == "UNRESOLVED"


@pytest.mark.parametrize("change", ["untrusted", "conflicting", "missing"])
def test_uncertain_fact_is_not_false(change):
    inputs = evidence({"ok": False})
    entry = inputs.facts["building"]["ok"]
    if change == "untrusted":
        entry.trusted = False
    elif change == "conflicting":
        entry.conflicting = True
    else:
        entry.value = None
    result = run_program(program(fact("ok")), inputs, include_drafts=True)
    assert result["outcome"] == "UNRESOLVED"
    assert result["trace"]["missing"]


def test_units_variables_and_unsupported_properties_are_rejected():
    bindings = {"area": Binding(kind="number", unit="m2")}
    for expr, message in [
        (binary("ge", fact("area"), literal(2, "m")), "incompatible"),
        (fact("area", "$unbound"), "unbound"),
        (fact("guessed"), "unsupported"),
    ]:
        with pytest.raises(ValueError, match=message):
            validate_program(program(expr), bindings)


def test_schema_rejects_code_extra_fields_and_duplicate_ids():
    with pytest.raises(ValidationError):
        program({"node": "python", "code": "print('never')"})
    with pytest.raises(ValidationError):
        program({**literal(True), "unused": True})
    with pytest.raises(ValidationError):
        evidence({}, collections={"rooms": {"items": ["a", "a"]}})


def test_division_by_zero_and_empty_min_are_unknown():
    for expr in [
        binary("eq", binary("div", literal(1), literal(0)), literal(0)),
        binary(
            "ge", {"node": "min", "collection": "rooms", "variable": "$r", "body": literal(1)}, literal(0)
        ),
    ]:
        assert outcome(program(expr), evidence({}, collections={"rooms": {"complete": True}})) == "UNRESOLVED"


def test_path_must_satisfy_all_conditions_on_one_route():
    inputs = Inputs.model_validate(
        {
            "bindings": {"width": {"kind": "number", "unit": "m"}, "allowed": {"kind": "boolean"}},
            "facts": {
                "a": {"allowed": {"value": False, "source": "a", "trusted": True}},
                "b": {"allowed": {"value": True, "source": "b", "trusted": True}},
                "start": {"allowed": {"value": True, "source": "start", "trusted": True}},
                "wide": {"width": {"value": 1.2, "source": "wide", "trusted": True}},
                "narrow": {"width": {"value": 0.6, "source": "narrow", "trusted": True}},
            },
            "graph_complete": True,
        }
    )
    graph = nx.MultiGraph()
    for a, b, via in [
        ("start", "a", "wide"),
        ("a", "EXIT", "wide"),
        ("start", "b", "narrow"),
        ("b", "EXIT", "wide"),
    ]:
        graph.add_edge(a, b, via=via, kind="door", trusted=True)
    rule = program(
        {
            "node": "path_exists",
            "origin": "start",
            "node_filter": fact("allowed", "$node"),
            "edge_filter": binary("ge", fact("width", "$edge"), literal(0.9, "m")),
        }
    )
    assert run_program(rule, inputs, include_drafts=True, graph=graph)["outcome"] == "VIOLATED"
    inputs.facts["narrow"]["width"].value = 0.95
    assert run_program(rule, inputs, include_drafts=True, graph=graph)["outcome"] == "SATISFIED"
    inputs.facts["narrow"]["width"].trusted = False
    assert run_program(rule, inputs, include_drafts=True, graph=graph)["outcome"] == "UNRESOLVED"


def test_runtime_budget():
    with pytest.raises(ValueError, match="budget"):
        Evaluator(evidence({}), max_steps=0).evaluate(program(literal(True)).requirement)


def test_context_follows_parent_subitems_references_and_cycles():
    text = "1 Main rule. See paragraph 2.\na) Additional condition.\n2 Refer to paragraph 1.\n"
    clauses = split_text(text)
    context = assemble_context("fixture", text, clauses, "1")
    assert {clause.id for clause in context.clauses} == {"1", "1 a)", "2"}
    assert not context.missing
    limited = assemble_context("fixture", text, clauses, "1", max_clauses=1)
    assert any("limit" in item for item in limited.missing)
    missing = assemble_context("fixture", text, clauses, "1", links={"1": ["external:standard"]})
    assert "unresolved reference:external:standard" in missing.missing


class StubClient:
    model = "offline-test"

    def __init__(self, answer):
        self.answer = answer

    def complete(self, system, user, json_schema):
        assert "untrusted source data" in system
        assert json.loads(user)["clauses"]
        assert "$defs" in json_schema
        return copy.deepcopy(self.answer)


def test_drafter_preserves_missing_dependencies_and_cannot_self_approve():
    text = "1 Requirement. See paragraph 9.\n"
    context = assemble_context("fixture", text, split_text(text), "1")
    rule = program(literal(True), status="approved")
    answer = rule.model_dump()
    result = draft_program(context, {}, [], StubClient(answer))
    assert result["program"]["status"] == "draft"
    assert result["program"]["unresolved"] == context.missing
    assert len(result["document_hash"]) == 64
    answer["sources"][0]["quote"] = "invented"
    with pytest.raises(ValueError, match="source"):
        draft_program(context, {}, [], StubClient(answer))


def test_drafts_require_preview_and_cli_writes_evidence(tmp_path):
    rule = program(literal(True))
    inputs = evidence({})
    with pytest.raises(ValueError, match="preview"):
        run_program(rule, inputs)
    rule_file, inputs_file, out = (tmp_path / name for name in ("rule.json", "inputs.json", "result.json"))
    rule_file.write_text(rule.model_dump_json(), encoding="utf-8")
    inputs_file.write_text(inputs.model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(app, ["check", str(rule_file), str(inputs_file), str(out), "--preview"])
    assert result.exit_code == 0, result.output
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["outcome"] == "SATISFIED" and saved["preview"]
    assert len(saved["trace"]["children"]) == 3


def test_three_compound_demonstrations_and_cli(tmp_path):
    examples = demonstrations()
    assert len(examples) == 3
    for example in examples:
        assert all(case["matches"] for case in run_demonstration(example))
    result = CliRunner().invoke(app, ["demo", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert len(list(tmp_path.glob("*/scenarios.json"))) == 3


def test_independent_review_fingerprint_and_stale_approval(tmp_path):
    text = "1 Requirement.\n"
    bundle = assemble_context("fixture", text, split_text(text), "1")
    rule, inputs = program(literal(True)), evidence({})

    class Critic:
        model = "critic-test"

        def complete(self, system, user, schema):
            assert "Independently audit" in system
            assert "program" in json.loads(user)
            return {"issues": [], "limitations": []}

    review = review_program(rule, bundle, inputs, Critic())
    assert review["fingerprint"] == review_fingerprint(rule, bundle, inputs)
    paths = [
        tmp_path / name
        for name in ("program.json", "context.json", "inputs.json", "review.json", "approved.json")
    ]
    for path, data in zip(
        paths, (rule.model_dump(), bundle.model_dump(mode="json"), inputs.model_dump(), review)
    ):
        path.write_text(json.dumps(data), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["approve", *(str(path) for path in paths), "Reviewer"])
    assert result.exit_code == 0, result.output
    approved = Program.model_validate_json(paths[-1].read_text())
    assert approved.approved_by == "Reviewer"
    assert run_program(approved, inputs)["outcome"] == "SATISFIED"
    edited = rule.model_copy(update={"title": "Changed interpretation"})
    paths[0].write_text(edited.model_dump_json(), encoding="utf-8")
    rejected = runner.invoke(app, ["approve", *(str(path) for path in paths), "Reviewer"])
    assert rejected.exit_code != 0 and "stale" in rejected.output


def test_building_adapter_reuses_existing_graph_and_preserves_uncertainty():
    import handmade

    from reviewpulse.interpreter.building import building_graph, building_inputs

    model = handmade.build()
    inputs = building_inputs(model)
    assert not inputs.graph_complete and not inputs.collections["rooms"].complete
    assert inputs.collections["rooms"].trusted
    graph = building_graph(model)
    assert graph.number_of_edges() == len(model.edges)
    assert all(data["trusted"] for _a, _b, data in graph.edges(data=True))
    model.tier = "T3"
    uncertain = building_inputs(model)
    assert not uncertain.collections["rooms"].trusted
    assert all(
        not values["area_m2"].trusted for key, values in uncertain.facts.items() if "area_m2" in values
    )


def test_unresolved_interpretation_and_semantic_review_block_approval():
    bundle = assemble_context("fixture", "1 Requirement.", split_text("1 Requirement."), "1")
    inputs = evidence({})
    rule = program(literal(True), unresolved=["Missing definition"])
    report = ReviewArtifact.model_validate(
        {
            "review": {"issues": [], "limitations": []},
            "model": "test",
            "fingerprint": review_fingerprint(rule, bundle, inputs),
        }
    )
    with pytest.raises(ValueError, match="dependencies"):
        approve_program(rule, bundle, inputs, report, "Reviewer")
    rule.unresolved = []
    report.fingerprint = review_fingerprint(rule, bundle, inputs)
    report.review.limitations = ["Exception context not verified"]
    with pytest.raises(ValueError, match="limitations"):
        approve_program(rule, bundle, inputs, report, "Reviewer")
