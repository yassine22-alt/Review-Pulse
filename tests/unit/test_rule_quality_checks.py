"""Rules that cannot fail, rules that drop an alternative, quotations with stray escapes, and requirements about the whole sheet."""

from types import SimpleNamespace

import handmade
from test_relation_arm import Relates, item_for
from test_verify import CAT, SRC, TEXT, bedroom_rule, rule

from reviewpulse.interpreter.context import assemble_context
from reviewpulse.rules.clauses import split_text
from reviewpulse.xeval.drafters import fix_spans
from reviewpulse.xeval.expr_ir import to_text
from reviewpulse.xeval.relation_arm import draft_relation
from reviewpulse.xeval.synth import binary, fact, lit, logic, setop
from reviewpulse.xeval.verify import blocking, verify


def codes(program, text=TEXT, cat=CAT):
    return {i.code for i in blocking(verify(program, text, cat))}


def test_a_rule_that_can_never_fail_is_refused():
    members = binary("eq", fact("room_type"), lit("bedroom"))
    assert "vacuous" in codes(rule(lit(True)), "Smoke alarms are required.")
    assert "vacuous" in codes(rule(setop("forall", "rooms", lit(True), members)), "Bedrooms need smoke alarms.")
    assert "vacuous" in codes(rule(setop("forall", "rooms", fact("room_type"), members)), "Bedrooms need smoke alarms.")
    assert "vacuous" in codes(rule(setop("forall", "rooms", binary("eq", fact("room_type"), lit("bedroom")), members)), "Bedrooms are bedrooms.")


def test_a_rule_that_tests_a_measure_a_count_or_a_route_is_not_vacuous():
    assert "vacuous" not in codes(bedroom_rule())
    assert "vacuous" not in codes(rule(binary("ge", setop("count", "doors"), lit(2, "count"))), "At least 2 doors.")


def test_a_sentence_with_an_alternative_needs_a_rule_with_an_or():
    text = "Bedrooms must have a window of 0.28 m2 or a mechanical exhaust."
    where = binary("eq", fact("room_type"), lit("bedroom"))
    one = rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(0.28, "m2")), where))
    both = rule(setop("forall", "rooms", logic("any", binary("ge", fact("area_m2"), lit(0.28, "m2")), fact("has_window")), where))
    assert "alternative_dropped" in codes(one, text)
    assert "alternative_dropped" not in codes(both, text)


def test_or_more_is_a_comparison_not_an_alternative():
    where = binary("eq", fact("room_type"), lit("bedroom"))
    r = rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(9.0, "m2")), where))
    assert "alternative_dropped" not in codes(r, "A bedroom has an area of 9 m2 or more.")


def _ctx(text):
    return assemble_context("d", text, split_text(text), split_text(text)[0].id)


def test_a_quotation_with_an_escaped_mark_or_a_check_box_is_still_found_when_its_words_are_in_the_clause():
    text = '- Stairway risers must be max. 8 1/4", treads min. 9".\n'
    ctx = _ctx(text)
    got = fix_spans([{"quote": '- Stairway risers must be max. 8 1/4\\", treads min. 9\\".'}], ctx)
    assert got[0]["quote"].startswith("Stairway risers")
    box = "☐ Site Plan: plans must be to scale.\n"
    assert fix_spans([{"quote": "☐ Site Plan: plans must be to scale."}], _ctx(box))


def test_a_quotation_whose_words_are_not_in_the_clause_is_still_refused():
    import pytest

    with pytest.raises(ValueError):
        fix_spans([{"quote": "Stairways must be 5 ft wide."}], _ctx("- Stairway risers must be max. 8 in.\n"))


def test_a_requirement_about_the_whole_sheet_becomes_a_rule_on_the_sheet():
    item = item_for("Plans must be to scale.")
    model = Relates("has_property")
    model.prop = "scale_stated"
    d = draft_relation("expr_relation", item, model)
    assert d.program is not None, d.detail
    assert to_text(d.program.model_dump(mode="json")["requirement"]).replace("(", "").replace(")", "") == "building.scale_stated == true"
    _ = (SRC, SimpleNamespace, handmade)


