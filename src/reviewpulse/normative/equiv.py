"""Logical equivalence of two obligation trees, by enumerating fact worlds.

Two trees are equivalent when, in every world, both compile to programs that the interpreter's own `run_program` gives the same
outcome (NOT_APPLICABLE, EXEMPT, SATISFIED, VIOLATED, UNRESOLVED). Nothing here knows what a fact means.

Worlds
  The tests of both trees cut the line of each numeric fact at their limits. Every cut point, and a value strictly between two cut
  points, below the first and above the last, is a "cell": a fact behaves the same everywhere inside a cell, so trying one value of
  every cell is EXACT for numeric limits (>=, >, <=, <, ==, != on any fact, any unit) with no solver. Booleans have two cells, text
  facts one cell per literal plus "other".
  * no scope: every combination of cells is run when there are at most MAX_EXACT of them (exact: true);
  * with a scope: every combination of building cells with a scope of 0 members and with 1 member in every cell, plus random worlds
    of 2 to 3 members (exact for 0 and 1 members, sampled beyond);
  * too many cells: a seeded random sample of at least `n_worlds` worlds (exact: false), always including every single fact sweep.
  z3 is not installed in this environment, so no SMT proof is attempted (`smt()` says so).

A mismatch is localised: each node of the first tree is replaced in turn by the node of the second tree at the same path; the nodes
whose replacement restores equivalence are the ones to repair (deepest first).
"""

from __future__ import annotations

import itertools
import random
import re
from dataclasses import dataclass, field

from ..interpreter import units
from ..interpreter.runtime import run_program
from ..interpreter.schema import Collection, Fact, Inputs
from .compile import BUILDING, CompileError, bindings_of, compile_obligation
from .schema import FactSpec, NormTree, Obligation, cond_paths

MAX_EXACT = 2048


def smt() -> dict:
    try:
        import z3  # noqa: F401
    except ImportError:
        return {"status": "skipped", "reason": "z3 is not installed; the cell enumeration is exact for numeric limits instead"}
    return {"status": "available"}


# ------------------------------------------------------------------------------------------------------------ the facts
def merged_facts(a: NormTree, b: NormTree) -> tuple[dict[str, FactSpec], list[str]]:
    facts: dict[str, FactSpec] = {}
    clashes = []
    for tree in (a, b):
        for f in tree.facts:
            old = facts.get(f.name)
            if old is None:
                facts[f.name] = f
            elif (old.kind, old.unit, old.owner, old.collection) != (f.kind, f.unit, f.owner, f.collection):
                clashes.append(f.name)
    return facts, clashes


def _cuts(trees: list[NormTree], specs: dict[str, FactSpec], extra: dict[str, set] | None = None) -> dict[str, set]:
    cuts: dict[str, set] = {n: set(extra.get(n, ())) if extra else set() for n in specs}
    for tree in trees:
        for ob in tree.obligations:
            for c in (n for n in _all_cond(ob) if n.kind == "test"):
                spec = specs[c.fact]
                v = c.value
                if spec.kind == "number" and type(v) not in (bool, str):
                    if c.unit not in ("1", spec.unit):
                        try:
                            v = units.convert(float(v), c.unit, spec.unit)
                        except units.UnitError:
                            continue
                    cuts[c.fact].add(round(float(v), 9))
                elif spec.kind == "string" and isinstance(v, str):
                    cuts[c.fact].add(v)
    return cuts


def _all_cond(ob: Obligation):
    for _, c in cond_paths(ob):
        yield c


def _domain(spec: FactSpec, cuts: set) -> list:
    if spec.kind == "boolean":
        return [True, False]
    if spec.kind == "string":
        return sorted(cuts) + ["__other__"]
    pts = sorted(cuts)
    if not pts:
        return [1.0]
    out = []
    below = pts[0] / 2 if pts[0] > 0 else pts[0] - 1.0
    out.append(round(below, 9))
    for i, p in enumerate(pts):
        out.append(p)
        out.append(round((p + pts[i + 1]) / 2, 9) if i + 1 < len(pts) else round(p + max(abs(p), 1.0) * 0.5, 9))
    return out


