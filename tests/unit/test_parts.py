"""A requirement is cut only into its own words; whatever else a model says leaves the line whole."""

import pytest

from reviewpulse.interpreter.parts import span_of, split_requirement, verified, whole

LINE = "Show tread and riser dimensions, handrail height (34 to 38 in), and baluster spacing."


class Says:
    def __init__(self, answer):
        self.answer, self.asked = answer, 0

    def complete(self, *_a):
        self.asked += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_copied_parts_are_kept_in_the_line_order_with_what_was_left_out():
    got = verified(LINE, ["baluster spacing", "Tread and riser dimensions", "handrail height (34 to 38 in)"])
    assert got.by_model
    assert got.parts == ("tread and riser dimensions", "handrail height (34 to 38 in", "baluster spacing")
    assert "Show" in got.left_out


@pytest.mark.parametrize("answer", [
    {"parts": ["stair width", "guard height"]},                   # words the line does not have: both dropped
    {"parts": ["handrail height", "guard height"]},               # one real part is not a split
    {"parts": ["rail", "spacing"]},                               # "rail" is inside "handrail": parts are whole words
    {"parts": "handrail height"}, {"other": 1}, ValueError("no answer"),
])
def test_anything_else_leaves_the_line_whole(answer):
    # an answer that is not a split is still an answer; a model that failed is asked again another time
    assert split_requirement(Says(answer), LINE) == whole(LINE, answered=not isinstance(answer, Exception))


def test_a_part_inside_another_part_is_not_listed_twice():
    got = verified(LINE, ["handrail height", "height", "baluster spacing"])
    assert got.parts == ("handrail height", "baluster spacing")


def test_case_accents_and_punctuation_do_not_hide_a_copied_part():
    line = "Indiquer la hauteur des garde-corps et l'écartement des barreaux."
    assert span_of("hauteur des garde corps", line) is not None
    assert span_of("ecartement des barreaux", line) is not None
    assert span_of("largeur", line) is None


def test_without_a_model_the_line_is_one_part():
    assert split_requirement(None, LINE) == whole(LINE, answered=False)