class _Yes:
    def __init__(self, answer):
        self.answer = answer

    def complete(self, system, user, schema):
        return {"choice": self.answer}


def test_a_category_the_sentence_names_is_added_only_when_the_model_confirms_it_both_ways():
    from test_relation_arm import item_for

    from reviewpulse.xeval.slot_arm import confirm_named

    cat = item_for("Stairways must be min. 3 ft wide.").catalogue
    kf = "room_type"
    assert confirm_named(_Yes("yes"), "Stairways must be min. 3 ft wide.", cat, kf, {}, []) == ["stairs"]
    assert confirm_named(_Yes("no"), "Stairways must be min. 3 ft wide.", cat, kf, {}, []) == []
    assert confirm_named(_Yes("yes"), "Hallways must be wide.", cat, kf, {}, []) == ["corridor"]
    assert confirm_named(_Yes("yes"), "Stairways must be wide.", cat, kf, {}, ["bedroom"]) == ["stairs"]       # a named, confirmed kind wins
    assert confirm_named(_Yes("no"), "Stairways must be wide.", cat, kf, {}, ["bedroom"]) == ["bedroom"]        # nothing confirmed: the pick stands
    assert confirm_named(_Yes("yes"), "Plans must be to scale.", cat, kf, {}, []) == []                        # "scale" is not a stair here


def test_examples_in_parentheses_are_not_part_of_the_requirement():
    from reviewpulse.interpreter.quantities import normalise_quantities

    assert normalise_quantities("Label all rooms (e.g. bedrooms, kitchen, etc.) including the basement.") ==         "Label all rooms including the basement."
    assert normalise_quantities("Doors (such as exit doors) must be 0.9 m wide.") == "Doors must be 0.9 m wide."
    assert normalise_quantities("Rooms (existing and proposed) must be labelled.") == "Rooms (existing and proposed) must be labelled."


class _Sheet:
    """Answers the sheet question with a list of properties, whatever the order of the options."""

    def __init__(self, props, about=True):
        self.props = props
        self.about = about          # whether the model says the sentence is about the drawing itself

    def complete(self, system, user, schema):
        if "DRAWING ITSELF" in system:
            return {"values": self.props}
        if "What does it require?" in system:
            return {"choice": "whole" if self.about else "thing"}
        return {"choice": "none"}


def test_a_scaled_and_dimensioned_sheet_becomes_one_rule_on_the_sheet():
    from test_relation_arm import item_for

    item = item_for("The submission shall include a scaled and dimensioned floor plan.")
    d = draft_relation("expr_relation", item, _Sheet(["scale_stated", "is_dimensioned"]))
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "scale_stated" in text and "is_dimensioned" in text


def test_a_sentence_that_only_mentions_dimensions_is_not_a_sheet_requirement():
    from test_relation_arm import item_for

    item = item_for("Attic access located with opening dimensions.")
    assert draft_relation("expr_relation", item, _Sheet(["is_dimensioned"], about=False)).program is None


def test_a_sentence_about_spaces_is_not_taken_for_a_sheet_requirement():
    from test_relation_arm import item_for

    item = item_for("No door connects a garage directly to a bedroom.")
    assert draft_relation("expr_relation", item, _Sheet([])).program is None


def test_a_sentence_that_names_rooms_is_not_a_sheet_requirement():
    from test_relation_arm import item_for

    item = item_for("Dimension and label all rooms.")
    assert draft_relation("expr_relation", item, _Sheet(["is_dimensioned"])).program is None


def test_has_property_on_a_sentence_about_rooms_never_offers_the_sheet_properties():
    from test_relation_arm import item_for

    item = item_for("Label all rooms.")
    model = Relates("has_property")
    model.prop = "is_dimensioned"
    assert draft_relation("expr_relation", item, model).program is None


