"""The quantity parser used by the demand analysis."""

import pytest

from reviewpulse.xeval.demand import analyse, quantities


@pytest.mark.parametrize("text,expect", [
    ("The door shall be at least 900 mm wide.", [(900, "mm")]),
    ("A clear width of 0.8 m is required.", [(0.8, "m")]),
    ("La largeur doit être d'au moins 0,80 m.", [(0.8, "m")]),
    ("Floor area of not less than 7.5 m2 and 9  square  metres.", [(7.5, "m2"), (9, "m2")]),
    ("between 200 and 300 millimetres from the wall", [(200, "mm"), (300, "mm")]),
    ("no more than 2,400 square metres", [(2400, "m2")]),
    ("at least 30 minutes of fire resistance", [(30, "min")]),
    ("a gradient not steeper than 1:12", [(1 / 12, "ratio")]),
])
def test_quantities(text, expect):
    got = [(round(q.value, 6), q.unit) for q in quantities(text, french="largeur" in text)]
    assert [(round(v, 6), u) for v, u in expect] == got


def test_analysis_counts_and_supply():
    result = analyse(["Each door shall be at least 850 mm wide.", "The room shall be pleasant.",
                      "The floor area shall be at least 9 m2."])
    assert result["with_quantity"] == 2 and result["no_quantity"] == 1
    assert dict(result["by_property"])["width / clear opening"] == 1
    assert result["share_measured"] == 1.0
