"""The sentence-versus-rule verifier, including the exact failure seen on a real plan (a dropped 'bedroom')."""

from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.synth import binary, fact, lit, logic, setop
from reviewpulse.xeval.verify import blocking, verify

CAT = {"kinds": {"room_type": ["bedroom", "kitchen"]},
       "kind_labels": {"room_type": {"bedroom": ["chambre", "chambres"], "kitchen": ["cuisine"]}}}
SRC = [{"clause": "1", "start": 0, "end": 1, "quote": "x"}]
TEXT = "Bedroom size. A bedroom has a floor area of at least 9.00 m² and a minimum width of at least 2.20 m."


def rule(requirement, **extra):
    return Program.model_validate({"id": "p", "title": "p", "document": "d", "requirement": requirement,
                                   "sources": SRC, **extra})


def bedroom_rule(scoped=True):
    body = logic("all", binary("ge", fact("area_m2"), lit(9.0, "m2")), binary("ge", fact("min_width_m"), lit(2.2, "m")))
    where = binary("eq", fact("room_type"), lit("bedroom")) if scoped else None
    return rule(setop("forall", "rooms", body, where))


def codes(program, text=TEXT, cat=CAT):
    return {i.code for i in blocking(verify(program, text, cat))}


def test_a_correct_rule_passes():
    assert codes(bedroom_rule()) == set()


def test_the_real_failure_a_dropped_category_is_blocked():
    assert codes(bedroom_rule(scoped=False)) == {"scope_dropped"}


def test_a_number_the_sentence_never_states_is_blocked():
    wrong = rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(10.0, "m2")),
                       binary("eq", fact("room_type"), lit("bedroom"))))
    assert "number_not_in_sentence" in codes(wrong, "A bedroom has a floor area of at least 9 m2.")


def test_a_number_the_sentence_states_but_the_rule_ignores_is_blocked():
    only_area = rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(9.0, "m2")),
                           binary("eq", fact("room_type"), lit("bedroom"))))
    assert "number_ignored" in codes(only_area)


def test_comparison_direction_must_follow_the_wording():
    text = "A bedroom has a floor area of at most 12 m2."
    wrong = rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(12.0, "m2")),
                       binary("eq", fact("room_type"), lit("bedroom"))))
    right = rule(setop("forall", "rooms", binary("le", fact("area_m2"), lit(12.0, "m2")),
                       binary("eq", fact("room_type"), lit("bedroom"))))
    assert codes(wrong, text) == {"direction"} and codes(right, text) == set()


def test_cues_after_the_number_and_bare_counts():
    text = "At least 2 doors shall be wide, except in buildings of 3 storeys or fewer."
    cat = {"kinds": {}}
    ok = rule(binary("ge", setop("count", "doors"), lit(2, "count")),
              exemption=binary("le", fact("storeys", "building"), lit(3, "count")))
    bad = rule(binary("ge", setop("count", "doors"), lit(2, "count")),
               exemption=binary("ge", fact("storeys", "building"), lit(3, "count")))
    assert codes(ok, text, cat) == set() and codes(bad, text, cat) == {"direction"}


def test_french_labels_match_and_article_une_is_not_a_number():
    text = "Chaque chambre doit avoir une surface d'au moins 9 m²."
    good = rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(9.0, "m2")),
                      binary("eq", fact("room_type"), lit("bedroom"))))
    assert codes(good, text) == set()
    assert codes(rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(9.0, "m2")))), text) == {"scope_dropped"}


def test_source_files_contain_no_stray_control_characters():
    """A regex written as \b once became a literal backspace and silently disabled a check."""
    from pathlib import Path

    for path in Path("src/reviewpulse/xeval").glob("*.py"):
        assert not [c for c in path.read_text(encoding="utf-8") if ord(c) < 32 and c not in "\n\r\t"], path


def test_article_and_table_references_are_not_thresholds():
    text = "Subject to Article 4, each bedroom shall have a floor area of at least 9 m2. See also Table 2 and Annex 3."
    assert codes(rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(9.0, "m2")),
                            binary("eq", fact("room_type"), lit("bedroom")))), text) == set()


# ---- any language, any script ------------------------------------------------------------------------------

DE = {"kinds": {"room_type": ["bedroom"]}, "kind_labels": {"room_type": {"bedroom": ["Schlafzimmer"]}}}


def bedroom_with(op="ge", value=9.0, unit="m2", prop="area_m2"):
    return rule(setop("forall", "rooms", binary(op, fact(prop), lit(value, unit)),
                      binary("eq", fact("room_type"), lit("bedroom"))))


def test_german_wording_is_checked_through_the_data_table():
    text = "Jedes Schlafzimmer muss eine Fläche von mindestens 9 m² haben."
    assert codes(bedroom_with("ge"), text, DE) == set()
    assert codes(bedroom_with("le"), text, DE) == {"direction"}
    assert codes(rule(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(9.0, "m2")))), text, DE) == {"scope_dropped"}