def test_a_subject_the_model_pads_with_unnamed_categories_is_cut_back_to_what_the_sentence_names():
    from test_relation_arm import item_for

    item = item_for("Every room must have a window.")
    model = Relates("has_property", subject=["bedroom", "kitchen", "living"])
    model.prop = "has_window"
    d = draft_relation("expr_relation", item, model)
    assert d.program is not None, d.detail
    text = to_text(d.program.model_dump(mode="json")["requirement"])
    assert "bedroom" not in text and "has_window" in text


def test_a_requirement_about_doors_or_windows_is_not_applied_to_every_room():
    from test_relation_arm import item_for

    item = item_for("Doors shall open outwards.")
    model = Relates("has_passage")
    model.every = False                    # the model says the sentence is not about every room or space
    assert draft_relation("expr_relation", item, model).program is None


def test_a_rule_that_only_says_a_size_is_above_zero_is_vacuous():
    anyroom = setop("forall", "rooms", binary("gt", fact("area_m2"), lit(0, "m2")), binary("eq", fact("room_type"), lit("bedroom")))
    assert "vacuous" in codes(rule(anyroom), "Square Footage")
    flipped = setop("forall", "rooms", binary("lt", lit(0, "m2"), fact("area_m2")), binary("eq", fact("room_type"), lit("bedroom")))
    assert "vacuous" in codes(rule(flipped), "Square Footage")
    real = setop("forall", "rooms", binary("gt", fact("area_m2"), lit(7, "m2")), binary("eq", fact("room_type"), lit("bedroom")))
    assert "vacuous" not in codes(rule(real), "Bedrooms must be larger than 7 m2.")


def test_a_bare_heading_is_a_label_and_not_a_requirement():
    from reviewpulse.interpreter.checked import is_bare_label

    for label in ("Dimensions", "Square Footage", "Compaction", "Slab thickness"):
        assert is_bare_label(label), label
    for sentence in ("Label all rooms", "Plans must be to scale", "Hallways shall be wide"):
        assert not is_bare_label(sentence), sentence
    assert not is_bare_label("Doors 0.9 m")                  # a figure makes it a requirement
    assert not is_bare_label("Doors shall open")             # an obligation word does too


def test_a_long_sentence_about_the_sheet_says_what_the_rule_does_not_check():
    from test_relation_arm import item_for

    long = item_for("Dimensions from grade to finished floor, and from grade to beginning of roofline and to roof peak.")
    d = draft_relation("expr_relation", long, _Sheet(["is_dimensioned"]))
    assert d.program is not None and any("specific items" in n for n in d.program.not_checked)
    short = item_for("All drawings shall be completely dimensioned.")
    d = draft_relation("expr_relation", short, _Sheet(["is_dimensioned"]))
    assert d.program is not None and not d.program.not_checked


def test_a_list_item_under_a_sheet_level_lead_is_not_a_sheet_requirement():
    from test_relation_arm import item_for

    from reviewpulse.interpreter.checked import clause_body
    from reviewpulse.interpreter.context import assemble_context
    from reviewpulse.rules.clauses import split_text

    text = ("A11. Provide a completely dimensioned plot plan showing:\na) Location of the sewer line.\n\nb) North arrow.\n\n"
            "A12. Show the address.\n\nA13. Show the scale.\n")
    clauses = split_text(text)
    parent = next(c for c in clauses if c.id == "A11")
    sub = next(c for c in clauses if c.kind == "subitem")
    assert sub.parent == parent.id
    item = item_for("x")
    for target, expect in ((parent.id, True), (sub.id, False)):
        ctx = assemble_context("d", text, clauses, target)
        item.ctx, item.text = ctx, clause_body(ctx)
        d = draft_relation("expr_relation", item, _Sheet(["is_dimensioned"]))
        assert (d.program is not None) == expect, (target, d.detail)
