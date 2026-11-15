"""Documents written for US readers: feet and inch marks, fractions of an inch, s.f.; a terse checklist item is a plain limit."""

import pytest

from reviewpulse.interpreter.quantities import normalise_quantities, us_typography
from reviewpulse.xeval.slot_arm import plan_limit


@pytest.mark.parametrize("before,after", [
    ("Hallways must be min. 3' wide.", "Hallways must be min. 3 ft wide."),
    ("1 egress door required min. 32\".", "1 egress door required min. 32 in."),
    ("risers max. 8 1/4\", treads min. 9\"", "risers max. 8.25 in, treads min. 9 in"),
    ("headroom must be min. 6'8\".", "headroom must be min. 80 in."),
    ("Attic access 22\"x30\" min.", "Attic access 22 in x 30 in min."),
    ("min. 7' in any dimension", "min. 7 ft in any dimension"),
    ("a sloping ceiling of 5.5' or 1/2\" less", "a sloping ceiling of 5.5 ft or 0.5 in less"),
])
def test_us_marks_become_numbers_and_unit_words(before, after):
    assert us_typography(before) == after


def test_square_feet_in_all_the_ways_checklists_write_them():
    for text in ("70 s.f.", "70 sf", "70 sq. ft.", "70 sq ft"):
        assert us_typography(f"min. {text}").startswith("min. 70 sq ft")


def test_a_quoted_word_or_plain_number_is_left_alone():
    assert us_typography('the "term" is 5 and 12 apply') == 'the "term" is 5 and 12 apply'


@pytest.mark.parametrize("sentence,op,unit", [
    ("Hallways must be min. 3' wide.", "ge", "3 ft"),
    ("Each egress door must be min. 32\".", "ge", "32 in"),
    ("Habitable rooms must be at least 70 s.f.", "ge", "70 ft2"),
    ("Footing depth 36\" min.", "ge", "36 in"),
])
def test_a_terse_checklist_item_is_a_plain_limit(sentence, op, unit):
    got = plan_limit(normalise_quantities(sentence))
    assert got is not None and got[0] == op and got[1] == unit


@pytest.mark.parametrize("before,after", [
    ("- Hallways must be min. 3' wide. 311.6", "- Hallways must be min. 3 ft wide."),
    ("min. 70 s.f. except kitchens, also min. 7' in any dimension. 304.1, 304.2",
     "min. 70 sq ft except kitchens, also min. 7 ft in any dimension."),
    ("Walls less than 5' from a lot line must be fire rated. Table 302.1(1)", "Walls less than 5 ft from a lot line must be fire rated."),
    ("Stairs must have handrails (FBC-R R311.7, R312.1) and landings.", "Stairs must have handrails and landings."),
    ("Doors shall be at least 0.9 m wide per Section 1011.5.2.", "Doors shall be at least 0.9 m wide."),
    ("Exits must be 12.5 ft apart (see 1007.1.1).", "Exits must be 12.5 ft apart."),
    ("risers max. 8 1/4\", treads min. 9\". PA UCC", "risers max. 8.25 in, treads min. 9 in."),
    ("Smoke alarms required on each story. 314.3", "Smoke alarms required on each story."),
])
def test_citations_of_code_sections_are_not_figures_of_the_requirement(before, after):
    assert normalise_quantities(before) == after


@pytest.mark.parametrize("text", [
    "The distance shall not exceed 311.6 m.", "Slope 1:12 max and 1.5 m clear.", "At least 12.5 % of the floor area.",
    "Rooms of 100.5 sq ft or more.", "Doors shall be 0.9 m wide.",
])
def test_a_real_quantity_with_a_unit_is_never_taken_for_a_citation(text):
    assert normalise_quantities(text) == text


def test_a_rule_cites_the_clause_as_written_even_when_the_sentence_read_was_normalised():
    """The sentence a program reads has its feet marks and section numbers rewritten; the quotation must still be the original."""
    from types import SimpleNamespace

    import handmade

    from reviewpulse.factgraph.convert import to_catalogue
    from reviewpulse.factgraph.from_building import from_building
    from reviewpulse.interpreter.checked import checked_draft
    from reviewpulse.interpreter.context import assemble_context
    from reviewpulse.interpreter.schema import Inputs
    from reviewpulse.rules.clauses import split_text

    text = "- Hallways must be min. 3' wide. 311.6\n"
    context = assemble_context("d", text, split_text(text), split_text(text)[0].id)
    graph = from_building(handmade.build(), complete=True)
    inputs = Inputs.model_validate({"bindings": {}, "facts": {}, "collections": {}, "graph_complete": True})
    answers = {"collection": "rooms", "fact": "min_width_m", "values": ["corridor"]}

    class Model:
        model = "scripted"

        def complete(self, system, user, schema):
            key = next(iter(schema["properties"]))
            if key == "values":
                return {"values": answers["values"]}
            if "Which kind of thing" in system:
                return {"choice": answers["collection"]}
            if key == "fact":
                return {"fact": answers["fact"]}
            return {"choice": "none"}

    out = checked_draft(context, inputs, graph, Model())
    assert out["program"] is not None, out["reason"] + str(out.get("tried"))
    assert out["program"]["sources"][0]["quote"].startswith("- Hallways must be min. 3' wide.")
    assert out["tried"][0].startswith("slots")
    _ = SimpleNamespace, to_catalogue


