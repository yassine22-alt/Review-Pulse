"""Words documents use for categories: synonyms in any language, and groups the document itself defines."""

from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.expr_ir import compile_expr_program
from reviewpulse.xeval.terms import document_groups, normalise_value
from reviewpulse.xeval.verify import blocking, verify

KINDS = {"kind": ["bath", "sleep", "cook", "day", "store"]}
LABELS = {"kind": {"bath": ["bathroom", "wc", "salle de bain"], "sleep": ["bedroom", "chambre"],
                   "cook": ["kitchen", "cuisine"], "day": ["living room", "séjour"], "store": ["garage"]}}
DOC = ("Art. 2: Every habitable room (bedroom, living room, kitchen) reaches an exit without passing a bathroom.\n"
       "Art. 5: A habitable room with a single door has a window.\n")


def test_a_word_maps_to_the_declared_value_through_its_labels_in_any_language():
    assert normalise_value("WC", "kind", KINDS, LABELS) == "bath"
    assert normalise_value("chambre", "kind", KINDS, LABELS) == "sleep"
    assert normalise_value("living room", "kind", KINDS, LABELS) == "day"
    assert normalise_value("enclosed", "kind", KINDS, LABELS) is None


def test_the_document_defines_a_group_and_the_group_is_named_without_its_determiner():
    assert document_groups(DOC, KINDS, LABELS) == {"kind": {"habitable room": ["cook", "day", "sleep"]}}


def compile_(require, groups=None):
    tree = compile_expr_program({"require": require, "sources": [{"clause": "1", "quote": "x"}]}, "d", {}, set(),
                                kinds=KINDS, labels=LABELS, groups=groups or {})
    tree["sources"] = [{"clause": "1", "start": 0, "end": 1, "quote": "x"}]
    return tree


def test_a_group_name_in_a_rule_becomes_its_values_and_a_synonym_becomes_the_value():
    groups = document_groups(DOC, KINDS, LABELS)
    where = compile_("forall rooms r where r.kind == 'habitable': r.n >= 1", groups)["requirement"]["where"]
    assert where["node"] == "any" and {a["right"]["value"] for a in where["args"]} == {"cook", "day", "sleep"}
    avoid = compile_("forall rooms r: reaches(r, EXIT, avoiding 'WC', 'chambre')")["requirement"]["body"]["node_filter"]
    assert {a["right"]["value"] for a in avoid["args"]} == {"bath", "sleep"}


def test_a_sentence_that_names_a_group_names_its_values_for_the_sentence_check():
    groups = document_groups(DOC, KINDS, LABELS)
    tree = compile_("forall rooms r where r.kind == 'habitable room': r.windows >= 1", groups)
    from reviewpulse.interpreter.schema import Binding

    program = Program.model_validate(tree)
    cat = {"kinds": KINDS, "kind_labels": LABELS, "groups": groups,
           "bindings": {"windows": Binding(kind="number", unit="count").model_dump()}}
    issues = verify(program, "A habitable room with a single door has a window.", cat, "en")
    assert not [i for i in blocking(issues) if i.code in ("scope_invented", "scope_dropped")]
