import pytest

from scripts.grade_blind_sample import agreement


def test_empty_grades_are_not_perfect_agreement():
    assert agreement([]) == {"exact": [0, 0], "kappa": None}


def test_nominal_agreement_has_explicit_denominator_and_no_fake_kappa_for_constant_labels():
    assert agreement([("correct", "correct")]) == {"exact": [1, 1], "kappa": None}
    result = agreement([("correct", "correct"), ("wrong", "correct")])
    assert result["exact"] == [1, 2] and result["kappa"] == pytest.approx(0)
