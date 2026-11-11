"""Variant plans through the whole loop: the approved rules must report the same elements as the validated engine.

Each scenario is a different plan (planted errors, page rotation, scale, drawing style, layout). A scripted model writes
the rule for each clause, so the test needs no Ollama and checks what the CODE does with a rule once it is written:
facts, evaluation, findings, report. The older engine is the reference, as in the planted-error measurement with the
real model.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402
from reviewpulse.synth.random_plan import random_plan  # noqa: E402
from reviewpulse.synth.scenarios import SCENARIOS  # noqa: E402

DOC = Path(__file__).parents[2] / "docs" / "requirements_example.md"
HAB = "r.room_type == 'bedroom' or r.room_type == 'living' or r.room_type == 'kitchen'"
# clause -> (rule as one line, quote from the clause, the older engine's rules for the same requirement)
RULES = {
    "Art. 1": ("building.links_to_exit >= 1", "Every dwelling has at least one exit door to the outside", ["C-C1"]),
    "Art. 2": (f"forall rooms r where {HAB}: reaches(r, EXIT, avoiding 'bathroom', 'wc', 'bedroom')",
               "reaches an exit without passing through a bathroom, a WC or a bedroom other than itself", ["C-T1"]),
    "Art. 2.1": ("forall rooms r: r.links_passable >= 1", "Every enclosed room has at least one door or opening", ["P-6"]),
    "Art. 3": ("forall rooms r where r.room_type == 'bedroom': reaches(r, EXIT, avoiding 'bedroom')",
               "A bedroom is not reached only through another bedroom", ["C-T2"]),
    "Art. 4": ("forall rooms a where a.room_type == 'garage': forall rooms b where b.room_type == 'bedroom': "
               "not linked(a, b)", "No door or opening connects a garage directly to a bedroom", ["C-T3"]),
    "Art. 6.1": ("forall doors d: d.width_m >= 0.8 m", "Every door has a clear width of at least 0.80 m", ["C-D1"]),
    "Art. 6.3": ("forall rooms r where r.room_type == 'bedroom': r.area_m2 >= 9 m2 and r.min_width_m >= 2.2 m",
                 "A bedroom has a floor area of at least 9.00 m² and a minimum width of at least 2.20 m", ["C-D3", "C-D3W"]),
    "Art. 6.4": ("forall rooms r where r.room_type == 'living': r.area_m2 >= 14 m2",
                 "A living room has a floor area of at least 14.00 m²", ["C-D3L"]),
    "Art. 8": (f"forall rooms r where {HAB}: r.exit_distance_m <= 15 m",
               "the travel distance to an exit is at most 15 m", ["C-T5"]),
}


class Scripted:
    model = "scripted"

    def complete(self, system, user, schema):
        props = schema.get("properties", {})
        if "CLAUSE_JSON:" in user:
            return {"property": "fire_resistance", "subject": "room", "room_types": [], "avoid_room_types": [],
                    "forbidden_pairs": [], "comparison": "no_number", "number": None, "unit_written": "none",
                    "severity": "major", "title": "x", "rase": {"requirement": [], "applicability": [],
                                                                "selection": [], "exception": []}}
        if "issues" in props:
            return {"issues": [], "limitations": []}
        clause = json.loads(user)["target"]
        require, quote, _ = RULES[clause]
        return {"title": clause, "applies_when": None, "unless": None, "require": require,
                "sources": [{"clause": clause, "quote": quote}], "unresolved": []}


def wait(c, pid, job):
    t0 = time.time()
    while time.time() - t0 < 300:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            assert rec["status"] == "done", rec.get("error")
            return
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def run_scenario(tmp_path, kind, kw):
    paths = make_plan(tmp_path / "plan", png=False, **kw) if kind == "make" else random_plan(tmp_path / "plan", **kw)
    with TestClient(create_app(tmp_path / "data", llm=lambda: Scripted(), workers=1)) as c:
        pid = c.post("/api/projects", json={"name": "s", "curator": "t"}).json()["id"]
        with open(paths["dxf"], "rb") as f:
            wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": ("plan.dxf", f)}).json())
        with open(DOC, "rb") as f:
            wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": ("req.md", f)}).json())
        status = {}
        for clause in RULES:
            status[clause] = c.post(f"/api/projects/{pid}/interpret/{clause}").json()["status"]
            if status[clause] == "DRAFTED":
                c.post(f"/api/projects/{pid}/decision", json={"clause": clause, "action": "approve", "reviewer": "t"})
        c.patch(f"/api/projects/{pid}", json={"inventory_reviewed": True})
        wait(c, pid, c.post(f"/api/projects/{pid}/check").json())
        findings = c.get(f"/api/projects/{pid}/findings").json()["findings"]
        coverage = c.get(f"/api/projects/{pid}/coverage").json()
    return status, findings, coverage


def compare(status, findings):
    """Per clause: the elements the approved rule reports against the elements the older engine reports."""
    problems = []
    for clause, (_, _, old_ids) in RULES.items():
        if status[clause] != "DRAFTED":
            problems.append(f"{clause}: no rule ({status[clause]})")
            continue
        old = {s for f in findings if f["rule_id"] in old_ids and f["verdict"] == "FAIL" for s in f["subject_ids"]}
        old_any = any(f["rule_id"] in old_ids and f["verdict"] == "FAIL" for f in findings)
        rid = "I-" + clause.replace(" ", "_")
        new = {s for f in findings if f["rule_id"] == rid and f["verdict"] == "FAIL" for s in f["subject_ids"]}
        new_any = any(f["rule_id"] == rid and f["verdict"] == "FAIL" for f in findings)
        if old_any != new_any:
            problems.append(f"{clause}: engine {'fails' if old_any else 'passes'}, approved rule {'fails' if new_any else 'passes'}")
        elif old and new and not new <= old:
            # the engine's route and link findings also name the rooms in the way, so the rule's failing rooms must be
            # among its subjects, never outside them
            problems.append(f"{clause}: engine reports {sorted(old)}, approved rule {sorted(new)}")
    return problems


FAST = {"01_clean", "02_door_too_narrow", "04_bedroom_through_bathroom", "10_rotated_other_scale"}


@pytest.mark.parametrize("scenario", [pytest.param(s, id=s[0], marks=[] if s[0] in FAST else [pytest.mark.slow])
                                      for s in SCENARIOS])
def test_the_approved_rules_agree_with_the_validated_engine(tmp_path, scenario):
    name, kind, kw, _ = scenario
    status, findings, coverage = run_scenario(tmp_path, kind, kw)
    problems = compare(status, findings)
    assert not problems, f"{name}: " + "; ".join(problems)
    # the report accounts for every clause of the document, whatever the plan
    assert coverage["summary"]["clauses"] == len(coverage["clauses"]) == 24
    assert coverage["summary"]["counts"]["not_read"] == 24 - len(RULES)
