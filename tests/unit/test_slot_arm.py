"""Slot filling: the model chooses from short lists, a program writes the rule, the usual checks decide."""

from types import SimpleNamespace

import handmade
import pytest

from reviewpulse.factgraph.convert import to_catalogue
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.rules.clauses import split_text
from reviewpulse.xeval.expr_ir import to_text
from reviewpulse.xeval.slot_arm import draft_slots, plan_limit


class Chooses:
    """Answers the three kinds of question by the key the question's schema asks for."""

    def __init__(self, collection=None, fact=None, values=()):
        self.collection, self.fact, self.values, self.calls = collection, fact, list(values), 0

    def complete(self, system, user, schema):
        self.calls += 1
        key = next(iter(schema["properties"]))
        return {"choice": {"choice": self.collection, "fact": self.fact, "values": self.values}[key]} if key == "choice" else \
            {key: {"fact": self.fact, "values": self.values}[key]}


def item_for(sentence: str):
    cat = to_catalogue(from_building(handmade.build(), complete=True))
    text = f"Art. 1 {sentence}\n"
    ctx = assemble_context("d", text, split_text(text), "Art. 1")
    return SimpleNamespace(id="x", text=sentence, catalogue=cat, lang=None, ctx=ctx)


@pytest.mark.parametrize("sentence,op,literal", [
    ("Every bedroom shall have an area of at least 9 m2.", "ge", "9 m2"),
    ("Chaque porte doit avoir une largeur d'au moins 0,80 m.", "ge", "0.8 m"),
    ("Die Tür muss mindestens 0,90 m breit sein.", "ge", "0.9 m"),
    ("The travel distance shall not exceed 30 m.", "le", "30 m"),
    ("La largeur minimale des circulations intérieures est de 0,90 mètre.", "ge", "0.9 m"),     # the wording is not next to the number
    ("La hauteur maximale est de 1,30 m.", "le", "1.3 m"),
])
def test_a_plain_limit_is_read_by_program(sentence, op, literal):
    got = plan_limit(sentence)
    assert got is not None and got[0] == op and got[1] == literal


@pytest.mark.parametrize("sentence", [
    "Corridors shall be at least 1.2 m wide, except in storage rooms.",       # an exception
    "No door shall be narrower than 0.8 m.",                                   # a negation turns the rule around
    "Doors shall be 0.8 m or 0.9 m wide.",                                     # two limits
    "Where a room has one door, the door shall be at least 0.9 m wide.",       # a condition
    "Every room shall have a window.",                                         # no quantity
    "Les couloirs doivent avoir 1,2 m.",                                       # no comparison wording
    "La largeur minimale est de 0,9 m et la hauteur maximale de 2,5 m.",       # two limits pointing different ways
])
def test_anything_else_is_left_to_the_free_form_arm(sentence):
    assert plan_limit(sentence) is None


def test_the_rule_is_built_from_the_choices():
    item = item_for("Every bedroom shall have a floor area of at least 9 m2.")
    d = draft_slots("expr_slots", item, Chooses("rooms", "area_m2", ["bedroom"]))
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "bedroom" in text and "area_m2" in text and ">= 9 m2" in text


def test_a_door_rule_needs_no_category():
    item = item_for("Chaque porte doit avoir une largeur d'au moins 0,80 m.")
    d = draft_slots("expr_slots", item, Chooses("doors", "width_m", []))
    assert d.program is not None, d.detail


def test_a_declined_sentence_costs_the_model_nothing():
    model = Chooses("rooms", "area_m2", [])
    d = draft_slots("expr_slots", item_for("Corridors shall be at least 1.2 m wide, except in storage rooms."), model)
    assert d.program is None and d.stage == "skip" and model.calls == 0


def test_a_wrong_category_is_caught_by_the_usual_checks():
    item = item_for("Every kitchen shall have a floor area of at least 6 m2.")
    d = draft_slots("expr_slots", item, Chooses("rooms", "area_m2", ["bedroom"]))        # the model chose the wrong category
    assert d.program is None


def test_a_quantity_that_is_not_of_that_collection_is_refused():
    item = item_for("Every door shall have a clear width of at least 0.8 m.")
    d = draft_slots("expr_slots", item, Chooses("doors", "area_m2", []))
    assert d.program is None
