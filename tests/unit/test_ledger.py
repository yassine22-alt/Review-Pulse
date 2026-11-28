"""The evidence ledger: typed fact requests, producers, fusion, and no change for the rules that run today."""

import pytest

from reviewpulse import pipeline
from reviewpulse.factgraph import to_inputs
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.factgraph.schema import FactGraph
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Binding, Fact, Inputs, Program
from reviewpulse.ledger import (
    Attestations,
    Candidate,
    FactRequest,
    Ledger,
    fact_graph_producers,
    inputs_for_program,
    inputs_from_resolutions,
    ledger_inputs,
    requests_for_program,
)
from reviewpulse.schema import BuildingModel, load
from reviewpulse.synth.make_plan import make_plan
from reviewpulse.synth.random_plan import random_plan
from reviewpulse.synth.scenarios import SCENARIOS
from reviewpulse.xeval.synth import binary, fact, lit, logic, setop

SRC = [{"clause": "Art. 6.1", "start": 0, "end": 1, "quote": "Every door has a clear width of at least 0.80 m"}]


def program(requirement, **extra):
    return Program.model_validate({"id": "p", "title": "p", "document": "d", "requirement": requirement,
                                   "sources": SRC, **extra})


class Listed:
    """A producer that answers from a fixed list: stands in for a dimension reader, a legend reader, a model."""

    def __init__(self, name, family, *candidates):
        self.name, self.family, self.candidates = name, family, list(candidates)

    def holds(self, request):
        return 1.0 if any(c.fact == request.fact for c in self.candidates) else 0.0

    def answer(self, request):
        return [c for c in self.candidates if c.fact == request.fact and request.entity in (None, c.entity)]


def cand(value, source, *, kind="measured", score=0.95, unit="m", entity="d1", fact="width_m", **kw):
    return Candidate(entity=entity, fact=fact, value=value, unit=unit, kind=kind, source=source, score=score, **kw)


WIDTH = FactRequest(entity="d1", entity_kind="door", fact="width_m", unit="m", words="clear width of a door")


# ---- the request ----------------------------------------------------------------------------------------------------

def test_a_request_knows_its_dimension_from_its_unit():
    assert FactRequest(fact="area", unit="m2").dimension == "m2"
    assert FactRequest(fact="w", unit="cm").dimension == "m"
    assert FactRequest(fact="has_window", kind="bool").dimension == ""
    with pytest.raises(ValueError):
        FactRequest(fact="room_type", kind="category", unit="m")


def test_a_candidate_needs_a_source_and_an_attestation_needs_a_name():
    with pytest.raises(ValueError):
        cand(0.9, " ")
    with pytest.raises(ValueError):
        cand(0.9, "reviewer note", kind="attested")
    cand(0.9, "reviewer note", kind="attested", reviewer="K. J.")


# ---- fusion ---------------------------------------------------------------------------------------------------------

def test_one_trusted_producer_is_resolved_and_one_untrusted_is_not():
    assert Ledger([Listed("a", "geometry", cand(0.9, "A-101:d1"))]).resolve(WIDTH).status == "resolved"
    weak = Ledger([Listed("a", "geometry", cand(0.9, "A-101:d1", score=0.5))]).resolve(WIDTH)
    assert weak.status == "unverified" and weak.value == 0.9 and not weak.fact().trusted


def test_agreement_of_independent_families_raises_trust_but_one_family_counts_once():
    weak = dict(score=0.6)
    one_family = Ledger([Listed("a", "text", cand(0.9, "note 1", **weak)), Listed("b", "text", cand(0.9, "note 2", **weak))])
    assert one_family.resolve(WIDTH).status == "unverified"
    two_families = Ledger([Listed("a", "text", cand(0.9, "note 1", **weak)),
                           Listed("b", "schedule", cand(0.9, "schedule row 3", **weak))])
    res = two_families.resolve(WIDTH)
    assert res.status == "resolved" and res.trust == pytest.approx(0.84) and "note 1" in res.source and "schedule row 3" in res.source


def test_planted_value_swap_is_a_conflict_with_both_sources_and_the_rule_is_unresolved():
    ledger = Ledger([Listed("geometry", "geometry", cand(0.9, "A-101:d1")),
                     Listed("schedule", "schedule", cand(0.7, "A-601 row D1", kind="stated"))])
    res = ledger.resolve(WIDTH)
    assert res.status == "conflict" and res.value is None and res.fact().conflicting and not res.fact().trusted
    assert "A-101:d1" in res.source and "A-601 row D1" in res.source          # both sources shown, none chosen
    assert "0.9" in res.explain() and "0.7" in res.explain()
    follow = res.followup()
    assert follow.reason == "conflicting" and follow.entity == "d1"
    rule = program(setop("forall", "doors", binary("ge", fact("width_m"), lit(0.8, "m"))))
    base = Inputs(bindings={"width_m": Binding(kind="number", unit="m")}, collections={
        "doors": {"items": ["d1"], "complete": True, "trusted": True}})
    out = run_program(rule, inputs_from_resolutions([res], base), include_drafts=True)
    assert out["outcome"] == "UNRESOLVED" and any("conflicting" in m for m in out["trace"]["missing"])
    # the same rule with the swap undone is decided, so the conflict (not the rule) caused the refusal
    agreed = Ledger([Listed("geometry", "geometry", cand(0.9, "A-101:d1"))]).resolve(WIDTH)
    assert run_program(rule, inputs_from_resolutions([agreed], base), include_drafts=True)["outcome"] == "SATISFIED"


