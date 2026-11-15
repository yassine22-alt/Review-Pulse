"""Scripted walkthrough of the whole combined flow against a RUNNING server, narrated step by step.

    python scripts/walkthrough.py                   # uses http://127.0.0.1:8000, opens the results tab at the end
    python scripts/walkthrough.py --no-browser

It does what a person would do in the app (create a project, upload a plan with planted errors, run the check),
then goes through the new layers: plan -> fact graph -> rules drafted from that plan's own catalogue -> ykram051's
checker. Everything is printed as it happens and mirrored to reports/extractor_eval/walkthrough.log.
This is a deterministic script, not an AI agent: the only model calls are the rule drafting steps.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "reports" / "extractor_eval" / "walkthrough.log"
DOC = ROOT / "docs" / "requirements_example.md"
ERRORS = ("metric_door_narrow", "metric_room_small", "topo_exit_via_bath", "cons_chain_off", "comp_tag_missing")
CLAUSES = [("Art. 6.1", "a door width, measured on the plan"),
           ("Art. 6.3", "two conditions on one room type, both measured"),
           ("Art. 7.2", "asks for a window HEIGHT, which the plan reader does not measure")]


class Tee:
    def __init__(self):
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self.fh = LOG.open("w", encoding="utf-8")

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        self.fh.write(text + "\n")
        self.fh.flush()


say = Tee()
SYM = {"eq": "=", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">=", "add": "+", "sub": "-", "mul": "x",
       "div": "/"}


def explain(node: dict) -> str:
    """A plain-language readback of a program expression, generated from the rule itself."""
    kind = node["node"]
    if kind == "literal":
        return f"{node['value']}" + (f" {node['unit']}" if node.get("unit") not in (None, "1") else "")
    if kind == "fact":
        who = "" if node["entity"].startswith("$") else f"{node['entity']}."
        return f"{who}{node['name']}"
    if kind in ("all", "any"):
        return "(" + f" {'AND' if kind == 'all' else 'OR'} ".join(explain(a) for a in node["args"]) + ")"
    if kind == "not":
        return "NOT " + explain(node["args"][0])
    if kind in SYM:
        return f"{explain(node['left'])} {SYM[kind]} {explain(node['right'])}"
    scope = f"each {node['collection']}" + (f" where {explain(node['where'])}" if node.get("where") else "")
    if kind == "forall":
        return f"for {scope}: {explain(node['body'])}"
    if kind == "exists":
        return f"there is some {scope[5:]} such that {explain(node['body'])}"
    if kind == "count":
        return f"number of {node['collection']}" + (f" where {explain(node['where'])}" if node.get("where") else "")
    return f"{kind} of {explain(node['body'])} over {scope}"


def wait(c: httpx.Client, pid: str, job: dict, label: str) -> dict:
    last = ""
    while True:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        msg = f"      {label}: {rec['message']} ({round(100 * rec['progress'])}%)"
        if msg != last:
            say(msg)
            last = msg
        if rec["status"] == "done":
            return rec
        if rec["status"] == "failed":
            raise SystemExit(f"{label} failed: {rec['error']}")
        time.sleep(1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--data", default=str(ROOT / "data" / "app"))
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    from reviewpulse.factgraph import io as fio
    from reviewpulse.factgraph import to_catalogue, to_inputs
    from reviewpulse.factgraph.from_building import from_building
    from reviewpulse.schema import BuildingModel
    from reviewpulse.synth.make_plan import make_plan
    from reviewpulse.xeval.arms import draft_arm
    from reviewpulse.xeval.status import clause_status
    from reviewpulse.xeval.drafters import BoundedOllama
    from reviewpulse.xeval.synth import Item
    from reviewpulse.xeval.verify import verify

    c = httpx.Client(base_url=a.url, timeout=120)
    health = c.get("/api/health").json()
    say(f"[1/7] SERVER  {a.url}  drafting model {health['llm']['model']} "
        f"({'online' if health['llm']['available'] else 'offline'})")

    say("[2/7] PROJECT  create, then upload a generated plan with 5 planted errors")
    out = Path(a.data) / "walkthrough_inputs"
    paths = make_plan(out, seed=11, errors=ERRORS, png=False, name="walk_plan")
    pid = c.post("/api/projects", json={"name": "Walkthrough · plan with planted errors", "curator": "walkthrough",
                                        "base_pack": "starter"}).json()["id"]
    say(f"      project {pid}")
    t0 = time.time()
    with open(paths["dxf"], "rb") as f:
        job = c.post(f"/api/projects/{pid}/plan", files={"file": (Path(paths["dxf"]).name, f)}).json()
    res = wait(c, pid, job, "plan")["result"]
    say(f"      analysed in {time.time() - t0:.1f}s: {res['elements']} elements, {res['rooms']} rooms, tier {res['tiers']}")

    say("[3/7] CHECK  run the starter rule pack on the plan (what the Results tab shows)")
    res = wait(c, pid, c.post(f"/api/projects/{pid}/check").json(), "check")["result"]
    say(f"      {res['rules']['total']} rules: {res['summary']}")
    found = c.get(f"/api/projects/{pid}/findings").json()["findings"]
    truth = json.loads(Path(paths["truth"]).read_text(encoding="utf-8"))
    expected = sorted({e["rule"] for e in truth["expected_findings"]})
    raised = {f["rule_id"] for f in found if f["verdict"] in ("FAIL", "WARNING")}
    for f in found:
        if f["verdict"] in ("FAIL", "WARNING"):
            say(f"      {f['verdict']:<8} {f['rule_id']:<8} {f['message'][:95]}")
    say(f"      planted errors found: {len([r for r in expected if r in raised])}/{len(expected)}  ({expected})")

    say("[4/7] FACT GRAPH  turn the analysed plan into the new facts format")
    building = next(Path(a.data).glob(f"projects/{pid}/run/building_*.json"))
    model = BuildingModel.model_validate_json(building.read_text(encoding="utf-8"))
    fg = from_building(model, complete=True)
    fio.dump(fg, building.with_name("factgraph.json"))
    cat = to_catalogue(fg)
    trusted = sum(f.trusted for n in fg.nodes for f in n.attrs.values())
    total = sum(len(n.attrs) for n in fg.nodes)
    say(f"      tier {fg.provenance.tier}, {len(fg.nodes)} nodes, {len(fg.edges)} edges, "
        f"{trusted}/{total} facts trusted")
    for coll, spec in cat["collections"].items():
        say(f"      {coll}: {', '.join(spec['facts'])}")
    inputs = to_inputs(fg).model_dump(mode="json")

    say("[5/7] INTERPRETER  clauses from the requirement document, drafted against THIS plan's catalogue")
    text = DOC.read_text(encoding="utf-8")
    client = BoundedOllama(model=a.model)
    summary = []
    for target, why in CLAUSES:
        ctx = c.post("/api/interpreter/context", json={"document": DOC.name, "text": text, "target": target}).json()
        clause = next(x for x in ctx["clauses"] if x["id"] == target)
        body = clause["text"].split(":", 1)[-1].strip()
        say(f"\n      {target}  ({why})")
        say(f"      \"{body}\"")
        item = Item(id="walk", family="real", lang="en", text=body, program={}, catalogue=cat)
        d = draft_arm("expr_verify", item, client)
        say(f"      draft: {d.stage}{' after one repair' if d.repaired else ''} in {d.seconds:.0f}s")
        status, reason = clause_status(d)
        if status != "DRAFTED":
            say(f"      {status}: {reason}")
            summary.append((target, status, ""))
            continue
        notes = [i.message for i in verify(d.program, body, cat) if not i.blocking]
        say("      sentence check: scope, numbers and comparison directions all match the sentence"
            + (f"  (notes: {notes})" if notes else ""))
        prog = d.program.model_dump(mode="json")
        say(f"      reads as: {explain(prog['requirement'])}")
        if prog["applicability"] != {"node": "literal", "value": True, "unit": "1"}:
            say(f"      applies when: {explain(prog['applicability'])}")
        if prog["unresolved"]:
            say(f"      model says it cannot express: {prog['unresolved']}")
        r = c.post("/api/interpreter/check", json={"program": prog, "inputs": inputs, "preview": True}).json()
        miss = r["trace"]["missing"][:3]
        say(f"      PLAN RESULT (preview, not yet approved): {r['outcome']}" + (f"   missing: {miss}" if miss else ""))
        summary.append((target, r["outcome"], explain(prog["requirement"])[:70]))

    say("\n[6/7] SUMMARY")
    for target, outcome, readback in summary:
        say(f"      {target:<9} {outcome:<16} {readback}")
    say("      A rule is shown only if it passed both the structure checks and the sentence check. 'rejected' means")
    say("      the rule dropped a condition, used a number the sentence does not state, or pointed the wrong way.")
    say("      UNRESOLVED means the clause is not being checked yet. It is never counted as a pass.")

    url = f"{a.url}/#/p/{pid}/results"
    say(f"[7/7] OPEN  {url}")
    if not a.no_browser:
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
