"""The normative form (src/reviewpulse/normative): schema, compiler, equivalence, round trip, cue arm, drafter. No model is called."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from reviewpulse.normative import (
    Cond,
    Drafter,
    Exc,
    FactSpec,
    NormTree,
    Obligation,
    Scope,
    TemplateParser,
    all_of,
    compile_tree,
    cue_seeds,
    equivalent,
    leaf,
    not_,
    roundtrip,
    run_tree,
    smt,
    sp,
    to_words,
    vote,
)
from reviewpulse.normative.compile import CompileError

TEXT = "Every bedroom shall have a floor area of at least 9 m2, unless the dwelling is a studio."


def facts():
    return [FactSpec(name="area", kind="number", unit="m2", owner="member", collection="rooms", label={"en": "floor area"}),
            FactSpec(name="kind", kind="string", owner="member", collection="rooms", label={"en": "room type"}),
            FactSpec(name="studio", kind="boolean", label={"en": "the dwelling is a studio"})]


def tree(**over) -> NormTree:
    ob = Obligation(id="o1", scope=Scope(collection="rooms", variable="$r", where=leaf("kind", "eq", "bedroom", span=sp(TEXT, "bedroom"))),
                    requirement=leaf("area", "ge", 9, "m2", sp(TEXT, "at least 9 m2")),
                    exceptions=[Exc(when=leaf("studio", "eq", True, span=sp(TEXT, "the dwelling is a studio")), cue="unless", span=sp(TEXT, "unless the dwelling is a studio"))],
                    span=sp(TEXT, TEXT[:-1]))
    return NormTree(clause_id="c1", text=TEXT, facts=facts(), obligations=[ob.model_copy(update=over)])


def bare(**over) -> NormTree:
    """A building level obligation: 'If a ramp is provided, its width is at least 36 in, unless the site is a small one.'"""
    t = "If a ramp is provided its width must be at least 36 in unless the site is small."
    f = [FactSpec(name="ramp", kind="boolean"), FactSpec(name="width", kind="number", unit="m"), FactSpec(name="small", kind="boolean")]
    ob = Obligation(id="o1", applicability=leaf("ramp", "eq", True, span=sp(t, "If a ramp is provided")), requirement=leaf("width", "ge", 36, "in", sp(t, "at least 36 in")),
                    exceptions=[Exc(when=leaf("small", "eq", True, span=sp(t, "the site is small")), cue="unless", span=sp(t, "unless the site is small"))], span=sp(t, t[:-1]))
    return NormTree(clause_id="c2", text=t, facts=f, obligations=[ob.model_copy(update=over)])


# ----------------------------------------------------------------------------------------------------------------- schema
def test_schema_refuses_bad_shapes():
    with pytest.raises(ValueError):
        Cond(kind="test", fact="a", op="ge")                      # no value
    with pytest.raises(ValueError):
        Cond(kind="not", args=[leaf("a", "eq", True), leaf("b", "eq", True)])
    with pytest.raises(ValueError):
        NormTree(clause_id="c", text="abc", facts=[], obligations=[Obligation(id="o", requirement=leaf("ghost", "eq", True))])   # undeclared fact
    with pytest.raises(ValueError):
        NormTree(clause_id="c", text="abc", facts=[FactSpec(name="a", kind="boolean")],
                 obligations=[Obligation(id="o", requirement=leaf("a", "eq", True, span=sp("abc" * 10, "abcabc")))])             # span outside the clause


def test_spans_quote_the_clause_and_ungrounded_nodes_are_listed():
    t = tree()
    assert t.quote(t.obligations[0].requirement.span) == "at least 9 m2"
    assert t.ungrounded() == []
    loose = tree(requirement=leaf("area", "ge", 9, "m2"))
    assert loose.ungrounded() == ["o1.requirement"]


# --------------------------------------------------------------------------------------------------------------- compiler
def test_building_level_parts_go_to_their_own_slots():
    t = bare()
    prog = compile_tree(t)[0]
    assert prog.applicability.node == "eq" and prog.exemption.node == "eq"
    assert run_tree(t, {"ramp": True, "width": 0.92, "small": False}) == ["SATISFIED"]
    assert run_tree(t, {"ramp": True, "width": 0.80, "small": False}) == ["VIOLATED"]
    assert run_tree(t, {"ramp": True, "width": 0.80, "small": True}) == ["EXEMPT"]
    assert run_tree(t, {"ramp": False, "width": 0.10, "small": False}) == ["NOT_APPLICABLE"]
    assert run_tree(t, {"ramp": True, "width": 0.9144, "small": False}) == ["SATISFIED"]          # 36 in is exactly 0.9144 m


def test_member_level_exception_moves_into_the_scope_filter():
    t = tree()
    assert run_tree(t, {"studio": False}, {"rooms": [{"kind": "bedroom", "area": 10.0}]}) == ["SATISFIED"]
    assert run_tree(t, {"studio": False}, {"rooms": [{"kind": "bedroom", "area": 8.0}]}) == ["VIOLATED"]
    assert run_tree(t, {"studio": True}, {"rooms": [{"kind": "bedroom", "area": 8.0}]}) == ["EXEMPT"]
    assert run_tree(t, {"studio": False}, {"rooms": [{"kind": "kitchen", "area": 3.0}]}) == ["SATISFIED"]      # out of scope: not checked


def test_prohibition_and_exists_and_unit_errors():
    t = bare(modality="prohibition")
    assert run_tree(t, {"ramp": True, "width": 0.80, "small": False}) == ["SATISFIED"]
    with pytest.raises(CompileError):
        compile_tree(bare(requirement=leaf("width", "ge", 36, "kg")))                              # incompatible unit
    ex = tree(scope=Scope(quantifier="exists", collection="rooms", variable="$r", where=leaf("kind", "eq", "bedroom")), exceptions=[])
    assert run_tree(ex, {}, {"rooms": [{"kind": "kitchen", "area": 1.0}, {"kind": "bedroom", "area": 12.0}]}) == ["SATISFIED"]
    assert run_tree(ex, {}, {"rooms": [{"kind": "bedroom", "area": 5.0}]}) == ["VIOLATED"]


def test_unresolved_parts_never_say_satisfied():
    t = bare(unresolved=["a part the drafter could not decide"])
    assert run_tree(t, {"ramp": True, "width": 5.0, "small": False}) == ["UNRESOLVED"]


# ------------------------------------------------------------------------------------------------------------ equivalence
def test_equivalent_trees_with_different_form():
    a = bare()
    b = bare(requirement=not_(leaf("width", "lt", 0.9144, "m")), applicability=all_of(leaf("ramp", "eq", True)))
    r = equivalent(a, b)
    assert r.equivalent and r.exact and r.n_worlds >= 8


@pytest.mark.parametrize("change", [
    {"requirement": leaf("width", "le", 36, "in")},                                 # swapped direction
    {"requirement": leaf("width", "gt", 36, "in")},                                 # a boundary: >= against >
    {"requirement": leaf("width", "ge", 36, "cm")},                                 # wrong unit
    {"exceptions": []},                                                             # dropped exception
    {"applicability": None},                                                        # dropped condition
    {"modality": "prohibition"},
])
def test_planted_perturbations_are_rejected_and_the_node_is_named(change):
    r = equivalent(bare(), bare(**change))
    assert not r.equivalent and r.repair and r.mismatches
    slot = next(iter(change))
    assert any(p.split(":", 1)[1].startswith(slot) for p in r.repair)


def test_scoped_equivalence_and_incompatible_facts():
    assert equivalent(tree(), tree()).equivalent
    assert not equivalent(tree(), tree(requirement=leaf("area", "ge", 9.5, "m2"))).equivalent
    other = tree()
    other.facts[0] = FactSpec(name="area", kind="number", unit="m", owner="member", collection="rooms")
    assert not equivalent(tree(), other).equivalent


def test_smt_is_reported_honestly():
    assert smt()["status"] in ("skipped", "available")


# -------------------------------------------------------------------------------------------------------------- round trip
@pytest.mark.parametrize("lang", ["en", "fr", "de"])
def test_round_trip_in_three_languages(lang):
    for t in (tree(), bare()):
        r = roundtrip(t, lang=lang)
        assert r.ok, r.error
        assert "9 m2" in r.words or "36 in" in r.words


def test_words_are_language_aware():
    assert "Sauf si" in to_words(bare(), "fr") and "Ausser wenn" in to_words(bare(), "de") and "Unless" in to_words(bare(), "en")
    with pytest.raises(ValueError):
        to_words(bare(), "xx")


class DropsExceptions:
    def parse(self, words, facts, language, tree):
        t = TemplateParser().parse(words, facts, language, tree)
        t.obligations[0].exceptions = []
        return t


class Garbage:
    def parse(self, words, facts, language, tree):
        raise ValueError("no idea")


def test_round_trip_mismatch_names_the_node_to_repair():
    r = roundtrip(bare(), DropsExceptions())
    assert not r.ok and any(p.endswith("exceptions") for p in r.repair)
    r = roundtrip(bare(), Garbage())
    assert not r.ok and "could not be read" in r.error


# --------------------------------------------------------------------------------------------------------- cue arm, drafter
def test_cue_arm_finds_exceptions_conditions_and_inline_exception():
    s = cue_seeds("Where toe clearance is required, the depth shall be 17 inches. EXCEPTION: Drive-up depositories are not required.")
    roles = [x.role for x in s]
    assert "condition" in roles and "exception" in roles
    s = cue_seeds("Les portes doivent faire 0,90 m sauf si le local est une cave.")
    assert [x.role for x in s] == ["exception"]
    s = cue_seeds("Wenn die Rampe steiler als 6 % ist, muss ein Handlauf vorhanden sein.")
    assert s and s[0].role == "condition"


class Scripted:
    """A fake client: answers from a script, in the order of the options it is shown."""

    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def complete(self, system, user, schema):
        d = json.loads(user)
        self.calls.append(d)
        return {"choice": self.fn(d["question"], list(d["options"]))}


def test_voting_needs_both_orders_to_agree():
    consistent = Scripted(lambda q, o: "b")
    assert vote(consistent, "q", {"a": "A", "b": "B"}) == "b"
    biased = Scripted(lambda q, o: o[0])                  # always the first option shown: a position bias
    assert vote(biased, "q", {"a": "A", "b": "B"}) is None
    assert vote(Scripted(lambda q, o: "zzz"), "q", {"a": "A"}) is None


def test_drafter_builds_a_grounded_tree_from_scripted_choices():
    text = "If a ramp is provided, its width must be at least 36 in unless the site is small."
    specs = bare().facts

    def answer(q, opts):
        if q.startswith("Which fact does the number"):
            return "width"
        if q.startswith("In which direction"):
            return "ge"
        if q.startswith("Which yes/no fact"):
            return "ramp" if "ramp is provided" in q else "small"
        if q.startswith("Does the clause say"):
            return "holds"
        return "require"

    got = Drafter(Scripted(answer), specs).draft(text, "c2")
    assert got is not None and got.ungrounded() == []
    assert len(got.obligations[0].exceptions) == 1 and got.obligations[0].applicability is not None
    assert equivalent(bare(), got).equivalent


def test_drafter_abstains_instead_of_guessing():
    text = "If a ramp is provided, its width must be at least 36 in unless the site is small."
    got = Drafter(Scripted(lambda q, o: o[0]), bare().facts).draft(text, "c2")           # position biased client
    assert got is None or got.obligations[0].unresolved


# -------------------------------------------------------------------------------------------- the 30 real sentences (hand read)
def _audit():
    path = Path(__file__).resolve().parents[2] / "scripts" / "normative_audit.py"
    spec = importlib.util.spec_from_file_location("normative_audit", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["normative_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_thirty_hand_read_sentences_compile_and_behave_as_read():
    audit = _audit()
    cases = audit.sentences()
    assert len(cases) == 30
    for c in cases:
        t = audit.build(c)
        assert t.ungrounded() == [], c["id"]
        compile_tree(t)
        for world, expect in c["checks"]:
            members = world if any(k in world for k in ("rooms", "doors", "basements")) else None
            assert run_tree(t, None if members else world, members) == expect, c["id"]
        assert roundtrip(t, lang=c["lang"], n_worlds=64).ok, c["id"]


def test_every_single_perturbation_of_a_few_real_sentences_is_rejected():
    audit = _audit()
    cases = {c["id"]: c for c in audit.sentences()}
    for cid in ("ada228.1", "irc_item9", "adb_notes3", "caue16"):
        t = audit.build(cases[cid])
        for m in audit.mutations(t):
            r = equivalent(t, audit.mutate(t, m), n_worlds=64)
            assert not r.equivalent, (cid, m)