@dataclass
class World:
    building: dict
    members: dict[str, list[dict]] = field(default_factory=dict)


def _inputs(w: World, specs: dict[str, FactSpec], trees: list[NormTree]) -> Inputs:
    binds = {}
    for t in trees:
        binds.update(bindings_of(t))
    facts: dict[str, dict[str, Fact]] = {BUILDING: {k: Fact(value=v, source="world", trusted=True) for k, v in w.building.items()}}
    colls = {}
    for coll, rows in w.members.items():
        ids = []
        for i, row in enumerate(rows):
            eid = f"{coll}_{i}"
            ids.append(eid)
            facts[eid] = {k: Fact(value=v, source="world", trusted=True) for k, v in row.items()}
        colls[coll] = Collection(items=ids, complete=True, trusted=True)
    return Inputs(bindings=binds, facts=facts, collections=colls, graph_complete=False)


def make_worlds(trees: list[NormTree], specs: dict[str, FactSpec], n_worlds: int = 128, seed: int = 0,
                extra_cuts: dict[str, set] | None = None) -> tuple[list[World], bool, str]:
    cuts = _cuts(trees, specs, extra_cuts)
    dom = {n: _domain(s, cuts[n]) for n, s in specs.items()}
    bnames = [n for n, s in specs.items() if s.owner == "building"]
    colls: dict[str, list[str]] = {}
    for n, s in specs.items():
        if s.owner == "member":
            colls.setdefault(s.collection, []).append(n)
    for t in trees:                                     # a scope over a collection with no member fact still needs members
        for ob in t.obligations:
            if ob.scope:
                colls.setdefault(ob.scope.collection, [])
    rng = random.Random(seed)
    bsize = 1
    for n in bnames:
        bsize *= len(dom[n])
    msize = {c: 1 for c in colls}
    for c, names in colls.items():
        for n in names:
            msize[c] *= len(dom[n])
    total = bsize
    for c in colls:
        total *= 1 + msize[c]
    worlds: list[World] = []
    if total <= MAX_EXACT:
        bcombos = [dict(zip(bnames, vals, strict=True)) for vals in itertools.product(*[dom[n] for n in bnames])]
        mopts = {c: [[]] + [[dict(zip(names, vals, strict=True))]
                            for vals in itertools.product(*[dom[n] for n in names])] for c, names in colls.items()}
        for b in bcombos:
            for pick in itertools.product(*[mopts[c] for c in colls]):
                worlds.append(World(dict(b), dict(zip(colls, pick, strict=True))))
        if colls:                                       # 2 to 3 members: sampled
            for _ in range(64):
                worlds.append(World({n: rng.choice(dom[n]) for n in bnames},
                                    {c: [{n: rng.choice(dom[n]) for n in names} for _ in range(rng.randint(2, 3))]
                                     for c, names in colls.items()}))
        return worlds, not colls, "exhaustive cells"

    def rand_world() -> World:
        return World({n: rng.choice(dom[n]) for n in bnames},
                     {c: [{n: rng.choice(dom[n]) for n in names} for _ in range(rng.randint(0, 3))] for c, names in colls.items()})

    for n in bnames:                                    # single fact sweeps first
        for v in dom[n]:
            w = rand_world()
            w.building[n] = v
            worlds.append(w)
    while len(worlds) < max(n_worlds, 64):
        worlds.append(rand_world())
    return worlds, False, "sampled"


# -------------------------------------------------------------------------------------------------------------- compare
def outcome(program, inputs: Inputs) -> str:
    try:
        return run_program(program, inputs, include_drafts=True)["outcome"]
    except ValueError:
        return "ERROR"


@dataclass
class EquivResult:
    equivalent: bool
    exact: bool = False
    mode: str = ""
    n_worlds: int = 0
    reason: str = ""
    mismatches: list[dict] = field(default_factory=list)
    repair: list[str] = field(default_factory=list)       # "<obligation index>:<path>" nodes of the FIRST tree to repair

    def __bool__(self) -> bool:
        return self.equivalent


