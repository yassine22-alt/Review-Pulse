"""M22: the new packages in the real review path, each behind a switch, and what each switch does."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from reviewpulse.factgraph import to_graph, to_inputs
from reviewpulse.factgraph.schema import FactGraph
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.interpreter.findings import to_findings
from reviewpulse.interpreter.schema import Binding, Fact, Program
from reviewpulse.ledger import FactRequest, Ledger, ledger_inputs
from reviewpulse.ledger.sheet_tables import SheetTableProducer
from reviewpulse.ledger.wiring import attest, build_inputs, load_attestations, reviewer_question
from reviewpulse.regs import synthetic as S
from reviewpulse.regs.context import with_resolved_context
from reviewpulse.rules.clauses import split_text
from reviewpulse.schedules.legacy import merge_door_fire
from reviewpulse.schedules.model import Candidate as TableCandidate
from reviewpulse.schedules.reader import is_unstated
from reviewpulse.xeval.synth import binary, fact, lit, setop

SRC = [{"clause": "Art. 6.1", "start": 0, "end": 1, "quote": "Every door has a fire rating of at least 20 minutes"}]
ROOT = Path(__file__).resolve().parents[2]


def fire_rule() -> Program:
    return Program.model_validate({"id": "p", "title": "Fire doors", "document": "d", "sources": SRC,
                                   "requirement": setop("forall", "doors", binary("ge", fact("fire_rating_min"), lit(20, "min")))})


def door_graph(rating=20.0) -> FactGraph:
    return FactGraph(
        bindings={"fire_rating_min": Binding(kind="number", unit="min", description="Fire resistance rating of the door")},
        nodes=[{"id": "d1", "kind": "door", "attrs": {"fire_rating_min": Fact(value=rating, source="A-601 row D1", trusted=True)}}],
        inventory={"door": {"complete": True, "trusted": True}})


def table_cand(value, element="d1", **kw):
    base = dict(value=value, unit="min", meaning="fire_rating", entity_kind="doors", entity_tag="D1", sheet="A-601",
                table="A-601:T1", row=0, cell_text="1 HR", header_text="Fire Label", element_id=element)
    return TableCandidate(**{**base, **kw})


# ---- (1) ledger ---------------------------------------------------------------------------------------------------------

def test_ledger_switch_off_is_the_plain_conversion(monkeypatch):
    fg = door_graph()
    monkeypatch.setenv("REVIEWPULSE_LEDGER", "off")
    inputs, resolutions = build_inputs(fg)
    assert resolutions == [] and inputs.model_dump() == to_inputs(fg).model_dump()
    monkeypatch.setenv("REVIEWPULSE_LEDGER", "on")
    inputs, resolutions = build_inputs(fg)
    assert resolutions and inputs.model_dump() == to_inputs(fg).model_dump()


def test_a_conflict_names_both_sources_and_asks_the_reviewer():
    fg = door_graph(20.0)
    table = SheetTableProducer([table_cand(0.0, cell_text="NR")])
    inputs, resolutions = ledger_inputs(fg, extra=[table])
    assert inputs.facts["d1"]["fire_rating_min"].conflicting
    findings, _ = to_findings(fire_rule(), inputs, to_graph(fg), resolutions=resolutions)
    [f] = findings
    assert f.verdict == "NOT_EVALUATED"
    assert "A-601 row D1" in f.message and "cell 'NR'" in f.message           # both sources
    assert "Reviewer question" in f.message and "fire_rating_min" in f.message
    assert f.evidence["unsettled"][0]["status"] == "conflict"
    # the same finding without the ledger's resolutions is worded as before
    plain, _ = to_findings(fire_rule(), inputs, to_graph(fg))
    assert "Reviewer question" not in plain[0].message and plain[0].verdict == "NOT_EVALUATED"


def test_agreeing_table_raises_trust_and_the_rule_is_decided():
    fg = door_graph(60.0)
    inputs, resolutions = ledger_inputs(fg, extra=[SheetTableProducer([table_cand(60.0)])])
    [res] = resolutions
    assert res.status == "resolved" and res.trust > 0.95 and "A-601 row D1" in res.source and "cell '1 HR'" in res.source
    [f], _ = to_findings(fire_rule(), inputs, to_graph(fg), resolutions=resolutions)
    assert f.verdict == "PASS"


def test_a_table_cell_not_bound_to_an_element_is_not_offered():
    req = FactRequest(entity="d1", fact="fire_rating_min", unit="min")
    assert SheetTableProducer([table_cand(60.0, element=None)]).holds(req) == 0


def test_reviewer_question_is_the_followup():
    res = Ledger([SheetTableProducer([table_cand(60.0, confidence=0.5)])]).resolve(
        FactRequest(entity="d1", fact="fire_rating_min", unit="min"))
    assert res.status == "unverified" and "fire_rating_min of d1 in min" in reviewer_question(res)


def test_attestations_persist_and_outrank(tmp_path):
    attest(tmp_path, "d1", "fire_rating_min", 90.0, reviewer="K. J.", source="door label seen on site", unit="min")
    book = load_attestations(tmp_path)                       # a reload restores it
    inputs, _ = ledger_inputs(door_graph(20.0), book)
    got = inputs.facts["d1"]["fire_rating_min"]
    assert got.value == 90.0 and got.trusted and "K. J." in got.source and "20" in got.source
    with pytest.raises(ValueError):
        attest(tmp_path, "d1", "fire_rating_min", 10.0, reviewer=" ", source="x", unit="min")
    assert len(load_attestations(tmp_path).entries) == 1
    (tmp_path / "attestations.json").write_text("not json", encoding="utf-8")
    assert load_attestations(tmp_path).entries == []         # a damaged file attests nothing


# ---- (2) sheet tables ---------------------------------------------------------------------------------------------------

def test_a_dash_is_unstated_and_nr_is_not():
    assert is_unstated("-") and is_unstated(" -- ") and is_unstated("TBD")
    assert not is_unstated("NR") and not is_unstated("0") and not is_unstated("1 HR")


def test_merge_fills_missing_ratings_and_keeps_row_counts(monkeypatch):
    monkeypatch.setattr("reviewpulse.schedules.legacy.general_door_fire", lambda sheet: {"D1": 60.0, "D2": 20.0, "D3": 45.0})
    schedules = [{"name": "doors", "rows": [{"tag": "D1"}, {"tag": "D2", "fire_rating_min": 20.0}]}]
    assert merge_door_fire(None, schedules) == 2
    assert [r.get("fire_rating_min") for r in schedules[0]["rows"]] == [60.0, 20.0]
    assert schedules[1] == {"name": "fire_ratings", "rows": [], "fire_rows": {"D3": 45.0}}      # no new row for row counters


def test_sheet_tables_switch_off_keeps_the_old_reader_alone(monkeypatch):
    monkeypatch.setattr("reviewpulse.schedules.legacy.general_door_fire", lambda sheet: {"D1": 60.0})
    monkeypatch.setenv("REVIEWPULSE_SHEET_TABLES", "off")
    schedules = [{"name": "doors", "rows": [{"tag": "D1"}]}]
    assert merge_door_fire(None, schedules) == 0 and schedules == [{"name": "doors", "rows": [{"tag": "D1"}]}]


def test_fire_rows_reach_the_fact_graph_rows():
    from reviewpulse.factgraph.from_building import schedule_rows

    class M:
        schedules = [{"name": "doors", "rows": [{"tag": "D1", "height_m": 2.1}]},
                     {"name": "fire_ratings", "rows": [], "fire_rows": {"D1": 60.0, "D9": 30.0}}]

    rows = schedule_rows(M())
    assert rows["D1"]["fire_rating_min"] == 60.0 and rows["D1"]["height_m"] == 2.1 and rows["D9"]["fire_rating_min"] == 30.0


# ---- (3) regulation graph -----------------------------------------------------------------------------------------------

def _span(clause, start, end, quote):
    return type("Sp", (), {"clause": clause.id, "start": start, "end": end, "quote": quote})()


def test_reggraph_adds_cited_clauses_and_never_a_quote_from_outside(monkeypatch):
    text = S.render(S.build(5, 5, seed=1), "fr")
    clauses = split_text(text)
    base = assemble_context("d", text, clauses, "2.1")
    more = with_resolved_context(base, clauses)
    added = {c.id for c in more.clauses} - {c.id for c in base.clauses}
    assert added and more.target == base.target
    cited = next(c for c in more.clauses if c.id in added)
    more.check_span(_span(cited, cited.start, cited.start + 5, cited.text[:5]))
    outside = next(c for c in clauses if c.id not in {x.id for x in more.clauses})
    with pytest.raises(ValueError):
        more.check_span(_span(outside, outside.start, outside.start + 5, outside.text[:5]))
    with pytest.raises(ValueError):                      # a quote that is not at its offsets is refused as before
        more.check_span(_span(cited, cited.start, cited.start + 5, "zzzzz"))
    monkeypatch.setenv("REVIEWPULSE_REGGRAPH", "off")
    assert with_resolved_context(base, clauses) is base


# ---- (4) drawing set summary and package data ---------------------------------------------------------------------------

def test_drawing_set_summary_is_off_by_default_and_counts(monkeypatch):
    from reviewpulse.drawingset import DrawingSet
    from reviewpulse.drawingset import Sheet as DSheet
    from reviewpulse.drawingset.model import Callout, IndexEntry
    from reviewpulse.drawingset.summary import enabled, html_block, summarise

    monkeypatch.delenv("REVIEWPULSE_DRAWINGSET", raising=False)
    assert not enabled()
    monkeypatch.setenv("REVIEWPULSE_DRAWINGSET", "on")
    assert enabled()
    ds = DrawingSet("set", "xycut", [DSheet(0, "A-101", "title block", "Plan", 100, 100)],
                    [Callout(0, "3/A-501", "g", "3", "A-501", None, (0, 0, 1, 1), status="view"),
                     Callout(0, "9/A-999", "g", "9", "A-999", None, (0, 0, 1, 1), status="unresolved_sheet")], [],
                    [IndexEntry("A-101", "Plan", 0, status="match"), IndexEntry("A-777", "Roof", 0, status="not in set")])
    out = summarise(ds)
    assert out["callouts"]["resolved"] == 1 and out["callouts"]["total"] == 2
    assert [m["number"] for m in out["index"]["mismatches"]] == ["A-777"]
    assert "information only" in html_block(out)


def test_word_lists_are_package_data():
    listed = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["package-data"]["reviewpulse"]
    for rel in ("drawingset/vocab.yaml", "regs/cues.yaml", "schedules/vocabulary.yaml"):
        assert rel in listed, rel
        assert (ROOT / "src" / "reviewpulse" / rel).is_file(), rel
