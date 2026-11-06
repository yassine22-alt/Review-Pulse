"""The experiment steps. Each one reports into the progress tracker as it runs."""

from __future__ import annotations

import copy
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from ..interpreter.schema import Program
from .arms import ARMS_E4, draft_arm
from .behavior import compare
from .drafters import ARMS, BoundedOllama
from .progress import OUT_DIR, Tracker
from .synth import Item, build_corpus, read_corpus, write_corpus

CORPUS = OUT_DIR / "corpus.jsonl"
FAMILIES = ["threshold", "conditional", "exemption", "scoped", "range", "alternative", "count", "total", "ratio",
            "exists"]


# ---- E2 / E3: corpus and scorer checks -----------------------------------------------------------

def mutants(program: dict) -> list[dict]:
    """Small wrong variants of a reference program: shifted thresholds, flipped comparators, wrong type."""
    flips = {"ge": "gt", "gt": "ge", "le": "lt", "lt": "le"}
    steps = {"m": 0.05, "m2": 0.5, "count": 1, "1": 0.05}
    out = []

    def paths(node, trail=()):
        if isinstance(node, dict):
            yield trail, node
            for key, child in node.items():
                yield from paths(child, trail + (key,))
        elif isinstance(node, list):
            for i, child in enumerate(node):
                yield from paths(child, trail + (i,))

    for trail, node in list(paths(program)):
        if node.get("node") == "literal" and isinstance(node.get("value"), (int, float)) \
                and not isinstance(node["value"], bool):
            clone = copy.deepcopy(program)
            target = clone
            for key in trail:
                target = target[key]
            target["value"] = round(node["value"] + steps.get(node.get("unit", "1"), 0.05), 6)
            out.append(clone)
        elif node.get("node") in flips:
            clone = copy.deepcopy(program)
            target = clone
            for key in trail:
                target = target[key]
            target["node"] = flips[node["node"]]
            out.append(clone)
    return out