def _pair_equivalent(a: NormTree, oa: Obligation, b: NormTree, ob: Obligation, worlds, specs, limit: int = 5):
    pa, pb = compile_obligation(a, oa), compile_obligation(b, ob)
    bad = []
    for w in worlds:
        inp = _inputs(w, specs, [a, b])
        x, y = outcome(pa, inp), outcome(pb, inp)
        if x != y:
            bad.append({"first": x, "second": y, "world": {"building": w.building, "members": w.members}})
            if len(bad) >= limit:
                break
    return bad


def equivalent(a: NormTree, b: NormTree, n_worlds: int = 128, seed: int = 0, localise: bool = True) -> EquivResult:
    """Do the two trees give the same outcome in every fact world? Spans and wording do not matter, behaviour does."""
    specs, clashes = merged_facts(a, b)
    if clashes:
        return EquivResult(False, reason=f"the two trees declare different kinds, units or owners for: {', '.join(sorted(clashes))}",
                           repair=[f"facts:{c}" for c in sorted(clashes)])
    if len(a.obligations) != len(b.obligations):
        return EquivResult(False, reason=f"{len(a.obligations)} obligations against {len(b.obligations)}", repair=["obligations"])
    worlds, exact, mode = make_worlds([a, b], specs, n_worlds, seed)
    res = EquivResult(True, exact, mode, len(worlds))
    for i, (oa, ob) in enumerate(zip(a.obligations, b.obligations, strict=True)):
        try:
            bad = _pair_equivalent(a, oa, b, ob, worlds, specs)
        except CompileError as exc:
            res.equivalent = False
            res.reason = f"obligation {i}: does not compile: {exc}"
            res.repair.append(f"{i}:compile")
            continue
        if bad:
            res.equivalent = False
            res.mismatches += [{"obligation": i, **m} for m in bad]
            res.reason = res.reason or f"obligation {i}: {bad[0]['first']} against {bad[0]['second']} in a world"
            if localise:
                res.repair += [f"{i}:{p}" for p in _localise(a, oa, b, ob, worlds, specs)]
    return res


# ----------------------------------------------------------------------------------------------------------- localising
TOKEN = re.compile(r"([A-Za-z_]+)|\[(\d+)\]")


def _tokens(path: str) -> list:
    return [m.group(1) if m.group(1) else int(m.group(2)) for m in TOKEN.finditer(path)]


def _get(d, toks):
    for t in toks:
        try:
            d = d[t]
        except (KeyError, IndexError, TypeError):
            return None, False
    return d, True


def _set(d, toks, value) -> bool:
    parent, ok = _get(d, toks[:-1])
    if not ok or parent is None:
        return False
    try:
        parent[toks[-1]] = value
    except (KeyError, IndexError, TypeError):
        return False
    return True


def _strip_spans(x):
    if isinstance(x, dict):
        return {k: _strip_spans(v) for k, v in x.items() if k != "span"}
    if isinstance(x, list):
        return [_strip_spans(v) for v in x]
    return x


def _localise(a: NormTree, oa: Obligation, b: NormTree, ob: Obligation, worlds, specs) -> list[str]:
    da, db = oa.model_dump(), ob.model_dump()
    paths = ["modality", "scope", "applicability", "requirement", "exceptions", "unresolved"]
    paths += [p for p, _ in cond_paths(oa) if p not in paths]
    paths += [p for p, _ in cond_paths(ob) if p not in paths]
    fixing = []
    for p in paths:
        toks = _tokens(p)
        vb, okb = _get(db, toks)
        va, oka = _get(da, toks)
        if not okb or not oka and len(toks) > 1:
            continue
        if _strip_spans(va) == _strip_spans(vb):
            continue
        patched = _strip_spans(da)
        if not _set(patched, toks, _strip_spans(vb)):
            continue
        try:
            new = Obligation.model_validate(patched)
            if not _pair_equivalent(a, new, b, ob, worlds, specs, limit=1):
                fixing.append(p)
        except (ValueError, CompileError):
            continue
    if fixing:
        return sorted(fixing, key=lambda p: (-len(_tokens(p)), p))
    differing = [p for p in ("modality", "scope", "applicability", "requirement", "exceptions", "unresolved")
                 if _strip_spans(da.get(p)) != _strip_spans(db.get(p))]
    return differing or ["requirement"]


