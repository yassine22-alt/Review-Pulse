"""Limits: several limits, an exception, "at least one", and parts the plan cannot show. The model chooses; a program writes."""

import re
from types import SimpleNamespace

import handmade
import pytest

from reviewpulse.factgraph.convert import to_catalogue
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.rules.clauses import split_text
from reviewpulse.xeval.expr_ir import to_text
from reviewpulse.xeval.limits_arm import draft_limits, read_limits


class Chooses:
    """Answers each kind of question by its words: collection, fact (by the limit's fragment), categories, excluded, flag, quantifier."""

    def __init__(self, collection="rooms", facts=None, values=(), excluded=(), flag="none", quantifier="every"):
        self.collection, self.facts, self.values = collection, facts or {}, list(values)
        self.excluded, self.flag, self.quantifier = list(excluded), flag, quantifier

    def complete(self, system, user, schema):
        key = next(iter(schema["properties"]))
        if key == "values":
            about_the_exception = "are excluded" in system or any(w in user.lower() for w in ("except", "sauf", "ausgenommen"))
            return {"values": self.excluded if about_the_exception else self.values}
        if "Which kind of thing" in system:
            return {"choice": self.collection}
        if "narrow them by one of these" in system:
            return {"choice": self.flag}
        if "Must every one" in system:
            return {"choice": self.quantifier}
        sentence = user if key == "fact" else system        # the quantity question carries its fragment in the user message
        fact = next((f for hint, f in self.facts.items() if hint in sentence), "none")
        return {"fact": fact} if key == "fact" else {"choice": fact}


def item_for(sentence: str):
    cat = to_catalogue(from_building(handmade.build(), complete=True))
    text = f"Art. 1 {sentence}\n"
    ctx = assemble_context("d", text, split_text(text), "Art. 1")
    return SimpleNamespace(id="x", text=sentence, catalogue=cat, lang=None, ctx=ctx)


@pytest.mark.parametrize("sentence,n,exception,existential", [
    ("Habitable rooms must be min. 70 sq ft except kitchens, also min. 7 ft in any dimension.", 2, True, False),
    ("Stairway risers must be max. 8.25 in, treads min. 9 in.", 2, False, False),
    ("1 egress door required min. 32 in.", 1, False, True),
    ("Doors shall be at least 0.9 m wide.", 1, False, False),
])
def test_the_limits_of_a_sentence_are_read_by_program(sentence, n, exception, existential):
    reading = read_limits(sentence)
    assert reading is not None
    assert len(reading.limits) == n and bool(reading.exception) == exception and reading.existential == existential


@pytest.mark.parametrize("sentence", [
    "Doors shall be 0.8 m or 0.9 m wide.",                              # two alternatives
    "Corridors shall be between 0.9 m and 1.3 m wide.",                 # a range
    "Where a room has one door, that door shall be at least 0.9 m.",    # a condition
    "No door shall be narrower than 0.8 m.",                            # a negation
    "Corridors shall be wide.",                                         # no limit
])
def test_a_sentence_that_is_not_a_set_of_limits_is_left_to_the_free_form_arm(sentence):
    assert read_limits(sentence) is None


def test_two_limits_and_an_exception_become_one_rule():
    item = item_for("Habitable rooms must have a floor area of at least 6.5 m2 except kitchens, also a minimum width of at least 2.1 m.")
    d = draft_limits("expr_limits", item, Chooses(facts={"6.5": "area_m2", "2.1": "min_width_m"},
                                                  excluded=["kitchen"]))
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "area_m2" in text and "min_width_m" in text and "!= 'kitchen'" in text and "forall" in text
    assert not d.program.not_checked


SENTENCE = "Each bedroom shall have a floor area of at least 9 m2, a minimum width of at least 2.2 m and a ceiling height of at least 2.4 m."


def test_a_limit_the_plan_cannot_show_is_listed_and_the_rest_is_still_checked():
    item = item_for(SENTENCE)
    d = draft_limits("expr_limits", item, Chooses(facts={"9 m2": "area_m2", "2.2": "min_width_m"}, values=["bedroom"]))
    assert d.program is not None, d.detail
    assert len(d.program.not_checked) == 1 and "2.4" in d.program.not_checked[0]
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "area_m2" in text and "min_width_m" in text