@pytest.mark.parametrize("text,count", [
    ("1 egress door required min. 32 in. Door must not require a key to open from inside.", 2),
    ("Habitable rooms must be min. 70 sq ft except kitchens, also min. 7 ft in any dimension.", 1),
    ("Risers max. 8.25 in, treads min. 9 in. Handrails required.", 2),
    ("Hallways must be min. 3 ft wide.", 1),
])
def test_a_clause_is_split_into_sentences_but_not_at_abbreviations(text, count):
    from reviewpulse.interpreter.checked import sentences

    assert len(sentences(text)) == count


def test_a_category_is_named_by_the_word_with_a_short_ending():
    from reviewpulse.xeval.verify import _names

    assert _names("stair", "stairways must be 3 ft wide") and _names("bedroom", "all bedrooms")
    assert not _names("bed", "bedroom") and not _names("room", "broom closet")


def test_a_model_that_could_not_be_reached_is_not_reported_as_a_clause_that_cannot_be_checked():
    from types import SimpleNamespace

    from reviewpulse.xeval.status import clause_status

    draft = SimpleNamespace(program=None, raw=None, stage="decode", detail="RuntimeError: Ollama not reachable at http://localhost:11434")
    status, reason = clause_status(draft)
    assert status == "UNRESOLVED" and "could not be reached" in reason


def test_a_title_never_states_an_obligation():
    from reviewpulse.interpreter.checked import strip_title

    assert strip_title("Dead ends. Corridors shall not exceed 6 m.") == "Corridors shall not exceed 6 m."
    assert strip_title("Hallways must be min. 3 ft wide.") == "Hallways must be min. 3 ft wide."


def test_a_table_row_is_read_with_the_names_of_its_columns():
    from reviewpulse.interpreter.checked import clause_body
    from reviewpulse.interpreter.context import assemble_context
    from reviewpulse.rules.clauses import split_text

    text = "Table 1\n\n| Room | Minimum area |\n| --- | --- |\n| Bedroom | 7 m2 |\n| Kitchen | 6 m2 |\n"
    cl = split_text(text)
    row = next(c for c in cl if c.kind == "table_row" and "Bedroom" in c.text)
    body = clause_body(assemble_context("d", text, cl, row.id))
    assert "Room: Bedroom" in body and "Minimum area: 7" in body


def test_a_declined_clause_says_what_it_seems_to_need(monkeypatch):
    from types import SimpleNamespace

    from reviewpulse.interpreter import checked

    def declined(context, catalogue, body, client, **_):
        return {"status": "UNRESOLVED", "reason": "no rule that matches the sentence could be written", "model": "m",
                "external": False, "program": None, "readback": None, "notes": []}

    monkeypatch.setattr(checked, "_attempt", declined)
    monkeypatch.setattr(checked, "catalogue_from", lambda inputs, graph: {"kinds": {}, "kind_labels": {}})
    monkeypatch.setattr(checked, "clause_body", lambda c: "Smoke alarms are required in each bedroom.")
    monkeypatch.setattr("reviewpulse.xeval.terms.document_groups", lambda *a: {})

    class Model:
        model = "m"

        def complete(self, system, user, schema):
            return {"needs": "alarm symbols"}

    out = checked.checked_draft(SimpleNamespace(text="t"), None, None, Model())
    assert out["status"] == "UNRESOLVED" and out["needs"] == "alarm symbols"
    assert out["reason"].startswith("no rule that matches") and "alarm symbols" in out["reason"]


def test_an_unreachable_model_is_not_explained_as_a_need(monkeypatch):
    from types import SimpleNamespace

    from reviewpulse.interpreter import checked

    monkeypatch.setattr(checked, "_attempt", lambda *a, **k: {
        "status": "UNRESOLVED", "reason": "the reading model could not be reached, so this clause was not read", "model": "m",
        "external": False, "program": None, "readback": None, "notes": []})
    monkeypatch.setattr(checked, "catalogue_from", lambda inputs, graph: {"kinds": {}, "kind_labels": {}})
    monkeypatch.setattr(checked, "clause_body", lambda c: "Doors must open outwards.")
    monkeypatch.setattr("reviewpulse.xeval.terms.document_groups", lambda *a: {})

    class Model:
        model = "m"

        def complete(self, system, user, schema):
            return {"needs": "should never be asked"}

    out = checked.checked_draft(SimpleNamespace(text="t"), None, None, Model())
    assert "needs" not in out and "should never" not in out["reason"]
