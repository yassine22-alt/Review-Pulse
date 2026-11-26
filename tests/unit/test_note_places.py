"""A note keeps the place of the words it was made from, so a reviewer is taken to the right words."""

from types import SimpleNamespace

from reviewpulse.annotate.passages import LONG, sheet_passages
from reviewpulse.interpreter.drawing_evidence import OllamaEmbedder


def line(text, y, x=10.0, width=200.0):
    return SimpleNamespace(text=text, bbox=(x, y, x + width, y + 3), height=3.0, kind="unknown")


def test_a_note_of_two_lines_has_the_box_of_both_and_not_of_its_neighbour():
    texts = [line("1. Provide one smoke detector in each", 100), line("bedroom and in each corridor.", 95.5),
             line("2. Kitchen cabinets are supplied by the owner.", 91)]
    first, second = sheet_passages("S", texts)
    assert first.box == (10.0, 95.5, 210.0, 103.0)
    assert second.box == (10.0, 91.0, 210.0, 94.0)


def test_each_sentence_of_a_long_paragraph_keeps_only_its_own_lines():
    words = ["Guards are required at open sided walking surfaces above grade level.",
             "Handrails shall be placed between the given heights above the stair nosings everywhere.",
             "Every smoke alarm is interconnected with the others and has a battery backup unit.",
             "Exhaust fans discharge directly to the outside air and never into an attic space.",
             "Safety glazing is provided at every door and at the windows beside each stair."]
    assert sum(map(len, words)) > LONG
    texts = [line(t, 200 - 4 * k) for k, t in enumerate(words)]
    got = sheet_passages("S", texts)
    assert len(got) > 1
    assert got[0].box[3] == 203.0 and got[-1].box[1] == 200 - 4 * (len(words) - 1)
    assert got[0].box[1] > got[-1].box[3] - 3.1                    # the first piece does not reach down to the last one


def test_a_schedule_beside_the_notes_neither_cuts_nor_widens_them():
    """From a real sheet: a door schedule stands at the same heights as the door notes."""
    texts = [line("4. DOORS BETWEEN GARAGE AND LIVING", 100, x=10, width=90),
             line("D04 EXT HINGED GLASS PANEL", 99.8, x=140, width=60),
             line("AREA SHALL BE SOLID CORE DOORS WITH A", 95.5, x=14, width=95),
             line("D05 BARN DOOR PANEL ONE", 95.3, x=140, width=60),
             line("RATING OF 60 MINUTES. SELF CLOSING", 91, x=14, width=90),
             line("5. EXTERIOR DOORS SHALL BE WOOD.", 86.5, x=10, width=85)]
    got = sheet_passages("S", texts)
    note = next(p for p in got if p.text.startswith("4."))
    assert note.text == "4. DOORS BETWEEN GARAGE AND LIVING AREA SHALL BE SOLID CORE DOORS WITH A RATING OF 60 MINUTES. SELF CLOSING"
    assert note.box[2] <= 110 and note.box[1] == 91
    assert any(p.text.startswith("5.") for p in got)
    assert not any("GARAGE" in p.text and "D04" in p.text for p in got)


def test_words_split_into_runs_on_one_line_stay_one_line():
    texts = [line("PROVIDE ONE SMOKE", 50, x=10, width=50), line("DETECTOR IN EACH ROOM", 50, x=63, width=60)]
    assert [p.text for p in sheet_passages("S", texts)] == ["PROVIDE ONE SMOKE DETECTOR IN EACH ROOM"]


def test_note_vectors_are_kept_with_a_project_and_only_reused_for_the_same_text_and_model(tmp_path):
    asked = []

    class Stub(OllamaEmbedder):
        def _call(self, path, body=None):
            asked.extend(body["input"])
            return {"embeddings": [[float(len(t)), 1.0] for t in body["input"]]}

    path = tmp_path / "v.npz"
    Stub(model="m1").save(path, ["alpha note", "beta note", "alpha note"])
    assert sorted(asked) == ["alpha note", "beta note"]
    fresh = Stub(model="m1")                                       # after a restart
    assert fresh.load(path, ["alpha note", "gamma note"]) == 1
    asked.clear()
    assert fresh(["alpha note"]) == [[10.0, 1.0]] and asked == []
    assert Stub(model="another").load(path, ["alpha note"]) == 0
    assert Stub(model="m1").load(tmp_path / "missing.npz", ["alpha note"]) == 0