def test_nothing_the_plan_provides_means_no_rule():
    assert draft_limits("expr_limits", item_for(SENTENCE), Chooses(values=["bedroom"])).program is None


def test_a_violated_covered_part_is_a_violation_but_a_satisfied_one_is_never_a_pass():
    item = item_for(SENTENCE)
    d = draft_limits("expr_limits", item, Chooses(facts={"9 m2": "area_m2", "2.2": "min_width_m"}, values=["bedroom"]))
    assert d.program is not None, d.detail
    from reviewpulse.interpreter.schema import Inputs

    def inputs(area, width):
        bindings = {"room_type": {"kind": "string"}, "area_m2": {"kind": "number", "unit": "m2"},
                    "min_width_m": {"kind": "number", "unit": "m"}}
        def fact(v):
            return {"value": v, "source": "t", "trusted": True}

        facts = {"r1": {"room_type": fact("bedroom"), "area_m2": fact(area), "min_width_m": fact(width)}}
        return Inputs.model_validate({"bindings": bindings, "facts": facts,
                                      "collections": {"rooms": {"items": ["r1"], "complete": True, "trusted": True}}, "graph_complete": True})

    assert run_program(d.program, inputs(6.0, 3.0), include_drafts=True)["outcome"] == "VIOLATED"
    assert run_program(d.program, inputs(12.0, 3.0), include_drafts=True)["outcome"] == "UNRESOLVED"
    _ = re


@pytest.mark.parametrize("sentence,op,literal", [
    ("The dwelling shall have at least one exit door.", "ge", "1"),
    ("Each building shall have no more than 3 storeys.", "le", "3"),
    ("Au moins deux sorties sont exigées.", "ge", "2"),
    ("Mindestens zwei Ausgänge müssen vorhanden sein.", "ge", "2"),
])
def test_a_limit_on_a_number_of_things_is_read_with_its_cue(sentence, op, literal):
    reading = read_limits(sentence)
    assert reading is not None and len(reading.limits) == 1
    limit = reading.limits[0]
    assert limit.op == op and limit.literal == literal and limit.count


@pytest.mark.parametrize("sentence", [
    "Chaque pièce doit avoir une porte.",        # "une" is the article here, not a count
    "Un espace cuisine offre un espace de manoeuvre.",
    "Every bedroom shall have a window.",
])
def test_the_word_for_one_that_is_also_an_article_is_not_a_limit(sentence):
    assert read_limits(sentence) is None


def test_a_count_of_exits_becomes_a_rule_on_the_building():
    item = item_for("The dwelling shall have at least one exit door.")
    d = draft_limits("expr_limits", item, Chooses(collection="whole", facts={"one": "links_to_exit"}))
    assert d.program is not None, d.detail
    assert "links_to_exit" in to_text(d.program.model_dump(mode="json")["requirement"])


def test_a_class_word_the_document_does_not_define_means_the_default_group():
    from reviewpulse.xeval.terms import default_groups, with_default_groups

    kinds = {"room_type": ["bathroom", "bedroom", "corridor", "kitchen", "living", "wc"]}
    groups = default_groups(kinds)["room_type"]
    assert groups["habitable room"] == ["bedroom", "kitchen", "living"]
    assert groups["sleeping room"] == ["bedroom"] and groups["wet room"] == ["bathroom", "wc"]
    # the document's own definition wins over the default
    merged = with_default_groups({"room_type": {"habitable room": ["bedroom", "living"]}}, kinds)
    assert merged["room_type"]["habitable room"] == ["bedroom", "living"]
    # a plan that knows none of a class's kinds is not offered it
    assert "habitable room" not in default_groups({"room_type": ["bathroom", "wc"]}).get("room_type", {})


def test_habitable_rooms_with_an_exception_become_one_rule_on_the_group():
    sentence = "Habitable rooms must have a floor area of at least 6.5 m2 except kitchens, also a minimum width of at least 2.1 m."
    item = item_for(sentence)
    from reviewpulse.xeval.terms import with_default_groups

    item.catalogue["groups"] = with_default_groups({}, item.catalogue["kinds"])
    d = draft_limits("expr_limits", item, Chooses(facts={"6.5": "area_m2", "2.1": "min_width_m"},
                                                  values=["habitable room"], excluded=["kitchen"]))
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "'bedroom'" in text and "'living'" in text and "!= 'kitchen'" in text
