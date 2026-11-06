"""Random fact worlds for any catalogue.

A catalogue says which collections exist, which measured facts each member has, and which building-level
facts exist. A world is an `Inputs` object filled with random members and values, aimed at the thresholds
that appear in the two programs being compared. Two programs are behaviorally equivalent when they give
the same outcome in every world: no label and no assumption about what the facts mean.
"""

from __future__ import annotations

import random
from fractions import Fraction

from ..interpreter.schema import (
    BinaryExpr,
    Binding,
    Collection,
    Expr,
    Fact,
    FactExpr,
    Inputs,
    LiteralExpr,
    Program,
    SetExpr,
    walk,
)

BUILDING = "building"


def bindings_of(cat: dict) -> dict[str, Binding]:
    return {name: Binding.model_validate(b) for name, b in cat["bindings"].items()}


def program_expressions(program: Program) -> list[Expr]:
    return [program.applicability, program.exemption, program.requirement]


def literal_pool(*programs: Program) -> tuple[dict[str, set[float]], set[str]]:
    """Numeric literals by unit and string literals used by the programs (boundary values to probe)."""
    numbers: dict[str, set[float]] = {}
    strings: set[str] = set()
    for program in programs:
        for expr in program_expressions(program):
            for node in walk(expr):
                if isinstance(node, LiteralExpr):
                    if isinstance(node.value, str):
                        strings.add(node.value)
                    elif not isinstance(node.value, bool):
                        numbers.setdefault(node.unit, set()).add(float(node.value))
    return numbers, strings


def ratio_plans(*programs: Program) -> list[dict]:
    """Share-of-total comparisons: sum(value where kind == v) / sum(value), with the thresholds in the program."""
    plans = []
    for program in programs:
        targets = [t for t in literal_pool(program)[0].get("1", set()) if 0 < t < 1]
        for expr in program_expressions(program):
            for node in walk(expr):
                if not (isinstance(node, BinaryExpr) and node.node == "div"):
                    continue
                num, den = node.left, node.right
                if not (isinstance(num, SetExpr) and isinstance(den, SetExpr) and num.node == den.node == "sum"):
                    continue
                where = num.where
                if (isinstance(where, BinaryExpr) and where.node == "eq" and isinstance(where.left, FactExpr)
                        and isinstance(where.right, LiteralExpr) and isinstance(num.body, FactExpr)):
                    for target in targets:
                        plans.append({"collection": num.collection, "value_fact": num.body.name,
                                      "kind_fact": where.left.name, "kind_value": where.right.value,
                                      "target": target})
    return plans


DEFAULT_TOP = {"m": 2.5, "m2": 20.0, "1": 0.2}


def _number(rng: random.Random, unit: str, pool: dict[str, set[float]]) -> float:
    aligned = sorted(pool.get(unit, set()))
    if unit == "count":
        base = [int(v) for v in aligned]
        if base and rng.random() < 0.6:
            return float(max(0, rng.choice(base) + rng.choice([-1, 0, 0, 1])))
        return float(rng.randint(0, max(base + [3]) + 2))
    step = 0.01
    if aligned and rng.random() < 0.55:
        return round(max(0.0, rng.choice(aligned) + rng.choice([-step, 0.0, 0.0, step])), 4)
    top = max(aligned) * 1.6 if aligned else DEFAULT_TOP.get(unit, 2.0)
    grid = {"m": 0.05, "1": 0.01}.get(unit, 0.5)
    return round(rng.randint(0, max(int(top / grid), 1)) * grid, 4)


def _ratio_rows(rng: random.Random, target: float, kind: str, others: list[str]) -> list[tuple[str, float]]:
    """Members whose values make (sum of `kind`) / (sum of all) equal, just below or just above `target`.

    Integer values keep the quotient exactly representable, so a >= versus > mistake is also exposed."""
    frac = Fraction(target).limit_denominator(1000)
    scale = rng.randint(1, 3)
    mine, rest = frac.numerator * scale, (frac.denominator - frac.numerator) * scale
    mine += rng.choice([-1, 0, 0, 1])
    rows = [(kind, float(max(mine, 0)))]
    if rest > 0:
        first = rng.randint(0, rest)
        rows += [(rng.choice(others), float(first)), (rng.choice(others), float(rest - first))]
    return rows


def sample_world(rng: random.Random, cat: dict, pool: dict[str, set[float]], strings: set[str],
                 plans: list[dict] | None = None, p_unknown: float = 0.08) -> Inputs:
    bindings = bindings_of(cat)
    kinds = cat.get("kinds", {})
    plan = None
    if plans and rng.random() < 0.4:
        plan = rng.choice(plans)
        if plan["collection"] not in cat["collections"]:
            plan = None

    def fact(value, forced=False) -> Fact:
        if not forced and rng.random() < p_unknown:
            return Fact(value=None if rng.random() < 0.5 else value, source="world", trusted=False)
        return Fact(value=value, source="world", trusted=True)

    facts: dict[str, dict[str, Fact]] = {}
    collections: dict[str, Collection] = {}
    complete = rng.random() > 0.05
    for coll, spec in cat["collections"].items():
        rows = None
        if plan and plan["collection"] == coll:
            others = [v for v in kinds.get(plan["kind_fact"], []) if v != plan["kind_value"]]
            if others:
                rows = _ratio_rows(rng, plan["target"], plan["kind_value"], others)
        count = len(rows) if rows else rng.randint(0, 6)
        ids = [f"{coll}_{i}" for i in range(count)]
        for i, eid in enumerate(ids):
            member = {}
            for name in spec["facts"]:
                binding = bindings[name]
                forced = bool(rows) and name in (plan["kind_fact"], plan["value_fact"])
                if binding.kind == "string":
                    values = kinds[name]
                    used = [v for v in values if v in strings]
                    value = rng.choice(used) if used and rng.random() < 0.7 else rng.choice(values)
                    if rows and name == plan["kind_fact"]:
                        value = rows[i][0]
                else:
                    value = _number(rng, binding.unit, pool)
                    if rows and name == plan["value_fact"]:
                        value = rows[i][1]
                member[name] = fact(value, forced)
            facts[eid] = member
        collections[coll] = Collection(items=ids, complete=complete, trusted=True)
    facts[BUILDING] = {name: fact(_number(rng, bindings[name].unit, pool)) for name in cat.get("building", [])}
    return Inputs(bindings=bindings, facts=facts, collections=collections, graph_complete=False)
