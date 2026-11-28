"""Requirements searched ahead of the reviewer: same results as opening them, never from other drawings, never in the way."""

import threading
import time

from reviewpulse.app import interpret, prepare


class Plan:
    """Stands in for the project: what the preparer asks the app about, and what it searched."""

    def __init__(self, monkeypatch, clauses=("a", "b", "c"), fail=()):
        self.stamp, self.clauses, self.fail, self.searched = "drawings 1", list(clauses), set(fail), []
        self.gate = threading.Event()
        self.gate.set()
        monkeypatch.setattr(interpret, "search_stamp", lambda _s, _p: self.stamp)
        monkeypatch.setattr(interpret, "searchable_clauses", lambda _s, _p: self.clauses)
        monkeypatch.setattr(interpret, "find_parts", self.find)

    def find(self, _store, _pid, cid, _llm):
        self.gate.wait(5)
        if cid in self.fail:
            raise RuntimeError("no model")
        self.searched.append((self.stamp, cid))


def until(check, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


def made(monkeypatch, client=None, **kw):
    plan = Plan(monkeypatch, **kw)
    return plan, prepare.Preparer(None, lambda: client)


def test_every_requirement_is_searched_once_and_asking_again_starts_nothing(monkeypatch):
    plan, p = made(monkeypatch)
    p.ensure("x")
    until(lambda: p.status("x")["running"] is False)
    p.ensure("x")
    time.sleep(0.2)
    assert [c for _, c in plan.searched] == ["a", "b", "c"] and p.status("x")["done"] == 3
    p.close()


def test_it_waits_while_a_person_is_waiting(monkeypatch):
    plan, p = made(monkeypatch)
    with p.person_waiting():
        p.ensure("x")
        time.sleep(0.4)
        assert plan.searched == []
    until(lambda: len(plan.searched) == 3)
    p.close()


def test_new_drawings_start_it_over(monkeypatch):
    plan, p = made(monkeypatch)
    plan.gate.clear()
    p.ensure("x")
    time.sleep(0.2)
    plan.stamp = "drawings 2"
    plan.gate.set()
    until(lambda: [c for s, c in plan.searched if s == "drawings 2"][-3:] == ["a", "b", "c"])
    p.close()


def test_it_gives_up_after_failures_in_a_row_and_says_why(monkeypatch):
    plan, p = made(monkeypatch, clauses="abcdef", fail="bcde")
    p.ensure("x")
    until(lambda: p.status("x")["running"] is False)
    assert [c for _, c in plan.searched] == ["a"] and "no model" in p.status("x")["problem"]
    p.close()


def test_a_hosted_reading_model_is_not_asked_ahead(monkeypatch):
    class Hosted:
        external = True

    plan, p = made(monkeypatch, client=Hosted())
    p.ensure("x")
    until(lambda: p.status("x")["running"] is False)
    assert plan.searched == [] and p.status("x")["off"]
    p.close()


def test_switched_off_or_without_drawings_nothing_starts(monkeypatch):
    plan, p = made(monkeypatch)
    plan.stamp = None
    p.ensure("x")
    off = prepare.Preparer(None, lambda: None, enabled=False)
    off.ensure("x")
    time.sleep(0.2)
    assert plan.searched == [] and p.status("x")["total"] == 0 and off.status("x")["running"] is False
    p.close()


def test_it_waits_while_a_job_runs(monkeypatch):
    plan = Plan(monkeypatch)
    running = [True]
    p = prepare.Preparer(None, lambda: None, busy=lambda: running[0])
    p.ensure("x")
    time.sleep(0.4)
    assert plan.searched == []
    running[0] = False
    until(lambda: len(plan.searched) == 3)
    p.close()
