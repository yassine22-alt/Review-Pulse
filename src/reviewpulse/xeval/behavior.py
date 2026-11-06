"""Behavioral equivalence: compare a drafted program with the reference on generated fact worlds.

This is test-suite evaluation in the sense of Zhong et al. 2020 (text-to-SQL), applied to rule programs:
exact structural match wrongly rejects programs that differ in form but behave the same.
"""

from __future__ import annotations

import random
from collections import Counter

from ..interpreter.runtime import run_program
from ..interpreter.schema import Program
from .world import literal_pool, ratio_plans, sample_world

OUTCOMES = ("SATISFIED", "VIOLATED", "NOT_APPLICABLE", "EXEMPT", "UNRESOLVED")


def canonical(program: Program) -> Program:
    """Round numeric literals so that 0.8 and 0.8000000000000002 are the same threshold."""
    data = program.model_dump()

    def fix(node):
        if isinstance(node, dict):
            if node.get("node") == "literal" and isinstance(node.get("value"), float):
                node["value"] = round(node["value"], 9)
            for child in node.values():
                fix(child)
        elif isinstance(node, list):
            for child in node:
                fix(child)

    fix(data)
    return Program.model_validate(data)


def outcome(program: Program, inputs) -> str:
    try:
        return run_program(program, inputs, include_drafts=True)["outcome"]
    except ValueError:
        return "ERROR"


def compare(reference: Program, candidate: Program, cat: dict, n_worlds: int = 300, seed: int = 0) -> dict:
    """Agreement on `n_worlds` random worlds, with the disagreement kinds that matter for a reviewer.

    - missed_violation: reference says VIOLATED, candidate does not (an error would go unreported)
    - false_alarm: candidate says VIOLATED, reference does not (a good plan would be flagged)
    """
    ref, cand = canonical(reference), canonical(candidate)
    pool, strings = literal_pool(ref, cand)
    plans = ratio_plans(ref, cand)
    rng = random.Random(seed)
    kinds: Counter = Counter()
    agree = 0
    first_diff = None
    for _ in range(n_worlds):
        world = sample_world(rng, cat, pool, strings, plans)
        a, b = outcome(ref, world), outcome(cand, world)
        if a == b:
            agree += 1
            continue
        if a == "VIOLATED":
            kinds["missed_violation"] += 1
        elif b == "VIOLATED":
            kinds["false_alarm"] += 1
        elif "UNRESOLVED" in (a, b):
            kinds["resolution_mismatch"] += 1
        else:
            kinds["other"] += 1
        first_diff = first_diff or {"reference": a, "candidate": b}
    return {
        "agreement": agree / n_worlds,
        "equivalent": agree == n_worlds,
        "kinds": dict(kinds),
        "first_diff": first_diff,
    }
