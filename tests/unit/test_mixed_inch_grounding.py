import pytest

from reviewpulse.interpreter.quantities import normalise_quantities
from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.verify import check_numbers


@pytest.mark.parametrize("written,value", [("2-1/2", 2.5), ("2 1/2", 2.5),
                                           ("3‑3/8", 3.375), ("4 - 1/4", 4.25)])
def test_construction_mixed_fractions_are_one_quantity(written, value):
    assert normalise_quantities(f'{written}"') == f"{value:g} in"


def test_mixed_fraction_grounding_accepts_whole_quantity_and_rejects_components():
    source = normalise_quantities('Thickness shall be 2-1/2".')
    for value, accepted in ((2.5, True), (2, False), (0.5, False)):
        program = Program.model_validate({
            "id": "quantity", "title": "Thickness", "document": "counterexample",
            "sources": [{"clause": "source", "start": 0, "end": len(source), "quote": source}],
            "requirement": {"node": "eq", "left": {"node": "fact", "entity": "building", "name": "thickness"},
                            "right": {"node": "literal", "value": value, "unit": "in"}},
        })
        assert (not check_numbers(program, source, "en")) is accepted
