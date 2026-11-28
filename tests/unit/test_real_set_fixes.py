"""Defects a real 22 sheet set showed that the one sheet demo plans did not."""

from reviewpulse.app import service
from reviewpulse.app.service import PACKS_ROOT
from reviewpulse.app.store import Store
from reviewpulse.engine.policy import Raw
from reviewpulse.engine.run import not_evaluated, render_message
from reviewpulse.pipeline import load_packs


def test_a_violation_sentence_is_not_shown_without_what_it_names():
    raw = Raw(["r1"], False, vars={"room": {"label": "BEDROOM 2", "__str__": "BEDROOM 2"}},
              detected="reachable", required="path to EXIT")
    msg = render_message("{room.label} is reached only through {witness.blocking}.", raw, raw.detected, raw.required)
    assert "{" not in msg and "only through" not in msg
    assert "BEDROOM 2" in msg and "reachable" in msg


def test_sheet_files_are_in_page_order(tmp_path):
    for k in (0, 1, 2, 10, 11):
        (tmp_path / f"building_{k}.json").write_text("{}")
    assert [f.stem for f in service._sheet_files(tmp_path)] == [f"building_{k}" for k in (0, 1, 2, 10, 11)]


def test_sheet_models_are_loaded_once_and_again_when_a_file_changes(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = store.create("p").id
    run = store.run_dir(pid)
    run.mkdir()
    (run / "building_0.json").write_text("{}")
    loads = []
    monkeypatch.setattr(service, "load", lambda cls, f: loads.append(f.name) or object())
    first = service._models(store, pid)
    assert service._models(store, pid) == first and len(loads) == 1
    (run / "building_0.json").write_text('{"changed": true}')
    assert service._models(store, pid) != first and len(loads) == 2


def test_messages_use_a_reviewers_words_and_keep_the_codes_for_the_program():
    rule = next(r for r in load_packs(PACKS_ROOT / "starter") if r.id == "C-C1")
    finding = not_evaluated(rule, ["room_graph", "scale"], "T3")
    assert "room_graph" not in finding.message and "how the rooms connect" in finding.message
    assert finding.evidence["missing"] == ["room_graph", "scale"]
