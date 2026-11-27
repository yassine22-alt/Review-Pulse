"""The reviewer's statuses (Approved, Approved with comments, Information requested, Revision required, Not applicable,
Deferred submittal) and the overall result as the most severe one. Everything is read from ``reviewer_states.yaml``.

The internal verdict policy is not touched: a finding keeps its verdict and assessment. This module only names them in the
words a plan reviewer uses, and keeps the one rule that matters: an undecided outcome is never a pass.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).with_name("reviewer_states.yaml")


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def statuses() -> dict[str, dict]:
    return config()["statuses"]


def label(status_id: str) -> str:
    return statuses()[status_id]["label"]


def results() -> list[str]:
    """Overall results, least to most severe."""
    return list(config()["results"])


def rank(result: str) -> int:
    return results().index(result)


def status_of_verdict(verdict: str) -> str:
    """Status id for a finding verdict. An unknown verdict is information requested, never approved."""
    return config()["verdicts"].get(verdict, "information_requested")


def status_of_outcome(outcome: str) -> str:
    return config()["outcomes"].get(outcome, "information_requested")


def rollup(status_id: str) -> str:
    """The overall result a single status contributes."""
    return statuses()[status_id]["rollup"]


def most_severe(results_: list[str]) -> str | None:
    return max(results_, key=rank, default=None)


def overall(status_ids: list[str], uncovered: int = 0, reviewed: int = 0) -> dict:
    """The proposed result from item statuses: the most severe of their roll ups, as real systems show it.

    ``uncovered`` counts clauses the review did not decide on this plan; while any remain, the proposal is no better than
    ``uncovered_floor`` (an unread clause is never a pass). ``reviewed`` is the number of decided requirements; with none
    and no statuses there is nothing to propose. The tool never proposes more severe than ``tool_max_result``.
    """
    cfg = config()
    if not status_ids and not reviewed:
        return {"result": None, "label": "Not reviewed", "reason": "no requirement was decided on this plan"}
    result = most_severe([rollup(s) for s in status_ids]) or "Approved"
    reason = "the most severe status of the items"
    if uncovered and rank(result) < rank(cfg["uncovered_floor"]):
        result, reason = cfg["uncovered_floor"], f"{uncovered} clause(s) were not decided on this plan"
    if rank(result) > rank(cfg["tool_max_result"]):
        result = cfg["tool_max_result"]
    return {"result": result, "label": result, "reason": reason}


def check_policy() -> list[str]:
    """Problems with the data file; empty when it keeps the rules stated at its top. Run by the tests."""
    cfg, problems = config(), []
    order = cfg["results"]
    approved = order.index("Approved")
    for verdict, sid in cfg["verdicts"].items():
        if verdict != "PASS" and order.index(statuses()[sid]["rollup"]) <= approved:
            problems.append(f"verdict {verdict} maps to {sid}, which can pass")
    for outcome, sid in cfg["outcomes"].items():
        if outcome not in ("SATISFIED", "NOT_APPLICABLE", "EXEMPT") and order.index(statuses()[sid]["rollup"]) <= approved:
            problems.append(f"outcome {outcome} maps to {sid}, which can pass")
    if cfg["tool_max_result"] == "Rejected":
        problems.append("the tool may not reject")
    for name, d in cfg["reviewer_decisions"].items():
        if d["status"] not in statuses():
            problems.append(f"decision {name} has the unknown status {d['status']}")
        if order.index(statuses()[d["status"]]["rollup"]) <= approved and name == "shown" and d["needs"] != "evidence":
            problems.append("a requirement may only be passed by hand with evidence")
    for result in cfg["signoff_results"] + [cfg["tool_max_result"], cfg["uncovered_floor"]]:
        if result not in order:
            problems.append(f"unknown result {result}")
    return problems
