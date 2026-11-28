"""When no arm can write a rule and the sentence is about something the drawings can only say, the rule "the set mentions it" is
offered: it fails when the set never mentions the thing and never passes on its own."""

import handmade

from reviewpulse.factgraph.convert import to_graph, to_inputs
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.checked import checked_draft
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.interpreter.findings import to_findings
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Program
from reviewpulse.rules.clauses import split_text
from reviewpulse.schema import Prov, TextItem


class Declines:
    """A model that never produces a usable answer: every model arm declines."""
    model = "fake"

    def complete(self, system, user, schema):
        return {}


def _graph(*notes):
    m = handmade.build()
    m.sheet.texts = [TextItem(id=f"n{i}", text=t, bbox=(0, -i, 5, -i + 0.2), prov=Prov(source="vector", stage="test"))
                     for i, t in enumerate(("LIVING ROOM", *notes))]
    return from_building(m, complete=True)


def _draft(text, graph):
    doc = f"Art. 1: {text}\n"
    ctx = assemble_context("doc", doc, split_text(doc), "Art. 1")
    return checked_draft(ctx, to_inputs(graph), graph, Declines())


def _run(out, graph):
    program = Program.model_validate(out["program"])
    return run_program(program, to_inputs(graph), graph=to_graph(graph), include_drafts=True)["outcome"]


def test_a_set_that_never_mentions_the_item_gets_a_warning_never_a_failure():
    graph = _graph()
    out = _draft("Smoke alarms shall be installed in each bedroom.", graph)
    assert out["status"] == "DRAFTED" and out["arm"] == "expr_mention" and "smoke_alarm_notes" in out["readback"]
    assert any("only checks that the drawing set mentions" in n for n in out["notes"])
    assert _run(out, graph) == "VIOLATED"                   # the rule itself does not hold ...
    program = Program.model_validate(out["program"])
    assert program.advisory
    found, _ = to_findings(program, to_inputs(graph), to_graph(graph))
    assert [f.verdict for f in found] == ["WARNING"] and "applies" in found[0].message      # ... and a person is asked to look


def test_a_set_that_mentions_it_is_never_reported_satisfied():
    graph = _graph("PROVIDE SMOKE DETECTOR IN EACH BEDROOM")
    out = _draft("Smoke alarms shall be installed in each bedroom.", graph)
    assert _run(out, graph) == "UNRESOLVED"                 # the mention is there; where and how many is for a person


def test_two_kinds_in_one_sentence_are_both_required():
    out = _draft("Show smoke alarms and carbon monoxide alarms on the plan.", _graph())
    assert "smoke_alarm_notes" in out["readback"] and "co_alarm_notes" in out["readback"]


def test_a_sentence_that_negates_or_excuses_stays_declined():
    for text in ("Sprinklers are not required in detached garages.", "A handrail is required unless the stair has fewer than four risers."):
        out = _draft(text, _graph())
        assert out["status"] != "DRAFTED", text


def test_a_sentence_about_nothing_the_notes_cover_stays_declined():
    out = _draft("The contractor shall submit the soil report before work starts.", _graph())
    assert out["status"] != "DRAFTED"


def test_the_arm_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("REVIEWPULSE_MENTIONS", "off")
    assert _draft("Smoke alarms shall be installed in each bedroom.", _graph())["status"] != "DRAFTED"
