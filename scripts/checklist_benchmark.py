"""Benchmark: real plan-review checklists read through the product, scored without anyone judging by eye.

    python scripts/checklist_benchmark.py [--docs data/real_docs] [--scenario 01] [--out reports/benchmark] [--only allentown]

Every requirement line of the checklists in benchmarks/checklist_labels.json is read with the real model, on one plan. Each line was
labelled once, by hand, with what a correct outcome is:

  rule_now    a plan carries what the line needs, so a correct rule is expected; the label says which numbers and facts it must use
  needs_fact  the line is about the plan, but the plan model does not yet record what it needs (the label names it)
  not_plan    the line is not about a floor plan (site, structure, paperwork, electrical)
  bundle      one clause that holds several requirements, so no single rule can be right

What is reported:
  recall      of the rule_now lines, the share that became a rule that uses the right numbers and facts
  wrong       rule_now lines that became a rule with the wrong numbers or facts (the worst outcome)
  unsupported a rule written for a line that should not produce one (it must be read: is it faithful, or invented?)
  refusals    why each other line was declined, and which missing facts would unlock the most lines
The labels hold only document names, clause ids and these labels, never document text. Documents and reports are never committed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient  # noqa: E402
from real_doc_study import Real, wait  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.rules.clauses import split_document  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402
from reviewpulse.synth.random_plan import random_plan  # noqa: E402
from reviewpulse.synth.scenarios import SCENARIOS  # noqa: E402

LABELS = Path(__file__).resolve().parent.parent / "benchmarks" / "checklist_labels.json"
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def judge(spec: dict, readback: str) -> tuple[bool, str]:
    """Is a rule written for a rule_now line the right one? Numbers and facts are compared, not wording."""
    found = [float(x) for x in NUMBER.findall(readback or "")]
    want = spec.get("numbers", [])
    for w in want:
        if not any(abs(f - w) <= 0.01 * max(abs(w), 1e-9) for f in found):
            return False, f"expected the number {w:g}"
    extra = [f for f in found if f not in (0.0, 1.0) and not any(abs(f - w) <= 0.01 * max(abs(w), 1e-9) for w in want)]
    if extra:
        return False, f"unexpected number {extra[0]:g}"
    text = readback or ""
    missing = [f for f in spec.get("facts_all", []) if f not in text]
    if missing:
        return False, "does not use " + ", ".join(missing)
    if spec.get("facts_any") and not any(f in text for f in spec["facts_any"]):
        return False, "uses none of " + ", ".join(spec["facts_any"])
    return True, "right numbers and facts"


def call_errors(llm) -> int:
    """How many calls to the hosted model have failed so far (0 for a local model)."""
    client = getattr(llm.real, "inner", llm.real)
    return int(getattr(client, "usage", {}).get("errors", 0))


def hosted_exhausted(llm) -> bool:
    client = getattr(llm.real, "inner", llm.real)
    return bool(getattr(client, "usage", {}).get("daily_exhausted"))


def why(reason: str | None) -> str:
    r = (reason or "").lower()
    for key, name in (("needs something the plan does not provide", "plan lacks the fact"), ("judged not checkable", "judged not about a plan"),
                      ("grounding", "grounding refused"), ("disagreed", "checks disagreed with the sentence"),
                      ("no rule that matches", "no rule could be written")):
        if key in r:
            return name
    return "other"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="data/real_docs")
    ap.add_argument("--scenario", default="01")
    ap.add_argument("--out", default="reports/benchmark")
    ap.add_argument("--only", default="", help="part of a document name")
    ap.add_argument("--labels", default="", help="comma separated labels to read (e.g. rule_now,needs_fact): saves a hosted model's quota")
    args = ap.parse_args()
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    name, kind, kw, _ = next(s for s in SCENARIOS if s[0].startswith(args.scenario))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, llm, stop = [], Real(), False
    with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp) / "data", llm=lambda: llm, workers=1)) as c:
        paths = make_plan(Path(tmp) / name, png=False, **kw) if kind == "make" else random_plan(Path(tmp) / name, **kw)
        for docname, spec in labels.items():
            if stop:
                break
            if args.only and args.only not in docname:
                continue
            doc = Path(args.docs) / docname
            if not doc.exists():
                print(f"missing {doc}: skipped", flush=True)
                continue
            _, clauses = split_document(doc)
            by_id = {cl.id: cl for cl in clauses}
            pid = c.post("/api/projects", json={"name": doc.stem, "curator": "benchmark"}).json()["id"]
            with open(paths["dxf"], "rb") as f:
                wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": ("plan.dxf", f)}).json())
            with open(doc, "rb") as f:
                wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": (doc.name, f)}).json())
            default = spec.get("_default")
            if default:                    # a document labelled by exception: every clause not listed carries the default label
                spec = {**{cl.id: dict(default) for cl in clauses if cl.kind != "heading"},
                        **{k: v for k, v in spec.items() if k != "_default"}}
            for cid, lab in spec.items():
                if hosted_exhausted(llm):
                    print("the hosted model's daily allowance is used up: stopping; the lines read so far are kept", flush=True)
                    stop = True
                    break
                if args.labels and lab["label"] not in args.labels.split(","):
                    continue
                if cid not in by_id:
                    print(f"  {docname}: no clause {cid}", flush=True)
                    continue
                t0, failed_before = time.time(), call_errors(llm)
                r = c.post(f"/api/projects/{pid}/interpret/{cid}").json()
                drafted = r.get("status") == "DRAFTED"
                broken = call_errors(llm) - failed_before          # calls to the model that failed: not a refusal by the model
                if not drafted and "could not be reached" in (r.get("reason") or ""):
                    broken = max(broken, 1)
                if broken and not drafted:
                    outcome, detail = "call_failed", f"{broken} model call(s) failed (rate limit or network)"
                elif lab["label"] == "rule_now":
                    outcome, detail = ("declined", why(r.get("reason"))) if not drafted else (
                        ("correct", "") if judge(lab, r.get("readback"))[0] else ("wrong", judge(lab, r.get("readback"))[1]))
                else:
                    outcome, detail = ("unsupported", "") if drafted else ("declined", why(r.get("reason")))
                rows.append({"doc": docname, "id": cid, "label": lab["label"], "need": lab.get("need"), "outcome": outcome, "detail": detail,
                             "text": re.sub(r"\s+", " ", by_id[cid].text)[:300], "readback": r.get("readback"), "plain": r.get("plain"), "tried": r.get("tried"),
                             "reason": r.get("reason"), "not_checked": (r.get("program") or {}).get("not_checked") if r.get("program") else None,
                             "seconds": round(time.time() - t0, 1)})
                print(f"  {docname[:18]:<18} {cid[:12]:<12} {lab['label']:<10} {outcome:<11} {detail[:60]}", flush=True)
    (out / "rows.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    usage = getattr(getattr(llm.real, "inner", llm.real), "usage", None)
    (out / "model.json").write_text(json.dumps({"model": llm.model, "external": llm.external, "usage": usage}), encoding="utf-8")
    summary(rows, out)


def summary(rows: list[dict], out: Path) -> None:
    now = [r for r in rows if r["label"] == "rule_now"]
    right = [r for r in now if r["outcome"] == "correct"]
    wrong = [r for r in now if r["outcome"] == "wrong"]
    other = [r for r in rows if r["label"] != "rule_now"]
    unsupported = [r for r in other if r["outcome"] == "unsupported"]
    lines = ["# Checklist benchmark", "", f"Lines read: {len(rows)}. Decidable with today's plan facts: {len(now)}.", "",
             f"- recall: {len(right)} of {len(now)} decidable lines became a rule with the right numbers and facts",
             f"- wrong rules: {len(wrong)} (a rule for a decidable line with the wrong numbers or facts)",
             f"- unsupported rules: {len(unsupported)} of {len(other)} lines that should not produce a rule (each must be read below)", ""]
    lines += ["## Decidable lines", "", "| document | line | outcome | detail |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['doc'][:28]} | {r['id']} | {r['outcome']} | {r['detail']} |" for r in now]
    lines += ["", "## Rules written where none was expected (read each: faithful, or invented?)", ""]
    lines += [f"- {r['doc'][:28]} {r['id']} ({r['label']}): {r['text'][:140]} => {r['readback']}" for r in unsupported] or ["- none"]
    needs = Counter(r["need"] for r in rows if r["label"] == "needs_fact")
    lines += ["", "## Facts that would unlock the most lines", ""] + [f"- {n}: {k} line(s)" for n, k in needs.most_common()]
    reasons = Counter(r["detail"] for r in rows if r["outcome"] == "declined")
    failed = [r for r in rows if r["outcome"] == "call_failed"]
    if failed:
        lines += ["", f"## Lines whose model calls failed ({len(failed)}): not counted as refusals; run them again", ""]
        lines += [f"- {r['doc'][:28]} {r['id']}: {r['detail']}" for r in failed]
    lines += ["", "## Why lines were declined", ""] + [f"- {n}: {k}" for n, k in reasons.most_common()]
    (out / "benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({"lines": len(rows), "decidable": len(now), "correct": len(right), "wrong": len(wrong),
                                                 "unsupported": len(unsupported), "other": len(other)}), encoding="utf-8")
    print("\n".join(lines[:8]), flush=True)


if __name__ == "__main__":
    main()