def test_a_swap_that_would_change_the_verdict_is_never_picked_by_score():
    low_wrong = Listed("model", "model", cand(0.7, "vision model", kind="inferred", score=0.9))
    high_right = Listed("geometry", "geometry", cand(0.9, "A-101:d1", score=0.99))
    for order in ([low_wrong, high_right], [high_right, low_wrong]):
        assert Ledger(order).resolve(WIDTH).status == "conflict"


def test_units_are_converted_into_the_unit_of_the_request():
    cm, ft = cand(90.0, "dimension string", unit="cm", kind="stated"), cand(2.952756, "imperial schedule", unit="ft", kind="stated")
    res = Ledger([Listed("dim", "text", cm), Listed("sch", "schedule", ft)]).resolve(WIDTH)
    assert res.status == "resolved" and res.value == pytest.approx(0.9) and res.request.unit == "m"
    assert res.fact().value == pytest.approx(0.9)


def test_a_candidate_of_another_dimension_or_kind_is_rejected_and_listed_not_converted():
    area = cand(0.72, "wrong row", unit="m2")
    flag = cand(True, "a note", unit="1")
    res = Ledger([Listed("a", "geometry", area, flag, cand(0.9, "A-101:d1"))]).resolve(WIDTH)
    assert res.status == "resolved" and res.value == 0.9 and len(res.rejected) == 2
    assert {why.split(":")[0] for _, why in res.rejected} == {"unit m2 does not measure m", "wrong kind of value"}


def test_nothing_answered_is_unknown_and_unknown_never_passes():
    res = Ledger([Listed("a", "geometry", cand(0.9, "x", entity="other"))]).resolve(WIDTH)
    assert res.status == "unknown" and res.fact() is None and res.followup().reason == "missing"
    rule = program(setop("forall", "doors", binary("ge", fact("width_m"), lit(0.8, "m"))))
    base = Inputs(bindings={"width_m": Binding(kind="number", unit="m")},
                  collections={"doors": {"items": ["d1"], "complete": True, "trusted": True}})
    assert run_program(rule, inputs_from_resolutions([res], base), include_drafts=True)["outcome"] == "UNRESOLVED"


def test_a_producer_that_read_no_value_leaves_an_unknown_fact_with_its_source():
    res = Ledger([Listed("a", "geometry", cand(None, "A-101:d1", score=0))]).resolve(WIDTH)
    assert res.status == "unknown" and res.fact() == Fact(value=None, source="A-101:d1", trusted=False)


# ---- attestation ----------------------------------------------------------------------------------------------------

def test_a_reviewer_attestation_outranks_producers_and_keeps_what_it_overrode():
    book = Attestations()
    book.attest("d1", "width_m", 85.0, unit="cm", reviewer="K. J.", source="site visit 3 Nov")
    ledger = Ledger([Listed("geometry", "geometry", cand(0.7, "A-101:d1")), book])
    res = ledger.resolve(WIDTH)
    assert res.status == "attested" and res.value == pytest.approx(0.85) and res.fact().trusted
    assert "K. J." in res.source and "site visit 3 Nov" in res.source and "0.7 from A-101:d1" in res.source
    assert [c.source for c in res.overridden] == ["A-101:d1"]


def test_two_disagreeing_attestations_are_a_conflict_and_a_nameless_one_cannot_exist():
    book = Attestations()
    book.attest("d1", "width_m", 0.8, unit="m", reviewer="A", source="s1")
    book.attest("d1", "width_m", 0.9, unit="m", reviewer="B", source="s2")
    assert Ledger([book]).resolve(WIDTH).status == "conflict"
    with pytest.raises(ValueError):
        Attestations().attest("d1", "width_m", 0.8, reviewer=" ", source="s")
    with pytest.raises(ValueError):
        Attestations().attest("d1", "width_m", 0.8, reviewer="A", source="")


# ---- by meaning -----------------------------------------------------------------------------------------------------

def tiny_graph() -> FactGraph:
    def f(v, t=True):
        return Fact(value=v, source="A-101:x", trusted=t)

    return FactGraph(
        bindings={"width_m": Binding(kind="number", unit="m", description="Clear width of a door or window opening"),
                  "area_m2": Binding(kind="number", unit="m2", description="Measured net floor area")},
        nodes=[{"id": "d1", "kind": "door", "attrs": {"width_m": f(0.9)}},
               {"id": "r1", "kind": "room", "attrs": {"area_m2": f(12.0)}}],
        inventory={"door": {"complete": True, "trusted": True}, "room": {"complete": True, "trusted": True}})