def step_synth(tr: Tracker, n: int = 200, seed: int = 7) -> list[Item]:
    tr.start("E2", total=n, detail="sampling catalogues, programs and text")
    items = build_corpus(n, seed, "dev") + [i for i in build_corpus(n // 4, seed + 1, "test")]
    for k, i in enumerate(items):
        i.id = f"{i.split[0]}{k:04d}"
        i.program["id"] = i.program["title"] = i.id
    write_corpus(items, CORPUS)
    fam = Counter(i.family for i in items)
    lang = Counter(i.lang for i in items)
    concepts = Counter(i.params["concept"] for i in items)
    tr.finish("E2", {"items": len(items), "dev": n, "test_heldout": len(items) - n, "families": len(fam),
                     "concepts": len(concepts), "en": lang["en"], "fr": lang["fr"], "file": str(CORPUS)},
              detail=f"{len(items)} items, {len(fam)} families, {len(concepts)} concepts")
    return items


def step_scorer_check(tr: Tracker, items: list[Item], per_item_worlds: int = 200) -> None:
    """Validate the scorer itself: a program equals itself, and small errors are caught."""
    tr.start("E3", total=len(items), detail="mutation check of the scorer")
    killed = total = 0
    self_ok = 0
    t0 = time.time()
    for k, item in enumerate(items):
        ref = Program.model_validate(item.program)
        self_ok += compare(ref, ref, item.catalogue, per_item_worlds)["equivalent"]
        for mutant in mutants(item.program):
            total += 1
            killed += not compare(ref, Program.model_validate(mutant), item.catalogue, per_item_worlds)["equivalent"]
        tr.step("E3", k + 1, detail=f"mutants caught {killed}/{total}")
    tr.finish("E3", {"self_equivalent": f"{self_ok}/{len(items)}",
                     "mutants_caught": f"{killed}/{total} ({killed / max(total, 1):.1%})",
                     "seconds": round(time.time() - t0, 1)},
              detail=f"self {self_ok}/{len(items)}, mutants caught {killed}/{total}")


# ---- E1 / E4: drafting runs -----------------------------------------------------------------------

def stratified(items: list[Item], per_family: int) -> list[Item]:
    by = defaultdict(list)
    for item in items:
        by[item.family].append(item)
    return [i for fam in FAMILIES for i in by[fam][:per_family]]


def run_arms(tr: Tracker, tid: str, items: list[Item], arms: tuple[str, ...], model: str,
             out_file: Path, worlds: int = 300) -> list[dict]:
    client = BoundedOllama(model=model)
    total = len(items) * len(arms)
    tr.start(tid, total=total, detail=f"{model}: {len(items)} items x {len(arms)} arms")
    rows, done = [], 0
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as fh:
        for item in items:
            ref = Program.model_validate(item.program)
            for arm in arms:
                d = draft_arm(arm, item, client)
                row = {"item": item.id, "family": item.family, "lang": item.lang, "arm": arm,
                       "stage": d.stage, "seconds": round(d.seconds, 1), "detail": d.detail,
                       "tokens": client.last.get("tokens"), "done": client.last.get("done"),
                       "split": item.split, "repaired": d.repaired}
                client.last = {}
                if d.program is not None:
                    row |= {k: v for k, v in compare(ref, d.program, item.catalogue, worlds, seed=1).items()
                            if k in ("agreement", "equivalent", "kinds")}
                    row["program"] = d.program.model_dump(mode="json")
                elif d.raw is not None:
                    row["raw"] = d.raw
                rows.append(row)
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                done += 1
                ok = [r for r in rows if r["arm"] == arm and r["stage"] == "ok"]
                tr.step(tid, done, detail=f"{item.id} {arm}: {d.stage}, "
                        f"{arm} valid {len(ok)}/{sum(r['arm'] == arm for r in rows)}")
    return rows


def summarise(rows: list[dict]) -> dict:
    out = {}
    for arm in sorted({r["arm"] for r in rows}):
        sub = [r for r in rows if r["arm"] == arm]
        stages = Counter(r["stage"] for r in sub)
        valid = [r for r in sub if r["stage"] == "ok"]
        equiv = sum(r["equivalent"] for r in valid)
        missed = sum(r["kinds"].get("missed_violation", 0) > 0 for r in valid)
        alarm = sum(r["kinds"].get("false_alarm", 0) > 0 for r in valid)
        out[arm] = {
            "n": len(sub),
            "valid": f"{len(valid)}/{len(sub)}",
            "equivalent_of_all": f"{equiv}/{len(sub)} ({equiv / len(sub):.0%})",
            "equivalent_of_valid": f"{equiv}/{len(valid)}" if valid else "0/0",
            "wrong_but_valid": len(valid) - equiv,
            "with_missed_violation": missed,
            "with_false_alarm": alarm,
            "fail_stages": {k: v for k, v in stages.items() if k != "ok"},
            "median_seconds": round(statistics.median(r["seconds"] for r in sub), 1),
        }
    return out


def by_family(rows: list[dict]) -> dict:
    table = {}
    for arm in sorted({r["arm"] for r in rows}):
        for fam in FAMILIES:
            sub = [r for r in rows if r["arm"] == arm and r["family"] == fam]
            if sub:
                table.setdefault(fam, {})[arm] = f"{sum(bool(r.get('equivalent')) for r in sub)}/{len(sub)}"
    return table


def step_probe(tr: Tracker, model: str = "qwen2.5:7b", per_family: int = 2) -> dict:
    items = stratified(read_corpus(CORPUS), per_family)
    rows = run_arms(tr, "E1", items, ARMS, model, OUT_DIR / "probe_rows.jsonl")
    summary = summarise(rows)
    (OUT_DIR / "probe_summary.json").write_text(json.dumps(
        {"model": model, "summary": summary, "by_family": by_family(rows)}, indent=1), encoding="utf-8")
    flat_metrics = {f"{arm}": f"valid {s['valid']}, equivalent {s['equivalent_of_all']}, median {s['median_seconds']}s"
                    for arm, s in summary.items()}
    tr.finish("E1", flat_metrics, detail="; ".join(f"{a}: {s['equivalent_of_all']}" for a, s in summary.items()))
    return summary


def step_baseline(tr: Tracker, model: str = "qwen2.5:7b", n: int = 30, arms: tuple[str, ...] = ARMS_E4,
                  tid: str = "E4", name: str = "baseline") -> dict:
    """n items, two thirds from dev concepts and one third from concepts the drafter never saw in dev."""
    pool = read_corpus(CORPUS)
    dev = stratified([i for i in pool if i.split == "dev"], max(1, round(n / 15)))
    held = stratified([i for i in pool if i.split == "test"], max(1, round(n / 30)))
    items = dev + held
    rows = run_arms(tr, tid, items, arms, model, OUT_DIR / f"{name}_rows.jsonl")
    summary = summarise(rows)
    per_split = {}
    for sp in ("dev", "test"):
        sub = [r for r in rows if r.get("split") == sp]
        if sub:
            per_split[sp] = summarise(sub)
    (OUT_DIR / f"{name}_summary.json").write_text(json.dumps(
        {"model": model, "n": len(items), "summary": summary, "per_split": per_split,
         "by_family": by_family(rows)}, indent=1), encoding="utf-8")
    flat_metrics = {arm: f"valid {s['valid']}, equivalent {s['equivalent_of_all']}, "
                         f"missed {s['with_missed_violation']}, false alarm {s['with_false_alarm']}, "
                         f"median {s['median_seconds']}s" for arm, s in summary.items()}
    tr.finish(tid, flat_metrics, detail="; ".join(f"{a}: {s['equivalent_of_all']}" for a, s in summary.items()))
    return summary


# ---- E9: the sentence-versus-rule verifier, tested without a model --------------------------------

def drop_scope(program: dict) -> dict | None:
    """The rule with its category condition removed: the 'applies to every member' failure."""
    clone = copy.deepcopy(program)
    changed = False

    def visit(node):
        nonlocal changed
        if isinstance(node, dict):
            where = node.get("where")
            if where:
                if where.get("node") == "eq" and where["left"].get("name", "").endswith("_kind"):
                    del node["where"]
                    changed = True
                elif where.get("node") == "all":
                    rest = [a for a in where["args"]
                            if not (a.get("node") == "eq" and a["left"].get("name", "").endswith("_kind"))]
                    if len(rest) < len(where["args"]):
                        node["where"] = rest[0] if len(rest) == 1 else {"node": "all", "args": rest}
                        changed = True
            for child in list(node.values()):
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(clone)
    return clone if changed else None


def step_verifier(tr: Tracker, items: list[Item]) -> None:
    from .verify import blocking, verify

    tr.start("E9", total=len(items), detail="verifier on correct and broken rules")
    false_rejects, correct = [], 0
    caught: dict[str, list[int]] = {"threshold shifted": [0, 0], "comparator flipped": [0, 0],
                                    "category condition dropped": [0, 0]}
    for k, item in enumerate(items):
        ref = Program.model_validate(item.program)
        correct += 1
        issues = blocking(verify(ref, item.text, item.catalogue, item.lang))
        if issues:
            false_rejects.append((item.id, item.text[:80], [i.message for i in issues][:2]))
        for mutant in mutants(item.program):
            label = "comparator flipped" if _is_flip(item.program, mutant) else "threshold shifted"
            caught[label][1] += 1
            caught[label][0] += bool(blocking(verify(Program.model_validate(mutant), item.text, item.catalogue,
                                                    item.lang)))
        dropped = drop_scope(item.program)
        if dropped:
            caught["category condition dropped"][1] += 1
            caught["category condition dropped"][0] += bool(
                blocking(verify(Program.model_validate(dropped), item.text, item.catalogue, item.lang)))
        tr.step("E9", k + 1, detail=f"false rejects {len(false_rejects)}/{correct}")
    metrics = {"correct_rules_wrongly_blocked": f"{len(false_rejects)}/{correct}"}
    metrics |= {f"caught: {name}": f"{c}/{t} ({c / max(t, 1):.0%})" for name, (c, t) in caught.items()}
    (OUT_DIR / "verifier_false_rejects.json").write_text(json.dumps(false_rejects, indent=1, ensure_ascii=False),
                                                         encoding="utf-8")
    tr.finish("E9", metrics, detail=f"false rejects {len(false_rejects)}/{correct}")


def _is_flip(original: dict, mutant: dict) -> bool:
    """True when the mutant differs from the original only by a changed comparator name."""
    return json.dumps(original, sort_keys=True).replace('"ge"', "").replace('"gt"', "").replace('"le"', "") \
        .replace('"lt"', "") == json.dumps(mutant, sort_keys=True).replace('"ge"', "").replace('"gt"', "") \
        .replace('"le"', "").replace('"lt"', "")


# ---- E10: does the sentence check survive meaning-preserving rewrites of the sentence? --------------------------

def step_stress(tr: Tracker, items: list[Item]) -> None:
    from .stress import KINDS, perturb
    from .verify import blocking, verify

    total = len(items) * len(KINDS)
    tr.start("E10", total=total, detail="sentence check under meaning-preserving rewrites")
    done, metrics, examples = 0, {}, []
    for kind in KINDS:
        wrongly_blocked = caught = droppable = 0
        for item in items:
            moved = perturb(item, kind)
            ref = Program.model_validate(item.program)
            issues = blocking(verify(ref, moved.text, moved.catalogue, moved.lang))
            if issues:
                wrongly_blocked += 1
                if len(examples) < 12:
                    examples.append({"rewrite": kind, "text": moved.text[:160], "issues": [i.message for i in issues]})
            dropped = drop_scope(item.program)
            if dropped:
                droppable += 1
                caught += bool(blocking(verify(Program.model_validate(dropped), moved.text, moved.catalogue,
                                               moved.lang)))
            done += 1
        tr.step("E10", done, detail=f"{kind}: correct rules wrongly blocked {wrongly_blocked}/{len(items)}")
        metrics[kind] = f"wrongly blocked {wrongly_blocked}/{len(items)}; dropped condition caught {caught}/{droppable}"
    (OUT_DIR / "stress_examples.json").write_text(json.dumps(examples, indent=1, ensure_ascii=False), encoding="utf-8")
    tr.finish("E10", metrics, detail="see metrics")