def facts_used(tree: NormTree) -> set[str]:
    return {c.fact for ob in tree.obligations for _, c in cond_paths(ob) if c.kind == "test"}





def run_tree(tree: NormTree, building: dict | None = None, members: dict | None = None) -> list[str]:
    """The outcome of every obligation of a tree in one named world (values in each fact's own unit)."""
    specs = {f.name: f for f in tree.facts}
    world = World(dict(building or {}), {k: [dict(r) for r in v] for k, v in (members or {}).items()})
    inp = _inputs(world, specs, [tree])
    return [outcome(compile_obligation(tree, ob), inp) for ob in tree.obligations]


def program_cuts(program) -> dict[str, set]:
    """Limits and text values a Program (for example one the benchmark wrote) compares each fact with."""
    from ..interpreter.schema import BinaryExpr, FactExpr, LiteralExpr, walk

    cuts: dict[str, set] = {}
    for expr in (program.applicability, program.exemption, program.requirement):
        for n in walk(expr):
            if isinstance(n, BinaryExpr):
                for f, lit in ((n.left, n.right), (n.right, n.left)):
                    if isinstance(f, FactExpr) and isinstance(lit, LiteralExpr) and type(lit.value) is not bool:
                        cuts.setdefault(f.name, set()).add(round(lit.value, 9) if not isinstance(lit.value, str) else lit.value)
    return cuts


def compare_program(tree: NormTree, index: int, program, n_worlds: int = 128, seed: int = 0) -> EquivResult:
    """Does obligation `index` of the tree behave like an existing Program (same facts, same collections) in every world?"""
    specs = {f.name: f for f in tree.facts}
    worlds, exact, mode = make_worlds([tree], specs, n_worlds, seed, extra_cuts=program_cuts(program))
    res = EquivResult(True, exact, mode, len(worlds))
    mine = compile_obligation(tree, tree.obligations[index])
    for w in worlds:
        inp = _inputs(w, specs, [tree])
        a, b = outcome(mine, inp), outcome(program, inp)
        if a != b:
            res.equivalent = False
            res.mismatches.append({"first": a, "second": b, "world": {"building": w.building, "members": w.members}})
            if len(res.mismatches) >= 5:
                break
    if not res.equivalent:
        res.reason = f"{res.mismatches[0]['first']} against {res.mismatches[0]['second']} in a world"
    return res


def compare_program_all(tree: NormTree, program, n_worlds: int = 128, seed: int = 0) -> EquivResult:
    """Like `compare_program`, for a Program written for the whole clause: it is compared with ALL obligations of the tree together
    (violated when any obligation is violated, unresolved when any is, satisfied when one is satisfied and none violated)."""
    specs = {f.name: f for f in tree.facts}
    worlds, exact, mode = make_worlds([tree], specs, n_worlds, seed, extra_cuts=program_cuts(program))
    res = EquivResult(True, exact, mode, len(worlds))
    mine = [compile_obligation(tree, ob) for ob in tree.obligations]
    for w in worlds:
        inp = _inputs(w, specs, [tree])
        outs = [outcome(p, inp) for p in mine]
        a = ("VIOLATED" if "VIOLATED" in outs else "UNRESOLVED" if "UNRESOLVED" in outs else
             "SATISFIED" if "SATISFIED" in outs else outs[0])
        b = outcome(program, inp)
        if a != b:
            res.equivalent = False
            res.mismatches.append({"first": a, "second": b, "world": {"building": w.building, "members": w.members}})
            if len(res.mismatches) >= 5:
                break
    if not res.equivalent:
        res.reason = f"{res.mismatches[0]['first']} against {res.mismatches[0]['second']} in a world"
    return res
