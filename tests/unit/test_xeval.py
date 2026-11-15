"""The evaluation harness itself: corpus validity, scorer sensitivity, flat IR, progress tracker."""

import json
import re

import pytest

from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval import drafters
from reviewpulse.xeval.behavior import compare
from reviewpulse.xeval.flat import FlatProgram, compile_flat
from reviewpulse.xeval.progress import Tracker
from reviewpulse.xeval.run import mutants
from reviewpulse.xeval.synth import build_corpus, document


def test_corpus_items_are_valid_and_cover_all_families():
    items = build_corpus(120, seed=3)
    assert len({i.family for i in items}) == 10
    assert len({i.params['concept'] for i in items}) >= 6
    for item in items:
        Program.model_validate(item.program)
        assert re.search(r"\d", item.text), item.text
        assert document(item).startswith("Art. 1:")


def test_scorer_accepts_self_and_catches_every_mutant():
    for item in build_corpus(40, seed=5):
        ref = Program.model_validate(item.program)
        assert compare(ref, ref, item.catalogue, 150)["equivalent"]
        for mutant in mutants(item.program):
            assert not compare(ref, Program.model_validate(mutant), item.catalogue, 150)["equivalent"], (item.family, item.text)


def test_scorer_reports_missed_violation_direction():
    item = next(i for i in build_corpus(80, seed=2) if i.family == "threshold" and i.program["requirement"]["body"]["node"] == "ge")
    ref = Program.model_validate(item.program)
    loose = json.loads(json.dumps(item.program))
    loose["requirement"]["body"]["right"]["value"] = 0.0  # accepts every value
    result = compare(ref, Program.model_validate(loose), item.catalogue, 300)
    assert not result["equivalent"] and result["kinds"].get("missed_violation", 0) > 0


def test_held_out_concepts_never_appear_in_dev_items():
    from reviewpulse.xeval.catalogue import CONCEPTS

    held = {c.key for c in CONCEPTS if c.split == "test"}
    dev = build_corpus(150, seed=4, split="dev")
    assert not any(set(i.catalogue["collections"]) & held for i in dev)
    test = build_corpus(40, seed=4, split="test")
    assert all(i.params["concept"] in held for i in test)


def test_catalogue_is_the_only_source_of_names():
    for item in build_corpus(60, seed=9):
        declared = set(item.catalogue["bindings"])
        text = json.dumps(item.program)
        used = set(__import__("re").findall(r'"name": "([a-z_0-9]+)"', text))
        assert used <= declared, (used - declared)


def test_flat_prompt_example_compiles_and_behaves_like_the_reference():
    example = drafters.FLAT_SYSTEM.split('7 m2":' + chr(10), 1)[1]
    flat = FlatProgram.model_validate(json.loads(example))
    program = Program.model_validate(compile_flat(flat, "synth") | {"sources": [
        {"clause": "Art. 1", "start": 0, "end": 1, "quote": "E"}]})
    from reviewpulse.xeval.synth import binary, fact, lit, setop

    reference = Program.model_validate({
        "id": "k", "title": "k", "document": "synth",
        "requirement": setop("forall", "shelters", binary("ge", fact("shelters_area"), lit(7.0, "m2"))),
        "sources": [{"clause": "Art. 1", "start": 0, "end": 1, "quote": "E"}]})
    cat = {"collections": {"shelters": {"facts": ["shelters_area"]}}, "building": [], "kinds": {},
           "bindings": {"shelters_area": {"kind": "number", "unit": "m2", "description": "shelter area"}}}
    assert compare(reference, program, cat, 300)["equivalent"]


def test_flat_compile_rejects_cycles_and_dangling_ids():
    base = {"id": "p", "title": "p", "requirement": "a", "sources": [{"clause": "Art. 1", "quote": "x"}]}
    cyc = FlatProgram.model_validate(base | {"nodes": [{"id": "a", "op": "not", "args": ["a"]}]})
    with pytest.raises(ValueError, match="cycle"):
        compile_flat(cyc, "d")
    dangling = FlatProgram.model_validate(base | {"nodes": [{"id": "a", "op": "not", "args": ["zz"]}]})
    with pytest.raises(ValueError, match="unknown node id"):
        compile_flat(dangling, "d")


def test_fix_spans_computes_offsets_from_quote():
    item = build_corpus(1, seed=1)[0]
    ctx = drafters.context_for(item)
    fixed = drafters.fix_spans([{"quote": item.text[:12]}], ctx)[0]
    assert ctx.text[fixed["start"]:fixed["end"]] == item.text[:12]
    with pytest.raises(ValueError, match="quote not found"):
        drafters.fix_spans([{"quote": "not in the clause"}], ctx)


def test_tracker_persists_and_renders(tmp_path):
    tr = Tracker(tmp_path)
    tr.start("E2", total=4, detail="go")
    tr.step("E2", 2, detail="halfway")
    assert "2/4" in tr.console()
    tr.finish("E2", {"items": 4}, detail="ok")
    again = Tracker(tmp_path)
    assert again.state["tasks"]["E2"]["status"] == "done"
    assert (tmp_path / "PROGRESS.md").read_text(encoding="utf-8").count("E2") >= 2
