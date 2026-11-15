"""The round trip refuses a rule only when two answers, in both orders of the options, say it is about something different."""

from reviewpulse.interpreter.roundtrip import compare


class Says:
    def __init__(self, first, second=None):
        self.answers = [first, second or first]

    def complete(self, system, user, schema):
        return {"choice": self.answers.pop(0)}


class Broken:
    def complete(self, system, user, schema):
        raise RuntimeError("down")


def test_two_agreeing_answers_decide():
    assert compare(Says("different"), "Zoning form.", "Every room is labelled.") == "different"
    assert compare(Says("partial"), "Window or exhaust.", "Bathrooms have a window.") == "partial"
    assert compare(Says("same"), "Hallways 3 ft.", "Hallways are 0.91 m wide.") == "same"


def test_disagreeing_answers_cost_no_rule():
    assert compare(Says("different", "same"), "s", "r") == "same"
    assert compare(Says("different", "partial"), "s", "r") == "same"


def test_no_answer_is_not_a_verdict():
    assert compare(Broken(), "s", "r") == "same"
