"""Relations: the model chooses the kind of relation and the spaces; a program writes the rule; the usual checks decide."""

import re
from types import SimpleNamespace

import handmade

from reviewpulse.factgraph.convert import to_catalogue
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.rules.clauses import split_text
from reviewpulse.xeval.expr_ir import to_text
from reviewpulse.xeval.relation_arm import draft_relation


class Relates:
    """Answers each question by its role: the relation, the first and second kind, the subject and the spaces to avoid."""

    def __init__(self, relation, first=None, second=None, subject=(), avoid=()):
        self.relation, self.first, self.second = relation, first, second
        self.subject, self.avoid, self.calls = list(subject), list(avoid), 0

    def complete(self, system, user, schema):
        self.calls += 1
        key = next(iter(schema["properties"]))
        if key == "choice":
            if "Which kind of requirement" in system:
                return {"choice": self.relation}
            if "SECOND kind" in system:
                return {"choice": self.second}
            if "FIRST kind" in system:
                return {"choice": self.first}
            if "THEMSELVES have the route" in system:
                c = re.search(r"category '([^']*)'", system).group(1).replace(" ", "_")
                return {"choice": "yes" if c in self.subject else "no"}
            if "every room or space" in system:           # is the subject really every space? (self.every, default yes)
                return {"choice": "spaces" if getattr(self, "every", True) else "something_else"}
            if "Which property of" in system:
                return {"choice": getattr(self, "prop", "none")}
            return {"choice": "EXIT"}
        if "NOT pass through" in system:
            return {"values": self.avoid}
        if getattr(self, "confuse", False):          # a small model lists the spaces to avoid among the subjects as well
            return {"values": sorted(set(self.subject) | set(self.avoid))}
        return {"values": self.subject}


def item_for(sentence: str):
    cat = to_catalogue(from_building(handmade.build(), complete=True))
    text = f"Art. 1 {sentence}\n"
    ctx = assemble_context("d", text, split_text(text), "Art. 1")
    return SimpleNamespace(id="x", text=sentence, catalogue=cat, lang=None, ctx=ctx)


def test_a_forbidden_connection_is_written_from_the_choices():
    item = item_for("No door or opening connects a garage directly to a bedroom.")
    d = draft_relation("expr_relation", item, Relates("no_link", first="garage", second="bedroom"))
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "not linked" in text and "garage" in text and "bedroom" in text
    # the two sides are different spaces: a bedroom joined to another bedroom is not what the sentence forbids
    assert text.count("'bedroom'") == 1 and text.count("'garage'") == 1


def test_connections_between_spaces_of_one_kind_need_the_same_option():
    item = item_for("No bedroom is joined directly to another bedroom.")
    d = draft_relation("expr_relation", item, Relates("no_link", first="bedroom", second="same"))
    assert d.program is not None, d.detail
    assert "bedroom" in to_text(d.program.model_dump(mode="json")["requirement"])


def test_a_route_that_must_avoid_some_spaces():
    item = item_for("Every bedroom reaches an exit without passing through a bathroom or a WC.")
    d = draft_relation("expr_relation", item, Relates("route", subject=["bedroom"], avoid=["bathroom", "wc"]))
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "reaches" in text and "bathroom" in text and "wc" in text


def test_a_sentence_with_a_figure_is_left_to_the_free_form_arm():
    item = item_for("Every bedroom shall be joined to a corridor by a door at least 0.8 m wide.")
    model = Relates("must_link", first="bedroom", second="corridor")
    d = draft_relation("expr_relation", item, model)
    assert d.program is None and model.calls == 0


def test_a_sentence_with_a_condition_is_left_to_the_free_form_arm():
    item = item_for("Where a room has a single door, that door shall lead to a corridor.")
    model = Relates("must_link", first="bedroom", second="corridor")
    assert draft_relation("expr_relation", item, model).program is None and model.calls == 0


def test_no_relation_chosen_means_no_rule():
    item = item_for("Walls shall be finished in a light colour.")
    assert draft_relation("expr_relation", item, Relates("none")).program is None


def test_a_wrong_choice_is_caught_by_the_sentence_checks():
    # the sentence names a garage and a bedroom; a rule about a kitchen is refused by the same checks as any draft
    item = item_for("No door or opening connects a garage directly to a bedroom.")
    d = draft_relation("expr_relation", item, Relates("no_link", first="kitchen", second="bedroom"))
    assert d.program is None


def test_choosing_every_category_means_every_space():
    item = item_for("Every enclosed room has at least one door or opening.")
    everything = ["bathroom", "bedroom", "corridor", "entry", "garage", "kitchen", "living", "office", "stairs", "storage",
                  "terrace", "wc"]
    d = draft_relation("expr_relation", item, Relates("has_passage", subject=everything))
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "room_type" not in text and ">= 1" in text


def test_accented_names_are_recognised_in_the_sentence():
    from reviewpulse.xeval.verify import fold_accents

    assert fold_accents("Küche") == "kuche" and fold_accents("séjour") == "sejour" and fold_accents("Straße") == "strasse"
    item = item_for("Ein Badezimmer darf nicht direkt mit der Küche verbunden sein.")
    d = draft_relation("expr_relation", item, Relates("no_link", first="bathroom", second="kitchen"))
    assert d.program is not None, d.detail
    item = item_for("Le séjour doit communiquer directement avec la cuisine.")
    assert draft_relation("expr_relation", item, Relates("must_link", first="living", second="kitchen")).program is not None


def test_spaces_to_avoid_are_not_taken_for_the_subject():
    item = item_for("Every bedroom or kitchen reaches an exit without passing through a bathroom or a WC.")
    model = Relates("route", subject=["bedroom", "kitchen"], avoid=["bathroom", "wc"])
    model.confuse = True              # the model lists the spaces to avoid among the subjects too
    d = draft_relation("expr_relation", item, model)
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    head = text.split(":")[0]            # the "forall ... where <subject>" part
    assert "bedroom" in head and "kitchen" in head and "bathroom" not in head and "wc" not in head


def test_a_space_that_is_both_subject_and_to_avoid_keeps_both_roles():
    # "a bedroom reaches an exit without passing through a bedroom other than itself"
    item = item_for("Every bedroom reaches an exit without passing through a bathroom or a bedroom other than itself.")
    d = draft_relation("expr_relation", item, Relates("route", subject=["bedroom"], avoid=["bathroom", "bedroom"]))
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "bedroom" in text.split(":")[0] and "bathroom" in text


def _presence(sentence, subject, prop):
    model = Relates("has_property", subject=subject)
    model.prop = prop
    return draft_relation("expr_relation", item_for(sentence), model)


def test_a_property_every_space_of_a_kind_must_have():
    d = _presence("Every bedroom shall have a window.", ["bedroom"], "has_window")
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "bedroom" in text and "has_window" in text


def test_every_room_must_be_named_on_the_drawing():
    d = _presence("Size and use of all rooms shall be shown on the drawing.", [], "has_label")
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "has_label" in text and "room_type" not in text


def test_no_property_chosen_means_no_rule():
    assert _presence("Every bedroom shall have a window.", ["bedroom"], "none").program is None
