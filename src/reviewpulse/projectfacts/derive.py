"""Conditions about the building computed from facts that are already there, and typed conditions with three answers.

A condition is true, false or unknown. It is unknown whenever the data it needs is not there; nothing is assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..drawingset.model import DrawingSet
from ..factgraph.schema import FactGraph
from ..ledger.candidate import Candidate

PRODUCER = "project_facts.derived"
FAMILY = "plan_model"          # derived from the drawing set model or the fact graph, not from the cover text


@dataclass
class Condition:
    """A condition read from a requirement's own words: a project fact compared with a value."""
    fact: str
    op: str = "=="             # ==, !=, >=, >, <=, <, in
    value: object = True
    entity: str = "building"
    words: str = ""


@dataclass
class Evaluation:
    known: bool
    holds: bool | None
    why: str


def plan_levels(ds: DrawingSet) -> list[tuple[str, int]]:
    """Distinct levels the plan views of a set sit on, bottom to top."""
    seen: dict[str, int] = {}
    for v in ds.views():
        if v.kind == "plan" and v.level is not None and v.level_rank is not None:
            seen.setdefault(v.level, v.level_rank)
    return sorted(seen.items(), key=lambda kv: kv[1])


def storeys_from_plans(ds: DrawingSet) -> Candidate | None:
    """Storeys above ground counted from the levels the plan views sit on. Only a lower bound in principle (a level may have
    no plan in the set), so it is scored low and marked inferred; it never replaces a number the set states."""
    lv = plan_levels(ds)
    above = [n for n, r in lv if 0 <= r < 99]            # a roof plan is not a storey
    if not above:
        return None
    names = ", ".join(above)
    return Candidate(entity="building", fact="number_of_storeys", value=len(above), unit="1", kind="inferred",
                     source=f"drawing set model: plan views on {len(above)} levels above ground ({names})",
                     words=names, producer=PRODUCER, family=FAMILY, score=0.4)


def riser_range(fg: FactGraph) -> tuple[int, int] | None:
    """Fewest and most risers in any stair flight, when the graph holds a trusted tread count. The flight has `steps_min`
    to `steps_max` risers: the finder says it cannot tell whether the last tread line is a nosing or the landing edge."""
    counts = [n.attrs["tread_lines"] for n in fg.nodes if n.kind == "stair" and "tread_lines" in n.attrs]
    counts = [c for c in counts if c.value is not None and c.trusted]
    if not counts:
        return None
    hi = max(int(c.value) for c in counts)
    return hi - 1, hi


def risers_at_least(fg: FactGraph, n: int) -> Evaluation:
    """Is there a stair flight with n or more risers? True when the fewest possible risers already reach n, false when even
    the most possible plus the landing riser fall short, unknown in between or when no trusted flight is in the graph."""
    r = riser_range(fg)
    if r is None:
        return Evaluation(False, None, "no stair flight with a trusted tread count in the fact graph")
    lo, hi = r
    if lo >= n:
        return Evaluation(True, True, f"a flight has at least {lo} risers (tread lines {hi})")
    if hi + 1 < n:
        return Evaluation(True, False, f"the longest flight has at most {hi + 1} risers")
    return Evaluation(False, None, f"the longest flight has {lo} to {hi + 1} risers, the limit {n} falls inside")


def dwelling_above_another(facts: dict[str, object]) -> Evaluation:
    """From stated project facts only: a single storey building, or a single family dwelling, has no dwelling above another.
    A multi family building may or may not stack its dwellings, so that stays unknown."""
    st, use = facts.get("number_of_storeys"), facts.get("building_class")
    if st == 1:
        return Evaluation(True, False, "the building has one storey")
    if use in ("single_family_dwelling",):
        return Evaluation(True, False, "the building is a single family dwelling")
    return Evaluation(False, None, "the set does not say how dwellings are stacked")


_OPS = {"==": lambda a, b: a == b, "!=": lambda a, b: a != b, ">=": lambda a, b: a >= b, ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b, "<": lambda a, b: a < b, "in": lambda a, b: a in b}


def evaluate(cond: Condition, facts: dict[str, object]) -> Evaluation:
    """A condition on project facts: known with a boolean, or unknown with the fact that is missing."""
    if cond.fact not in facts or facts[cond.fact] is None:
        return Evaluation(False, None, f"{cond.fact} is not stated in the set")
    try:
        return Evaluation(True, bool(_OPS[cond.op](facts[cond.fact], cond.value)), f"{cond.fact} is {facts[cond.fact]}")
    except TypeError:
        return Evaluation(False, None, f"{cond.fact} cannot be compared with {cond.value!r}")
