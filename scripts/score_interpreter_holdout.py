"""Evaluate frozen human ratings and actual model outputs without changing checker code."""
import argparse
import json
from collections import Counter
from pathlib import Path

from real_interpreter_holdout import access_graph, clause_context, fire_inputs, read, sources

from reviewpulse.factgraph.convert import to_graph, to_inputs
from reviewpulse.interpreter.review import ReviewArtifact, approve_program, review_fingerprint
from reviewpulse.interpreter.runtime import run_program
from reviewpulse.interpreter.schema import Program

DECIDED = {"SATISFIED", "VIOLATED"}


def approve(draft, context, inputs):
    if draft.get("status") != "DRAFTED" or not draft.get("program"):
        return None, draft.get("reason") or "no draft"
    program = Program.model_validate(draft["program"])
    report = ReviewArtifact(review={"issues": [], "limitations": []}, model="scripted benchmark reviewer",
                            fingerprint=review_fingerprint(program, context, inputs))
    try:
        return approve_program(program, context, inputs, report, "benchmark reviewer"), None
    except ValueError as error:
        return None, f"Approval refused: {error}"


def execute(draft, context, inputs, graph=None):
    program, why = approve(draft, context, inputs)
    if program is None:
        return "UNRESOLVED", [why]
    result = run_program(program, inputs, graph=graph)
    return result["outcome"], result["trace"]["missing"]


def totals(rows):
    out = Counter(row["outcome"] for row in rows)
    fp = sum(row["outcome"] == "SATISFIED" and row["gold"] == "VIOLATED" for row in rows)
    tp = sum(row["outcome"] == row["gold"] == "VIOLATED" for row in rows)
    return {"applicable": len(rows), "decided": sum(out[k] for k in DECIDED),
            "pass": out["SATISFIED"], "violated": out["VIOLATED"], "unresolved": out["UNRESOLVED"],
            "false_passes": fp, "confirmed_violation_precision": [tp, out["VIOLATED"]],
            "lost_manual_decisions": sum(row.get("manual") in DECIDED and row["outcome"] == "UNRESOLVED"
                                         for row in rows),
            "changed_manual_decisions": sum(row.get("manual") in DECIDED and row["outcome"] in DECIDED
                                             and row["manual"] != row["outcome"] for row in rows),
            "wrong_decisions": sum(row["outcome"] in DECIDED and row["outcome"] != row["gold"] for row in rows)}


def fire_run(labels, drafts, ratings, manual, contexts, reviewed, mode):
    results = []
    field = "reviewed" if reviewed else "automatic"
    for i, (key, plan) in enumerate(labels["plans"].items()):
        inputs = fire_inputs(plan, reviewed=reviewed)
        for clause in labels["clauses"]:
            cid = clause["id"]
            rating = ratings[cid]["rating"]
            if mode == "match_only" and rating != "matches":
                outcome, missing = "UNRESOLVED", [f"reviewer withheld approval: {rating}"]
            else:
                outcome, missing = execute(drafts[cid], contexts[cid], inputs)
            gold = {"PASS": "SATISFIED", "FAIL": "VIOLATED"}[clause["truth"][i]]
            results.append({"plan": key, "id": cid, "outcome": outcome, "gold": gold, "missing": missing,
                            "manual": manual[key, cid][field]["outcome"]})
    return {"metrics": totals(results), "cases": results}


def draft_metrics(ids, drafts, ratings, contexts, inputs):
    presented = [cid for cid in ids if drafts[cid]["status"] == "DRAFTED" and drafts[cid].get("program")]
    approvable = [cid for cid in presented if approve(drafts[cid], contexts[cid], inputs)[0] is not None]
    unflagged = [cid for cid in presented if not drafts[cid].get("notes")]
    counts = Counter(ratings[cid]["rating"] for cid in ids)
    return {"ratings": dict(counts), "presented": len(presented), "approvable": len(approvable),
            "wrong_presented": [sum(ratings[cid]["rating"] == "wrong" for cid in presented), len(presented)],
            "wrong_unflagged": [sum(ratings[cid]["rating"] == "wrong" for cid in unflagged), len(unflagged)],
            "wrong_approvable": [sum(ratings[cid]["rating"] == "wrong" for cid in approvable), len(approvable)],
            "wrong_or_partial_approvable": [
                sum(ratings[cid]["rating"] in {"wrong", "partly matches"} for cid in approvable), len(approvable)
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo", "access_text", "drafts", "ratings", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    reports = args.repo / "reports"
    fire, access = (read(reports / f"{name}-holdout-labels.json") for name in ("morocco", "accessibility"))
    manual = {(row["plan"], row["clause"]): row for row in read(reports / "morocco-holdout-after.json")["cases"]}
    drafts = {row["id"]: row for row in map(json.loads, args.drafts.read_text(encoding="utf-8").splitlines())}
    ratings = read(args.ratings)
    manifest, items = sources(args.repo, args.access_text)
    contexts = {cid: clause_context(manifest, items, suite, cid) for suite in items for cid in items[suite]}
    access_facts = access_graph(access)
    observed = {"fire": fire_inputs(fire["plans"]["A"]), "access": to_inputs(access_facts)}
    result = {}
    for key, labels in (("fire", fire), ("access", access)):
        ids = [clause["id"] for clause in labels["clauses"]]
        result[key] = {"drafting": draft_metrics(ids, drafts, ratings, contexts, observed[key]), "interpretations": [
            {"id": c["id"], "ref": c["ref"], "frozen": c["meaning"], **ratings[c["id"]],
             "draft": drafts[c["id"]].get("readback"), "applies_when": drafts[c["id"]].get("applies_when"),
             "unless": drafts[c["id"]].get("unless"), "reason": drafts[c["id"]].get("reason")}
            for c in labels["clauses"]
        ]}
    result["fire"]["execution"] = {
        f"{mode}_{stage}": fire_run(fire, drafts, ratings, manual, contexts, stage == "reviewed", mode)
        for mode in ("match_only", "as_is") for stage in ("automatic", "reviewed")
    }
    inputs, routes = observed["access"], to_graph(access_facts)
    rows = []
    for clause in access["clauses"]:
        cid = clause["id"]
        verdict, missing = execute(drafts[cid], contexts[cid], inputs, routes)
        rows.append({"id": cid, "outcome": verdict, "gold": clause["truth"], "missing": missing,
                     "blocker": ratings[cid].get("blocker", clause["blocker"]) if verdict == "UNRESOLVED" else None})
    result["access"]["execution"] = {"metrics": totals(rows), "cases": rows, "unresolved_by_blocker":
                                     dict(Counter(row["blocker"] for row in rows if row["blocker"]))}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
