"""One sheet cannot show what a building lacks; only real words are quoted."""

from types import SimpleNamespace

from reviewpulse.engine.setwide import combine, leads_elsewhere
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.interpreter.review import NOT_IN_SOURCE, anchor
from reviewpulse.report import correction_list as cl
from reviewpulse.rules.clauses import split_text
from reviewpulse.rules.registry import REGISTRY
from reviewpulse.rules.schema import Rule
from reviewpulse.schema import Finding


def rule(fn="count_exits", op=">=", value=1, rid="C-1"):
    return Rule.model_validate({
        "id": rid, "title": "The dwelling has at least one exit door", "family": "C", "class": "count",
        "applies_to": {}, "check": {"fn": fn, "op": op, "value": value, "unit": "count"}, "severity": "critical",
        "needs": [], "source": {"doc": "pack.md", "clause": "1"}, "message": "{detected}", "status": "approved",
        "approved_by": "x"})


def found(sheet, detected, verdict, rid="C-1", subjects=()):
    return Finding(rule_id=rid, verdict=verdict, severity="critical", subject_ids=list(subjects), message="m",
                   detected=str(detected), required=">= 1", tier="T3",
                   evidence={"sheet": sheet, "finding_id": f"{rid}:{sheet}"}, source={"doc": "pack.md", "clause": "1"})


def test_a_shortfall_on_one_sheet_of_a_set_is_not_a_violation():
    out = combine([found("s1", 0, "FAIL"), found("s2", 0, "FAIL")], [rule()], 2, set())
    assert [f.verdict for f in out] == ["WARNING"]
    assert out[0].assessment.outcome == "UNRESOLVED"
    assert "not decided for the whole building" in out[0].message and out[0].evidence["sheets_read"] == ["s1", "s2"]


def test_what_one_sheet_shows_holds_for_the_building():
    out = combine([found("s1", 2, "PASS"), found("s2", 0, "FAIL"), found("s3", 0, "FAIL")], [rule()], 3, set())
    assert [(f.verdict, f.evidence["sheet"]) for f in out] == [("PASS", "s1")]
    # counts are not added up: two sheets may draw the same doors
    two = combine([found("s1", 1, "FAIL"), found("s2", 1, "FAIL")], [rule(value=2)], 2, set())
    assert [f.verdict for f in two] == ["WARNING"]


def test_an_exceeded_maximum_and_a_single_sheet_stay_violations():
    over = combine([found("s1", 5, "FAIL"), found("s2", 0, "PASS")], [rule(op="<=", value=3)], 2, set())
    assert [f.verdict for f in over] == ["FAIL", "PASS"]
    alone = combine([found("s1", 0, "FAIL")], [rule()], 1, set())
    assert [f.verdict for f in alone] == ["FAIL"]


def test_a_missing_route_is_undecided_only_where_the_route_can_leave_the_sheet():
    routes = [rule("exists_path", rid="T-1")]
    finding = found("s2", "no route", "FAIL", "T-1", ["r1"])
    out = combine([finding], routes, 2, {"s2"})
    assert out[0].verdict == "WARNING" and "another sheet" in out[0].message and out[0].subject_ids == ["r1"]
    # a sheet with its own exit and no way to another level holds all its routes: the violation stays (two houses in one file)
    assert combine([finding], routes, 2, {"s1"})[0].verdict == "FAIL"
    local = combine([found("s2", 0.7, "FAIL", "D-1", ["d1"])], [rule("width_m", rid="D-1")], 2, {"s2"})
    assert local[0].verdict == "FAIL"
    assert {n for n, f in REGISTRY.items() if f.whole_building} == {
        "count_exits", "exists_path", "shortest_path_m", "disjoint_paths"}


def sheet(exits=True, elements=(), rooms=(), texts=()):
    edges = [SimpleNamespace(a="r1", b="EXIT" if exits else "r2")]
    return SimpleNamespace(edges=edges, elements=[SimpleNamespace(cls=c) for c in elements],
                           rooms=[SimpleNamespace(type=None, label=name) for name in rooms],
                           sheet=SimpleNamespace(texts=[SimpleNamespace(text=t) for t in texts]))


def test_which_sheets_a_route_can_leave():
    assert not leads_elsewhere(sheet(rooms=["SEJOUR", "SUPPLY"], texts=["UPPER CABINETS"]))
    assert leads_elsewhere(sheet(exits=False))
    assert leads_elsewhere(sheet(elements=["stair"]))
    assert leads_elsewhere(sheet(rooms=["STAIRWELL"]))
    assert leads_elsewhere(sheet(texts=["DN"]))


DOC = "# R\n\n6.1 Every door shall have a clear\nwidth of at least 0.80 m.\n"


def context():
    clauses = split_text(DOC)
    return assemble_context("r.md", DOC, clauses, next(c.id for c in clauses if "door" in c.text))


def test_a_quote_is_found_by_its_words_whatever_offsets_the_model_claims():
    ctx = context()
    got = anchor({"message": "units", "source": {"clause": ctx.target, "start": 3, "end": 4,
                                                 "quote": "clear width of AT least 0.80 m"}}, ctx)
    s = got["source"]
    assert ctx.text[s["start"]:s["end"]] == s["quote"] and "0.80 m" in s["quote"] and got["message"] == "units"


def test_an_invented_quote_is_never_shown_and_the_concern_is_kept():
    ctx = context()
    got = anchor({"message": "misses windows", "source": {"clause": ctx.target, "quote": "and every window"}}, ctx)
    assert "every window" not in got["source"]["quote"]
    assert got["message"] == "misses windows" + NOT_IN_SOURCE
    s = got["source"]
    assert ctx.text[s["start"]:s["end"]] == s["quote"]


def test_a_pack_rule_is_never_shown_as_a_quote_of_the_uploaded_document():
    finding = found("s1", 0, "WARNING").model_dump()
    finding["evidence"]["title"] = "The dwelling has at least one exit door"
    document = {"name": "checklist.pdf", "clauses": [{"id": "1", "text": "1 Provide two copies of the site plan."}]}
    sheets = [{"id": "s1", "page": 0, "width": 10, "height": 10, "scale_method": "user", "sheet_type": "", "discipline": ""}]
    item = cl.build({"name": "p", "plan": "p.pdf"}, [finding], document, {}, sheets)["items"][0]
    assert not item["from_document"] and item["citation"] == "[built-in rule C-1]"
    assert "site plan" not in item["quote"] and item["quote"] == "The dwelling has at least one exit door"
    assert item["finding_ids"] == ["C-1:s1"]
