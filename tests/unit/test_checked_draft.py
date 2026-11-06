"""The production drafting path: a checked rule, or UNRESOLVED with a reason. A fake model stands in for Ollama."""

from reviewpulse.interpreter.checked import checked_draft, clause_body
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Binding, Collection, Fact, Inputs, Program
from reviewpulse.rules.clauses import split_text

TEXT = "Art. 1: Every door has a clear width of at least 0.80 m.\n"


class FakeModel:
    model = "fake"

    def __init__(self, require: str):
        self.require, self.calls = require, 0

    def complete(self, system, user, schema):
        self.calls += 1
        return {"title": "door width", "applies_when": None, "unless": None, "require": self.require,
                "sources": [{"clause": "Art. 1", "quote": "Every door has a clear width of at least 0.80 m"}],
                "unresolved": []}


def setup():
    ctx = assemble_context("doc", TEXT, split_text(TEXT), "Art. 1")
    inputs = Inputs(
        bindings={"doors_width": Binding(kind="number", unit="m", description="door: clear width (m)")},
        facts={"d1": {"doors_width": Fact(value=0.7, source="t", trusted=True)}},
        collections={"doors": Collection(items=["d1"], complete=True, trusted=True)}, graph_complete=True)
    return ctx, inputs


def test_the_clause_label_is_not_read_as_a_number():
    ctx, _ = setup()
    assert clause_body(ctx) == "Every door has a clear width of at least 0.80 m."


def test_a_correct_draft_is_returned_with_a_readback_and_runs():
    ctx, inputs = setup()
    out = checked_draft(ctx, inputs, None, FakeModel("forall doors d: d.doors_width >= 0.8 m"))
    assert out["status"] == "DRAFTED" and "doors_width" in out["readback"]
    program = Program.model_validate(out["program"])
    assert run_program(program, inputs, include_drafts=True)["outcome"] == "VIOLATED"


def test_a_draft_with_the_wrong_number_is_never_returned():
    ctx, inputs = setup()
    model = FakeModel("forall doors d: d.doors_width >= 0.9 m")
    out = checked_draft(ctx, inputs, None, model)
    assert out["status"] == "UNRESOLVED" and out["program"] is None and "0.9" in out["reason"]
    assert model.calls == 2                      # one repair was offered, and it was also wrong


def test_a_draft_that_measures_something_else_is_unresolved():
    ctx, inputs = setup()
    out = checked_draft(ctx, inputs, None, FakeModel("forall doors d: d.nonexistent >= 0.8 m"))
    assert out["status"] == "UNRESOLVED" and out["program"] is None


def test_a_route_requirement_is_drafted_and_judged_on_the_plan_graph():
    import handmade

    from reviewpulse.factgraph.convert import to_graph, to_inputs
    from reviewpulse.factgraph.from_building import from_building

    text = "Art. 1: Every bedroom reaches an exit without passing through a bathroom.\n"
    ctx = assemble_context("doc", text, split_text(text), "Art. 1")

    class RouteModel(FakeModel):
        def complete(self, system, user, schema):
            out = super().complete(system, user, schema)
            out["sources"] = [{"clause": "Art. 1", "quote": "Every bedroom reaches an exit without passing through a bathroom"}]
            return out

    model = RouteModel("forall rooms r where r.room_type == 'bedroom': reaches(r, EXIT, through n: n.room_type != 'bathroom')")
    bad = from_building(handmade.build(bed_b_via_bath=True), complete=True)
    out = checked_draft(ctx, to_inputs(bad), bad, model)
    assert out["status"] == "DRAFTED" and "reaches(" in out["readback"]
    program = Program.model_validate(out["program"])
    assert run_program(program, to_inputs(bad), include_drafts=True, graph=to_graph(bad))["outcome"] == "VIOLATED"
    good = from_building(handmade.build(bed_b_via_bath=False), complete=True)
    assert run_program(program, to_inputs(good), include_drafts=True, graph=to_graph(good))["outcome"] == "SATISFIED"
