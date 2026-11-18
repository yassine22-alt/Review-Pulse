import pytest

from reviewpulse.xeval.verify import number_words


@pytest.mark.parametrize("phrase,value", [("vingt", 20), ("trente-sept", 37),
                                           ("quatre-vingt-onze", 91), ("vingt‑et‑un", 21)])
def test_complete_number_phrases_are_read_without_their_components(phrase, value):
    assert number_words(phrase, "fr") == [value]


@pytest.mark.parametrize("phrase", ["cent vingt", "mille vingt", "quatre-vingt-dix-neuf cent"])
def test_unknown_larger_compounds_cannot_license_a_partial_threshold(phrase):
    assert number_words(phrase, "fr") == []


def test_independent_numbers_are_kept_but_percent_unit_is_not_a_hundred():
    assert number_words("une unité sur trente", "fr") == [1, 30]
    assert number_words("cinq pour cent", "fr") == [5]


@pytest.mark.parametrize("source,threshold,accepted", [
    ("vingt", 20, True), ("vingt-et-un", 20, False),
    ("cent vingt", 20, False), ("trente-sept", 37, True),
])
def test_numeric_grounding_uses_the_whole_phrase(source, threshold, accepted):
    from reviewpulse.interpreter.schema import Program
    from reviewpulse.xeval.verify import check_numbers

    program = Program.model_validate({
        "id": "grounding", "title": "Numeric grounding", "document": "counterexamples",
        "sources": [{"clause": "value", "start": 0, "end": len(source), "quote": source}],
        "requirement": {"node": "ge", "left": {"node": "fact", "entity": "building", "name": "quantity"},
                        "right": {"node": "literal", "value": threshold}},
    })
    rejected = any(issue.code == "number_not_in_sentence" for issue in check_numbers(program, source, "fr"))
    assert rejected is not accepted
