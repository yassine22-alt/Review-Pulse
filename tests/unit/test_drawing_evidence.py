"""Evidence in the drawings for a clause: retrieval by words and by meaning, a choice that must not depend on the order of the
options, and figures compared with the unit table."""

import json

from reviewpulse.annotate.passages import Passage, sheet_passages
from reviewpulse.interpreter import drawing_evidence as ev
from reviewpulse.schema import Prov, TextItem

DOOR = Passage("A5", "4. Doors between garage and dwelling shall be solid core doors with a rating of 60 minutes, self closing")
RAIL = Passage("A3", "HANDRAIL 34 - 36 in")
GUARD = Passage("A3", "Guardrails 36 in high at floor surfaces more than 30 in above grade.")
ALARM = Passage("E1", "Provide one smoke detector in each bedroom")
OTHER = Passage("A1", "Kitchen cabinets by owner")
ALL = [DOOR, RAIL, GUARD, ALARM, OTHER]


class Chooser:
    """Chooses the option whose text holds a keyword, whatever the order; `flip` makes it follow the order instead."""

    def __init__(self, keyword, flip=False):
        self.keyword, self.flip, self.calls = keyword, flip, 0

    def complete(self, system, user, schema):
        self.calls += 1
        options = json.loads(user)["options"]
        if self.flip:
            return {"choice": next(iter(options))}
        return {"choice": next((k for k, v in options.items() if self.keyword in v.lower()), "none")}


def _text(i, s, x, y, kind="unknown"):
    return TextItem(id=f"t{i}", text=s, bbox=(x, y, x + 3, y + 0.2), height=0.2, kind=kind, prov=Prov(source="vector", stage="t"))


def test_lines_of_one_note_are_joined_and_numbered_notes_are_separate():
    texts = [_text(1, "GENERAL NOTES", 0, 10), _text(2, "1. PROVIDE A SMOKE ALARM IN EACH", 0, 9.6), _text(3, "BEDROOM AND IN THE HALLWAY.", 0.3, 9.3),
             _text(4, "2. GLAZING NEAR DOORS SHALL BE TEMPERED.", 0, 9.0), _text(5, "3,45", 20, 5, kind="dimension"),
             _text(6, "D1", 22, 5, kind="tag")]
    got = [p.text for p in sheet_passages("S1", texts)]
    assert got == ["GENERAL NOTES", "1. PROVIDE A SMOKE ALARM IN EACH BEDROOM AND IN THE HALLWAY.", "2. GLAZING NEAR DOORS SHALL BE TEMPERED."]


def test_words_in_common_rank_the_right_note_first():
    docs = [p.text for p in ALL]
    assert ev.bm25_ranking("Door to attached garage must be a 20-min. door.", docs)[0] == 0
    assert ev.bm25_ranking("Smoke detectors required in bedrooms", docs)[0] == 3
    assert ev.bm25_ranking("Parking bays are paved", docs) == []


def test_meaning_finds_what_words_cannot_and_the_two_rankings_are_fused():
    def embedder(texts):                      # a stand-in: "coupe-feu" and "rating" share a direction, nothing else does
        return [[1.0, 0.0] if ("coupe-feu" in t or "rating" in t) else [0.0, 1.0] for t in texts]

    clause = "La porte doit être coupe-feu"
    assert ev.retrieve(clause, ALL, None) == []                       # no word in common
    assert ev.retrieve(clause, ALL, embedder)[0] == DOOR
    assert ev.fuse([[2, 0, 1], [0, 2, 1]])[:2] in ([0, 2], [2, 0]) and ev.fuse([[1], [1, 0]])[0] == 1


def test_figures_are_compared_with_units():
    assert [(c.stated, c.result) for c in ev.compare("Door to attached garage must be a 20-min. door.", DOOR.text)] == [("60 min", "agrees")]
    assert [(c.stated, c.result) for c in ev.compare("The door shall have a rating of at least 1.5 hours.", DOOR.text)] == [("60 min", "contradicts")]
    got = ev.compare("Handrails shall be 34 to 38 inches above the nosing.", RAIL.text)
    assert [(c.required, c.result) for c in got] == [(">= 34 in", "agrees"), ("<= 38 in", "agrees")]
    assert [c.result for c in ev.compare("Guards must be at least 36 in high.", ALARM.text)] == ["no figure"]
    assert ev.compare("Show smoke alarms.", ALARM.text) == []


def test_several_figures_of_one_kind_need_the_model_to_say_which():
    clause = "Guards must be at least 42 in high."
    assert [c.result for c in ev.compare(clause, GUARD.text)] == ["unclear"]
    got = ev.compare(clause, GUARD.text, Chooser("36 in, written"))
    assert [(c.stated, c.result) for c in got] == [("36 in", "contradicts")]
    assert [c.result for c in ev.compare(clause, GUARD.text, Chooser("nothing"))] == ["unclear"]      # the model says none


