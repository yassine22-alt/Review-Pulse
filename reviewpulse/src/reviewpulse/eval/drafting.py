"""I4 evaluation: score LLM drafts against hand-translated gold rules.

Per clause: is the `checkable` label right, and for drawing-checkable clauses do
fn / op / value / unit / scope match? Reported for a dev split (odd gold ids, the
only ones looked at while improving the prompt) and a held-out test split (even ids).
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml

from ..rules.clauses import Clause
from ..rules.draft import LLMClient, build_prompt, output_schema, to_rule_dict, validate

GOLD = Path(__file__).parents[3] / "tests" / "fixtures" / "i4_gold.yaml"
FIELDS = ("fn", "op", "value", "unit", "scope")
UNIT_DEFAULT = {"width_m": "m", "min_width_m": "m", "area_m2": "m2", "shortest_path_m": "m"}


def _scope(expect: dict) -> object:
    if "element" in expect:
        return ("element", expect["element"])
    if "room_types" in expect:
        return ("rooms", frozenset(expect["room_types"]))
    if "pairs" in expect:
        return ("pairs", frozenset(frozenset(p) for p in expect["pairs"]))
    return None


def _got_fields(rule: dict) -> dict:
    c = rule.get("check", {})
    at = rule.get("applies_to", {})
    scope = None
    if at.get("element"):
        scope = ("element", at["element"])
    elif at.get("room_type"):
        scope = ("rooms", frozenset(at["room_type"]))
    elif c.get("pairs"):
        scope = ("pairs", frozenset(frozenset(p) for p in c["pairs"]))
    return {"fn": c.get("fn"), "op": c.get("op"), "value": c.get("value"),
            "unit": c.get("unit") or UNIT_DEFAULT.get(c.get("fn")), "scope": scope,
            "avoid": frozenset((c.get("avoid") or {}).get("room_type", []))}


def _match(field: str, want, got) -> bool:
    if field == "value":
        return want is not None and got is not None and abs(float(want) - float(got)) <= 0.005 * max(1, abs(float(want)))
    return want == got


def _score_one(g: dict, out: dict | None, err: str | None) -> dict:
    rec = {"id": g["id"], "split": "dev" if int(g["id"][1:]) % 2 else "test", "gold": g["checkable"],
           "label_ok": False, "tp": {}, "exp": {}, "prod": {}, "note": ""}
    if out is None:
        rec["note"] = f"error: {err}"
        return rec
    cl = Clause(id=g["id"], heading="", text=g["text"], page=0, start=0, end=len(g["text"]))
    d = validate(out, cl, "gold")
    rec["label_ok"] = d.checkable == g["checkable"]
    rec["checkable"] = d.checkable
    if g["checkable"] != "from_drawings":
        rec["note"] = "refused correctly" if d.checkable != "from_drawings" else "SHOULD REFUSE"
        return rec
    exp = dict(g["expect"])
    want = {"fn": exp.get("fn"), "op": exp.get("op"), "value": exp.get("value"),
            "unit": exp.get("unit") or UNIT_DEFAULT.get(exp.get("fn")), "scope": _scope(exp)}
    rule = d.rule or to_rule_dict(out, cl, "gold") or {}
    rec["valid"] = bool(d.rule) and not d.errors
    got = _got_fields(rule) if rule else {f: None for f in FIELDS}
    misses = []
    for f in FIELDS:
        rec["exp"][f] = want[f] is not None
        rec["prod"][f] = got.get(f) is not None
        ok = want[f] is not None and _match(f, want[f], got.get(f))
        rec["tp"][f] = ok
        if want[f] is not None and not ok:
            misses.append(f"{f}: want {want[f]} got {got.get(f)}")
    if exp.get("avoid") is not None and set(exp["avoid"]) - set(got.get("avoid", ())):
        misses.append(f"avoid: want {exp['avoid']} got {sorted(got.get('avoid', ()))}")
    rec["note"] = "; ".join(misses) or "exact"
    return rec


def _aggregate(recs: list[dict]) -> dict:
    n = len(recs)
    res = {"clauses": n, "label_accuracy": round(sum(r["label_ok"] for r in recs) / n, 4) if n else 0.0}
    refuse = [r for r in recs if r["gold"] != "from_drawings"]
    res["non_checkable_refused"] = f"{sum(r['note'] == 'refused correctly' for r in refuse)}/{len(refuse)}"
    for f in FIELDS:
        e = sum(r["exp"].get(f, False) for r in recs)
        p = sum(r["prod"].get(f, False) for r in recs)
        t = sum(r["tp"].get(f, False) for r in recs)
        res[f"{f}_recall"] = round(t / e, 4) if e else 1.0
        res[f"{f}_precision"] = round(t / p, 4) if p else 1.0
    res["exact_rules"] = sum(r["note"] == "exact" for r in recs)
    return res


def run_drafting_eval(client: LLMClient, gold_path: Path = GOLD) -> tuple[dict, list]:
    gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))
    schema = output_schema()
    recs, secs = [], []
    for g in gold:
        cl = Clause(id=g["id"], heading="", text=g["text"], page=0, start=0, end=len(g["text"]))
        system, user = build_prompt(cl)
        t0 = time.perf_counter()
        try:
            out, err = client.complete(system, user, schema), None
        except Exception as e:  # noqa: BLE001 - a failure is a result
            out, err = None, str(e)[:120]
        secs.append(time.perf_counter() - t0)
        recs.append(_score_one(g, out, err))
    res = {"all": _aggregate(recs), "dev (odd ids)": _aggregate([r for r in recs if r["split"] == "dev"]),
           "test (even ids, held out)": _aggregate([r for r in recs if r["split"] == "test"]),
           "seconds_per_clause": round(sum(secs) / len(secs), 2) if secs else None}
    rows = [(r["id"], r["split"], r.get("checkable", "-"), r["note"]) for r in recs]
    return res, rows
