import random

import pytest

from reviewpulse.xeval.demand import quantities
from reviewpulse.xeval.verify import _expected_operator
from reviewpulse.xeval.world import sample_world


def test_world_generator_preserves_boolean_and_string_types():
    catalogue = {
        "bindings": {"flag": {"kind": "boolean"}, "note": {"kind": "string"}},
        "collections": {"items": {"facts": ["flag", "note"]}},
        "building": ["flag", "note"], "kinds": {},
    }
    for seed in range(20):
        world = sample_world(random.Random(seed), catalogue, {}, {"red", "blue"})
        for facts in world.facts.values():
            assert type(facts["flag"].value) is bool or facts["flag"].value is None
            assert type(facts["note"].value) is str or facts["note"].value is None


@pytest.mark.parametrize("noun", ["démarrage", "mécanisme", "système", "dégagement"])
def test_unit_symbols_do_not_match_prefixes_of_unicode_words(noun):
    assert quantities(f"1 {noun}", french=True) == []
    assert quantities("1 d", french=True)[0].unit == "d"


@pytest.mark.parametrize("text,expected", [
    ("La pièce doit être à plus de 7 m", "gt"),
    ("La pièce ne doit pas être à plus de 7 m", "le"),
    ("La pièce ne doit pas être à moins de 7 m", "ge"),
    ("La pièce doit être au moins 7 m", "ge"),
])
def test_general_french_comparison_negation(text, expected):
    start = text.index("7")
    assert _expected_operator(text, start, start + 1, "fr") == expected
