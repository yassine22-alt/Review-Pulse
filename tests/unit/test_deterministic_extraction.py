import pytest

from reviewpulse.interpreter.deterministic import extract_quantities


@pytest.mark.parametrize("text,operator", [
    ("La largeur doit être au moins 1,7 m.", "ge"), ("La longueur ne doit pas dépasser 2,3 m.", "le"),
    ("La largeur est inférieur à 3,2 m.", "lt"), ("La largeur est au plus 1,4 m.", "le"),
    ("Minimum 8 m2", "ge"), ("Maximum 6 m2", "le"),
    ("Width ≥ 1.3 m", "ge"), ("Width ≤ 4.7 m", "le"),
    ("Width must be at least 2.6 m", "ge"), ("Width must be no more than 2.7 m", "le"),
])
def test_source_comparators_and_numbers_are_locked(text, operator):
    result = extract_quantities(text)
    assert len(result["evidence"]) == 1
    assert result["evidence"][0]["operator"] == operator


def test_table_cell_inherits_only_its_own_explicit_header_unit():
    result = extract_quantities("| Z8 | ≤ 0,72 |", "| Zone | Coefficient (W/m2/K) |")
    assert [(row["value"], row["unit"], row["operator"]) for row in result["evidence"]] == [(0.72, "W/m2/K", "le")]


def test_ranges_preserve_two_bounds_and_bare_values_do_not_gain_units():
    result = extract_quantities("Band 18 – 28 %; limit ≤ 0.9")
    assert [(r["value"], r["operator"]) for r in result["evidence"][:2]] == [(18, "ge"), (28, "le")]
    assert result["evidence"][-1]["unit"] is None


def test_reference_numbers_do_not_become_measurements():
    result = extract_quantities("See article 3.2. Width shall be ≥ 1.7 m.")
    assert [r["value"] for r in result["evidence"]] == [1.7]