def test_a_request_with_other_words_finds_the_property_by_meaning_and_stays_below_trust_alone():
    fg = tiny_graph()
    ledger = Ledger(fact_graph_producers(fg))
    res = ledger.resolve(FactRequest(entity="d1", entity_kind="door", fact="door_clear_width", unit="m"))
    assert res.value == 0.9 and res.status == "unverified" and res.accepted[0].fact == "width_m"
    # a dimension that does not fit is not matched, whatever the words say
    assert ledger.resolve(FactRequest(entity="d1", fact="clear_width", unit="m2")).status == "unknown"
    # the same name is a direct answer
    assert ledger.resolve(FactRequest(entity="d1", fact="width_m", unit="m")).status == "resolved"


def test_a_kind_of_entity_request_answers_every_member():
    fg = tiny_graph()
    got = Ledger(fact_graph_producers(fg)).resolve_all(FactRequest(entity_kind="room", fact="area_m2", unit="m2"))
    assert [(r.entity, r.value) for r in got] == [("r1", 12.0)]


def test_requests_are_read_from_a_rule_with_the_words_of_its_clause():
    fg = tiny_graph()
    rule = program(setop("forall", "doors", binary("ge", fact("width_m"), lit(0.8, "m"))))
    [req] = requests_for_program(rule, to_inputs(fg))
    assert (req.entity, req.entity_kind, req.fact, req.unit, req.clause) == (None, "doors", "width_m", "m", "Art. 6.1")
    assert "clear width" in req.words
    inputs, resolutions = inputs_for_program(rule, fg, Ledger(fact_graph_producers(fg)))
    assert inputs.facts == {"d1": {"width_m": Fact(value=0.9, source="A-101:x", trusted=True)}} and len(resolutions) == 1


# ---- no change for the rules that run today -------------------------------------------------------------------------

def rules():
    hab = logic("any", *(binary("eq", fact("room_type"), lit(t)) for t in ("bedroom", "living", "kitchen", "office")))
    return {
        "door width": program(setop("forall", "doors", binary("ge", fact("width_m"), lit(0.8, "m")))),
        "bedroom size": program(setop("forall", "rooms", logic("all", binary("ge", fact("area_m2"), lit(9, "m2")),
                                                               binary("ge", fact("min_width_m"), lit(2.2, "m"))),
                                      where=binary("eq", fact("room_type"), lit("bedroom")))),
        "living area": program(setop("forall", "rooms", binary("ge", fact("area_m2"), lit(14, "m2")),
                                     where=binary("eq", fact("room_type"), lit("living")))),
        "exit distance": program(setop("forall", "rooms", binary("le", fact("exit_distance_m"), lit(15, "m")), where=hab)),
        "windows": program(setop("exists", "rooms", fact("has_window"))),
        "fire doors": program(setop("forall", "doors", binary("ge", fact("fire_rating_min"), lit(20, "min")))),
    }


def check_through_the_ledger(fg: FactGraph, where: str):
    today = to_inputs(fg)
    via, resolutions = ledger_inputs(fg)
    assert via.model_dump() == today.model_dump(), where
    assert all(r.status in ("resolved", "unverified", "unknown") for r in resolutions)      # one family each: no conflicts
    ledger = Ledger(fact_graph_producers(fg))
    outcomes = {}
    for name, rule in rules().items():
        if name == "fire doors" and "fire_rating_min" not in today.bindings:
            continue                  # the plan has no door schedule, so no rule can name that fact
        want = run_program(rule, today, include_drafts=True)
        assert run_program(rule, via, include_drafts=True) == want, f"{where}: {name}"
        demand, _ = inputs_for_program(rule, fg, ledger)
        assert run_program(rule, demand, include_drafts=True) == want, f"{where}: {name} (demand driven)"
        outcomes[name] = want["outcome"]
    return outcomes


FAST = {"01_clean", "02_door_too_narrow", "04_bedroom_through_bathroom", "10_rotated_other_scale"}


def graph_of(tmp_path, kind, kw) -> FactGraph:
    paths = make_plan(tmp_path / "plan", png=False, **kw) if kind == "make" else random_plan(tmp_path / "plan", **kw)
    run_dir = pipeline.inspect(paths["dxf"], tmp_path / "runs")
    pipeline.extract(run_dir)
    pipeline.build(run_dir, images=False)
    models = [load(BuildingModel, p) for p in sorted(run_dir.glob("building_*.json"))]
    return from_building(models[0], complete=True)


@pytest.mark.parametrize("scenario", [pytest.param(s, id=s[0], marks=[] if s[0] in FAST else [pytest.mark.slow])
                                      for s in SCENARIOS])
def test_the_ledger_gives_the_rules_exactly_the_inputs_they_had(tmp_path, scenario):
    name, kind, kw, _ = scenario
    outcomes = check_through_the_ledger(graph_of(tmp_path, kind, kw), name)
    if name == "02_door_too_narrow":
        assert outcomes["door width"] == "VIOLATED"
