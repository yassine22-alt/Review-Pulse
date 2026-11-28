"""What would settle a requirement: agreement is needed, and nothing is set aside on a split vote."""

from reviewpulse.interpreter.needs import KINDS, NOTHING, UNSURE, decide, orders, what_settles


def test_a_kind_needs_a_majority_and_nothing_needs_every_vote():
    assert decide(["drawn_content", "drawn_content", "site_plan"]) == "drawn_content"
    assert decide(["drawn_content", "site_plan", "written_fact"]) == UNSURE
    assert decide([NOTHING, NOTHING, NOTHING]) == NOTHING
    assert decide([NOTHING, NOTHING, "drawn_content"]) == UNSURE          # a split vote never sets a line aside
    assert decide([NOTHING, NOTHING, None]) == UNSURE                     # nor does an unanswered question
    assert decide(["drawn_content", None, None]) == UNSURE
    assert decide([None, None, None]) == UNSURE


def test_every_question_offers_every_kind_in_a_different_order():
    got = orders(3)
    assert all(sorted(o) == sorted(KINDS) for o in got)
    assert len({tuple(o) for o in got}) == 3 and len({o[0] for o in got}) == 3


class Fixed:
    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def complete(self, system, user, schema):
        self.asked.append(schema["properties"]["choice"]["enum"])
        answer = self.answers[len(self.asked) - 1]
        if isinstance(answer, Exception):
            raise answer
        return {"choice": answer}


def test_a_failed_or_invented_answer_is_not_a_vote():
    client = Fixed("site_plan", RuntimeError("down"), "something_else")
    got = what_settles(client, "Show the setbacks")
    assert got == {"kind": UNSURE, "votes": ["site_plan", None, None]} and len(client.asked) == 3
