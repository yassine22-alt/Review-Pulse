"""I5 - Rule tests: every rule runs on a plan that should pass and a plan that should fail.

The failing plan comes from the generator's planted-error catalogue; a rule with
no planted error is reported as "untested" (it may still be approved by a curator,
but the report says so). Every rule also runs on the regression plans, and any
verdict change against ``reports/rule_baseline.json`` is listed for the curator.
"""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from pathlib import Path

from ..engine.run import run
from ..schema import BuildingModel
from .schema import Rule, load_pack


def _model(path: str) -> BuildingModel:
    from ..ingest.classify import inspect_file
    from ..pipeline import build_model, extract_stub

    stub = inspect_file(path)[0]
    return build_model(extract_stub(stub, Path(path).parent, preview=False))


def fixtures_for(rule_id: str) -> list[tuple[str, str]]:
    """(error switch, expected verdict) pairs that must trigger this rule."""
    from ..synth.make_plan import ERRORS

    out = []
    for err, exp in ERRORS.items():
        for rid, verdict, _subject in exp:
            if rid == rule_id:
                out.append((err, verdict))
    return sorted(set(out))


def test_rules(rules: list[Rule], seed: int = 7, fmt: str = "dxf") -> dict:
    from ..synth.make_plan import make_plan

    results: dict[str, dict] = defaultdict(dict)
    with tempfile.TemporaryDirectory() as td:
        clean = _model(make_plan(td, seed=seed, png=False)[fmt])
        for f in run(clean, rules, include_drafts=True):
            r = results[f.rule_id]
            r.setdefault("clean", set()).add(f.verdict)
        cache: dict[str, BuildingModel] = {}
        for rule in rules:
            res = results[rule.id]
            res["pass_ok"] = not ({"FAIL", "WARNING"} & res.get("clean", set()))
            fx = fixtures_for(rule.id)
            res["fixtures"] = []
            for err, verdict in fx:
                if err not in cache:
                    cache[err] = _model(make_plan(td, seed=seed, errors=(err,), png=False)[fmt])
                got = {f.verdict for f in run(cache[err], [rule], include_drafts=True)}
                res["fixtures"].append({"error": err, "expected": verdict, "got": sorted(got), "ok": verdict in got})
            res["fail_ok"] = all(x["ok"] for x in res["fixtures"]) if fx else None
    return dict(results)


def test_pack(pack: str | Path, out: Path | None = None) -> tuple[bool, str]:
    rules = load_pack(pack)
    res = test_rules(rules)
    lines = ["# Rule tests", "", "| rule | clean plan | failing fixtures | status |", "|---|---|---|---|"]
    ok_all = True
    for r in rules:
        x = res.get(r.id, {})
        clean = ",".join(sorted(x.get("clean", {"(no finding)"})))
        fx = "; ".join(f"{f['error']}: {'/'.join(f['got']) or '-'} (want {f['expected']})" for f in x.get("fixtures", []))
        if x.get("fail_ok") is None:
            status = "untested (no planted error)" if x.get("pass_ok") else "FAILS on clean plan"
            ok = bool(x.get("pass_ok"))
        else:
            ok = bool(x.get("pass_ok") and x.get("fail_ok"))
            status = "ok" if ok else "FAILING"
        ok_all &= ok
        lines.append(f"| {r.id} | {clean} | {fx or '-'} | {status} |")
    report = "\n".join(lines) + "\n"
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(report, encoding="utf-8")
        base = Path(out).with_name("rule_baseline.json")
        snapshot = {rid: sorted(v.get("clean", [])) for rid, v in res.items()}
        if base.exists():
            old = json.loads(base.read_text(encoding="utf-8"))
            changed = {k: (old.get(k), snapshot.get(k)) for k in set(old) | set(snapshot) if old.get(k) != snapshot.get(k)}
            if changed:
                report += "\nVerdict changes against the baseline (curator must confirm):\n" + \
                          "\n".join(f"- {k}: {a} -> {b}" for k, (a, b) in sorted(changed.items()))
        else:
            base.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
    return ok_all, report
