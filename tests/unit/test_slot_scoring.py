import copy

from reviewpulse.xeval.slot_scoring import partial_json, score_slots, totals


def sample():
    slots = {"subject": "access width", "nodes": [
        {"op": "fact", "entity": "building", "name": "clear_width"},
        {"op": "literal", "value": 0.85, "unit": "m"}, {"op": "ge"}],
        "sources": [{"clause": "s", "quote": "Access width shall be at least 0.85 m."}]}
    annotation = {"conditions": [], "annotated": False, "subject_accept": ["access width"]}
    return slots, {"slots": slots}, annotation


def test_rejected_raw_output_can_receive_partial_slot_credit():
    raw, gold, annotation = sample()
    changed = copy.deepcopy(raw)
    changed["nodes"][2]["op"] = "le"
    scores = score_slots(changed, gold, annotation)
    assert scores["value"]["exact"] and scores["fact"]["exact"]
    assert not scores["operator"]["exact"]
    assert not scores["applicability"]["eligible"]


def test_scoring_normalizes_equivalent_units_and_variable_names():
    raw, gold, annotation = sample()
    changed = copy.deepcopy(raw)
    changed["nodes"][1].update(value=85, unit="cm")
    scores = score_slots(changed, gold, annotation)
    assert scores["value"]["exact"] and scores["unit"]["exact"]


def test_truncated_json_keeps_only_emitted_complete_fields():
    raw = partial_json('{"subject":"access width","nodes":[{"op":"literal","value":0.85,"unit":"m"},{"op":')
    assert raw["subject"] == "access width"
    assert raw["nodes"][0]["value"] == 0.85
    assert "op" not in raw["nodes"][-1]
    _, gold, annotation = sample()
    scores = score_slots(raw, gold, annotation)
    assert scores["subject"]["exact"] and scores["value"]["exact"]
    assert not scores["fact"]["exact"]


def test_unrequested_subject_and_unannotated_scope_do_not_inflate_accuracy():
    raw, gold, annotation = sample()
    values = totals([score_slots(raw, gold, annotation, subject_requested=False)])
    assert values["subject"]["denominator"] == 0
    assert values["applicability"]["accuracy"] is None


def test_categorical_literal_values_are_scored():
    raw, _, annotation = sample()
    raw["nodes"].append({"op": "literal", "value": "category_a"})
    changed = copy.deepcopy(raw)
    changed["nodes"][-1]["value"] = "category_b"
    assert not score_slots(changed, {"slots": raw}, annotation)["value"]["exact"]


def test_subject_alternatives_are_explicit_review_data_not_substring_guesses():
    raw, gold, annotation = sample()
    raw["subject"] = "the clear access width"
    assert not score_slots(raw, gold, annotation)["subject"]["exact"]
    annotation["subject_accept"].append("the clear access width")
    assert score_slots(raw, gold, annotation)["subject"]["exact"]
    raw["subject"] = "width"
    assert not score_slots(raw, gold, annotation)["subject"]["exact"]


def test_reversed_and_negated_comparators_score_equivalently_without_dropping_negation():
    raw = {"subject": "access width", "require": "building.clear_width >= 0.85 m", "sources": []}
    gold = {"slots": raw}
    annotation = {"conditions": [], "annotated": False, "subject_accept": ["access width"]}
    for text in ("0.85 m <= building.clear_width", "not (building.clear_width < 0.85 m)"):
        assert score_slots({**raw, "require": text}, gold, annotation)["operator"]["exact"]
    assert not score_slots({**raw, "require": "not (building.clear_width >= 0.85 m)"}, gold, annotation)["operator"]["exact"]


def test_unicode_unit_aliases_score_equally_but_missing_units_are_not_invented():
    raw, gold, annotation = sample()
    gold = copy.deepcopy(gold)
    raw["nodes"][1].update(value=0.85, unit="m²")
    gold["slots"]["nodes"][1].update(value=0.85, unit="m2")
    assert score_slots(raw, gold, annotation)["unit"]["exact"]
    changed = copy.deepcopy(raw)
    changed["nodes"][1].pop("unit")
    assert not score_slots(changed, gold, annotation)["unit"]["exact"]
