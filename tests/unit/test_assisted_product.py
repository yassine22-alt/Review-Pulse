import pytest

from reviewpulse.interpreter.assisted import (
    assisted_draft,
    classify_scope,
    compile_assisted,
    numeric_frame,
    ratio_quantity,
)
from reviewpulse.interpreter.context import ContextBundle
from reviewpulse.rules.clauses import Clause


def context(text):
    return ContextBundle(document="test", text=text, target="q", clauses=[
        Clause(id="q", heading="", page=0, text=text, start=0, end=len(text))])


def catalogue():
    return {"whole": "building", "subject_aliases": ["building", "bâtiment"], "building": ["height"],
        "bindings": {"height": {"kind": "number", "unit": "m", "description": "Height hauteur"}},
        "collections": {}, "metadata_vocabulary": {}}


@pytest.mark.parametrize("text,operator", [
    ("The building height must be at least 4.6 m.", "ge"),
    ("The building height must be maximum 4.6 m.", "le"),
    ("La hauteur du bâtiment doit être au plus 4,6 m.", "le"),
    ("La hauteur du bâtiment doit être au moins 4,6 m.", "ge"),
    ("La hauteur du bâtiment est minimum 4,6 m.", "ge"),
    ("La hauteur du bâtiment ne doit pas dépasser 4,6 m.", "le"),
    ("La hauteur du bâtiment doit être inférieur à 4,6 m.", "lt"),
    ("The building height shall be ≥ 4.6 m.", "ge"),
    ("The building height shall be ≤ 4.6 m.", "le")])
def test_source_operator_value_unit_and_roundtrip(text, operator):
    ctx = context(text)
    scope = classify_scope(ctx, catalogue())
    assert scope["in_scope"]
    assert scope["frame"]["measurements"][0]["operator"] == operator
    program, _ = compile_assisted(scope, {"choices": [{"measurement": "m0", "fact": "height"}]}, ctx, catalogue())
    assert program.requirement.node == operator
    assert program.requirement.right.value == 4.6
    for step in scope["frame"]["trace"]:
        span = step["source"]
        assert ctx.text[span["start"]:span["end"]] == span["quote"]


@pytest.mark.parametrize("text", [
    "If the building is new, height must be at least 4 m.",
    "The building height must be at least 4 m except extensions.",
    "The building height must be at least 4 m in residential buildings.",
    "Every connector must link two spaces within 4 m.",
    "The building height must be between 4 m and 6 m.",
    "The building height must be at least 4.",
    "The building must be suitable."])
def test_unsupported_clauses_never_call_a_model(text):
    class Forbidden:
        def complete(self, *args):
            pytest.fail("out-of-scope source must not be drafted")
    out = assisted_draft(context(text), catalogue(), Forbidden())
    assert out["program"] is None
    assert out["queue"] == "reviewer_formalization"


def test_ratios_are_extracted_without_inventing_a_comparator_or_denominator():
    assert ratio_quantity("un objet sur vingt")["value"] == .05
    assert ratio_quantity("at least two items per ten")["value"] == .2
    assert ratio_quantity("un objet par entrée") is None
    assert numeric_frame(context("un sur vingt"))["blockers"]
    frame = numeric_frame(context("au moins un sur vingt"))
    assert frame["measurements"][0]["operator"] == "ge"
    assert frame["measurements"][0]["unit"] == "1"


def test_wrong_unit_and_unknown_subject_cannot_be_approvable():
    ctx = context("The building height must be at least 4 kg.")
    with pytest.raises(ValueError):
        compile_assisted(classify_scope(ctx, catalogue()), {"choices": [{"measurement": "m0", "fact": "height"}]}, ctx, catalogue())
    ctx = context("The object height must be at least 4 m.")
    with pytest.raises(ValueError, match="subject"):
        compile_assisted(classify_scope(ctx, catalogue()), {"choices": [{"measurement": "m0", "fact": "height"}]}, ctx, catalogue())