def test_evidence_is_the_note_chosen_in_both_orders_with_its_figure():
    found = ev.find_evidence("Door to attached garage must be a 20-min. door.", ALL, Chooser("60"))
    assert found.chosen == {"sheet": "A5", "text": DOOR.text}
    assert [(c["required"], c["stated"], c["result"], c["basis"]) for c in found.checks] == [
        (">= 20 min", "60 min", "agrees", "the only figure of that kind in the note")] and "only if both are about the same thing" in found.summary
    assert "rating of 60 minutes" in found.checks[0]["words"]


def test_a_choice_that_follows_the_order_of_the_options_is_not_believed():
    found = ev.find_evidence("Doors, handrail and guardrails are shown.", ALL, Chooser("", flip=True))
    assert found.chosen is None and found.candidates and "none was chosen" in found.summary


def test_no_notes_and_no_match_say_so():
    assert "no written notes" in ev.find_evidence("Any clause.", [], Chooser("x")).summary
    assert ev.find_evidence("Parking bays are paved", ALL, Chooser("x")).chosen is None


def test_a_long_block_is_cut_into_its_statements_and_a_short_one_is_left_whole():
    from reviewpulse.annotate.passages import statements

    short = "Provide one smoke detector in each bedroom. Connect to house power."
    assert statements(short) == [short]
    block = " ".join(["Electrical outlets in rooms shall be installed per code and verified with the owner on site."] * 3
                     + ["Provide one smoke detector in each bedroom."] + ["Ventilation fans shall be on timer switches unless noted."] * 3)
    parts = statements(block)
    assert len(parts) >= 2 and all(len(p) <= 420 for p in parts) and " ".join(parts) == block


def test_each_figure_is_shown_with_its_own_words():
    figures = ev.stated_figures('1. STAIRWAYS SHALL HAVE A MIN. WIDTH OF 34". HAND RAILS MAY ENCROACH A MAX. OF 3 1/2" INTO THE REQUIRED WIDTH.')
    assert [(f[0], f[2]) for f in figures] == [(34.0, "in"), (3.5, "in")]
    assert "width of 34 in" in figures[0][4] and "encroach" not in figures[0][4] and "encroach" in figures[1][4]


class _Reader:
    """A stand-in cross-encoder: scores a passage by how many words of the requirement's translation it holds."""

    def __init__(self, keyword):
        self.keyword = keyword

    def scores(self, query, docs):
        return [1.0 if self.keyword in d.lower() else 0.0 for d in docs]


def test_the_cross_encoder_reorders_what_the_two_rankings_kept():
    def embedder(texts):                      # every passage looks alike to the meaning ranking, so the first stage cannot tell them apart
        return [[1.0, 0.0] for _ in texts]

    clause = "La porte du garage doit etre coupe-feu"
    got = ev.retrieve(clause, ALL, embedder, top=3, reranker=_Reader("rating"))
    assert got[0] == DOOR
    assert ev.rerank(clause, [p.text for p in ALL], [1, 2, 0], _Reader("rating")) == [0, 1, 2]
    assert ev.rerank(clause, [], [], _Reader("x")) == []


def test_a_failing_cross_encoder_leaves_the_fusion_as_it_was():
    class Broken:
        def scores(self, query, docs):
            raise RuntimeError("no model")

    assert ev.retrieve("Door rating", ALL, None, top=2, reranker=Broken()) == ev.retrieve("Door rating", ALL, None, top=2)


def test_without_its_files_there_is_no_cross_encoder(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("REVIEWPULSE_RERANKER", raising=False)
    monkeypatch.setattr(ev, "reranker_folder", lambda: None)
    assert ev.default_reranker() is None


def test_a_majority_over_rotations_is_believed_and_a_lean_to_one_position_is_not():
    class Leans:
        """Right two times out of three, wrong once (it leans to the last option shown when the right one is first)."""

        def __init__(self):
            self.n = 0

        def complete(self, system, user, schema):
            self.n += 1
            options = json.loads(user)["options"]
            if self.n == 1:
                return {"choice": list(options)[-1]}
            return {"choice": next(k for k, v in options.items() if "rating" in v.lower())}

    options = {"n0": "Doors with a rating of 60 minutes", "n1": "Kitchen cabinets", "n2": "Smoke detector in each room"}
    assert ev._stable(Leans(), ev.SYSTEM, "requirement", "door rating", options) == "n0"
    assert ev._stable(Chooser("", flip=True), ev.SYSTEM, "requirement", "door rating", options) is None
    assert ev._stable(Chooser("nothing"), ev.SYSTEM, "requirement", "door rating", options) is None


def test_figures_that_fit_are_never_reported_as_meeting_the_requirement_on_their_own():
    """Two figures with the same unit can measure different things: the summary has to ask a person to check."""
    from reviewpulse.annotate.passages import Passage
    from reviewpulse.interpreter.drawing_evidence import find_evidence

    class First:
        def complete(self, system, user, schema):
            return {"choice": "n0"}

    got = find_evidence("Window sills must be at least 24 in above the floor.",
                        [Passage(sheet="A1", text="SAFETY GLAZING WITHIN 24 IN OF ANY DOOR SILL FLOOR WINDOW")], First())
    assert got.checks and got.checks[0]["result"] == "agrees"
    assert "only if both are about the same thing" in got.summary and "which meets" not in got.summary