def test_an_unsupported_language_is_reported_not_guessed():
    text = "Her yatak odası en az 9 m² olmalıdır."          # Turkish: no wording table
    issues = verify(bedroom_with("le"), text, {"kinds": {}})
    assert {i.code for i in issues} == {"unchecked"} and not blocking(issues)          # direction not judged
    wrong_number = verify(bedroom_with("ge", 12.0), text, {"kinds": {}})
    assert "number_not_in_sentence" in {i.code for i in blocking(wrong_number)}         # numbers still checked


def test_digits_of_other_scripts_and_decimal_commas_are_read():
    arabic = "يجب ألا تقل مساحة غرفة النوم عن ٩ m2"
    assert not blocking([i for i in verify(bedroom_with("ge"), arabic, {"kinds": {}}) if i.code != "unchecked"])
    comma = "Jedes Schlafzimmer muss mindestens 0,90 m breit sein."
    assert codes(bedroom_with("ge", 0.9, "m", "min_width_m"), comma, DE) == set()


def test_an_unknown_unit_word_does_not_cause_a_false_block():
    text = "Jedes Schlafzimmer muss mindestens 90 Zentimeter breit sein."     # unit word the parser does not know
    assert codes(bedroom_with("ge", 0.9, "m", "min_width_m"), text, DE) == set()


def test_language_detection_needs_evidence():
    from reviewpulse.xeval.verify import detect_language

    assert detect_language("Each door shall have a clear width of at least 0.8 m.") == "en"
    assert detect_language("Chaque porte doit avoir une largeur d'au moins 0,8 m.") == "fr"
    assert detect_language("12 34") is None


def test_a_member_fact_read_from_the_wrong_owner_and_an_undeclared_value_are_blocked():
    from reviewpulse.xeval.semantic import hoist

    cat = {"collections": {"ramps": {"facts": ["ramps_length"]}}, "building": ["occupants"],
           "kinds": {"ramps_kind": ["steep"]}, "kind_labels": {}}
    wrong = rule(setop("forall", "ramps", binary("ge", fact("ramps_length"), lit(8.0, "m")),
                       binary("gt", fact("occupants"), lit(50, "count"))))
    assert "fact_wrong_owner" in codes(wrong, "ramps are 8 m long where there are more than 50", cat)
    bad = rule(setop("forall", "ramps", binary("ge", fact("ramps_length"), lit(8.0, "m")),
                     binary("eq", fact("ramps_kind"), lit("gentle"))))
    assert "value_undeclared" in codes(bad, "gentle ramps are at least 8 m", cat)
    tree = {"requirement": {"node": "forall", "collection": "c", "variable": "$x",
                            "where": {"node": "all", "args": [
                                {"node": "gt", "left": {"node": "fact", "entity": "building", "name": "s"},
                                 "right": {"node": "literal", "value": 2}},
                                {"node": "eq", "left": {"node": "fact", "entity": "$x", "name": "k"},
                                 "right": {"node": "literal", "value": "a"}}]},
                            "body": {"node": "literal", "value": True}}}
    out = hoist(tree)
    assert out["applicability"]["node"] == "gt" and out["requirement"]["where"]["node"] == "eq"


def test_a_sum_in_the_sentence_needs_a_sum_in_the_rule():
    per_member = rule(setop("forall", "guards", binary("le", fact("height"), lit(3.0, "m"))))
    assert "aggregate_missing" in codes(per_member, "The sum of the heights of all guardrails shall be at most 300 cm.", {})
    total = rule(binary("le", setop("sum", "guards", fact("height")), lit(3.0, "m")))
    assert "aggregate_missing" not in codes(total, "The sum of the heights of all guardrails shall be at most 300 cm.", {})


def test_a_rule_about_an_unrelated_quantity_is_blocked_by_word_grounding():
    cat = {"collections": {"doors": {"facts": ["doors_width"]}}, "building": [], "kinds": {},
           "bindings": {"doors_width": {"kind": "number", "unit": "m", "description": "door: clear width (m)"}}}
    wrong = rule(setop("forall", "doors", binary("ge", fact("doors_width"), lit(0.27, "m"))))
    assert "not_grounded" in codes(wrong, "The tread must be no less than 270 millimetres.", cat)
    assert "not_grounded" not in codes(wrong, "Every door must have a width of at least 270 millimetres.", cat)


def test_the_older_drafter_does_not_flag_a_number_written_as_a_word():
    from reviewpulse.rules.draft import _spelled_out

    assert _spelled_out(1.0, "Every dwelling has at least one exit door to the outside.")
    assert not _spelled_out(2.0, "Every dwelling has at least one exit door to the outside.")
