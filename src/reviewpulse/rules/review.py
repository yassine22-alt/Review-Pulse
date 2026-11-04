"""I5 - Curator review and rule self-tests.

``rp rules review drafts/<doc>.drafts.yaml --pack rules/packs/<name>`` shows each
clause beside its draft and offers approve / edit / reject / skip. Approval writes
``<pack>/<id>.yaml`` with status, approved_by and version - but only after the
rule passes its self-test (a passing and a failing case, see ``selftest``).
"""

from __future__ import annotations

import copy
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from .schema import Rule, dump_rule

METRIC_FNS = {"width_m": ("element", "width_m"), "area_m2": ("room", "area_m2"),
              "min_width_m": ("room", "min_width_m")}


@dataclass
class SelfTest:
    status: str            # ok | failing | untested
    detail: str


def _oracle_model(seed: int = 7, errors: tuple = ()):
    from ..eval.adapters.synth import load_truth, truth_model
    from ..ingest.dxf_reader import extract_dxf
    from ..synth.make_plan import make_plan

    with tempfile.TemporaryDirectory() as td:
        p = make_plan(td, seed=seed, errors=errors, png=False)
        sheet = extract_dxf(Path(p["dxf"]), "selftest")
        from ..annotate.text_classify import classify_items

        classify_items(sheet.texts)
        return truth_model(load_truth(p["truth"]), sheet)


def _metric_selftest(rule: Rule) -> SelfTest:
    from ..engine.context import Context
    from ..engine.run import run

    kind, attr = METRIC_FNS[rule.check.fn]
    if kind == "room" and rule.applies_to.get("element"):
        return SelfTest("failing", f"{rule.check.fn} measures rooms, but the rule applies to "
                                   f"{rule.applies_to['element']} elements")
    base = _oracle_model()
    ctx = Context.of(base)
    subjects = ctx.elements_for(rule.applies_to) if kind == "element" else ctx.rooms_for(rule.applies_to)
    if not subjects:
        return SelfTest("untested", f"no {rule.applies_to} in the test plan")
    limit = float(rule.check.value)
    unit = rule.check.unit
    limit = limit / 100 if unit == "cm" else limit / 1000 if unit == "mm" else limit
    # probe clearly outside the policy's tolerance band (areas 5 %, lengths 1 % / 1 cm), or a correct
    # rule reads as WARNING at the probe and could never be approved
    from ..engine.policy import AREA_TOL_REL, length_tol

    tol = AREA_TOL_REL * abs(limit) if unit == "m2" else length_tol(limit)
    margin = max(2 * tol, 0.05 * abs(limit), 0.05)
    good = limit + margin if rule.check.op in (">=", ">") else limit - margin
    bad = limit - margin if rule.check.op in (">=", ">") else limit + margin
    results = {}
    for name, val in (("pass", good), ("fail", bad)):
        m = copy.deepcopy(base)
        sid = subjects[0].id
        for coll in (m.elements, m.rooms):
            for obj in coll:
                if obj.id == sid:
                    if kind == "element":
                        obj.attrs[attr] = val
                    else:
                        setattr(obj, attr, val)
        verdicts = {f.verdict for f in run(m, [rule], include_drafts=True) if sid in f.subject_ids}
        results[name] = verdicts
    ok = results["pass"] == {"PASS"} and "FAIL" in results["fail"]
    return SelfTest("ok" if ok else "failing",
                    f"subject at {good:.3f} -> {sorted(results['pass'])}; at {bad:.3f} -> {sorted(results['fail'])}")


def _catalogue_selftest(rule: Rule, pack_rules: list[Rule]) -> SelfTest:
    """Use the planted errors of starter rules that call the same function."""
    from ..engine.run import run
    from ..synth.make_plan import ERRORS

    same = {r.id for r in pack_rules if r.check.fn == rule.check.fn}
    errs = sorted({e for e, exp in ERRORS.items() for rid, _v, _s in exp if rid in same})
    if not errs:
        return SelfTest("untested", f"no planted error exercises {rule.check.fn}")
    clean = {f.verdict for f in run(_oracle_model(), [rule], include_drafts=True)}
    if "FAIL" in clean:
        return SelfTest("failing", "fails on the clean plan")
    hits = []
    for e in errs:
        got = {f.verdict for f in run(_oracle_model(errors=(e,)), [rule], include_drafts=True)}
        hits.append((e, "FAIL" in got or "WARNING" in got))
    if any(h for _, h in hits):
        return SelfTest("ok", "clean plan passes; triggered by " + ", ".join(e for e, h in hits if h))
    return SelfTest("untested", "clean plan passes; none of " + ", ".join(errs) + " triggers it (may be correct)")


def threshold_gaps(rule: Rule) -> str:
    """What a threshold rule lacks to be evaluated ("" when complete)."""
    if rule.cls != "threshold":
        return ""
    gaps = [k for k, v in (("a comparison (check.op)", rule.check.op), ("a value (check.value)", rule.check.value))
            if v is None]
    return " and ".join(gaps)


def selftest(rule: Rule, pack_rules: list[Rule] | None = None) -> SelfTest:
    if rule.check.fn in METRIC_FNS and rule.check.op and rule.check.value is not None:
        return _metric_selftest(rule)
    return _catalogue_selftest(rule, pack_rules or [])


def approve(rule_dict: dict, pack_dir: Path, curator: str, pack_rules: list[Rule] | None = None,
            force_untested: bool = True) -> tuple[bool, str]:
    rd = dict(rule_dict, status="approved", approved_by=curator)
    rule = Rule.model_validate(rd)
    missing = threshold_gaps(rule)
    if missing:
        return False, f"not approved: a threshold rule needs {missing}; edit the rule first"
    st = selftest(rule, pack_rules)
    if st.status == "failing" or (st.status == "untested" and not force_untested):
        return False, f"not approved: self-test {st.status}: {st.detail}"
    pack_dir.mkdir(parents=True, exist_ok=True)
    path = pack_dir / f"{rule.id}.yaml"
    if path.exists():
        old = yaml.safe_load(path.read_text(encoding="utf-8"))
        rule = rule.model_copy(update={"version": int(old.get("version", 1)) + 1})
    path.write_text(dump_rule(rule), encoding="utf-8")
    return True, f"approved -> {path} (self-test {st.status}: {st.detail})"
