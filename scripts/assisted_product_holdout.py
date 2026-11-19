"""One frozen assisted-product run. Source-only model calls; gold stays in grading."""
import argparse
import json
import subprocess
from pathlib import Path

from real_interpreter_holdout import bundle

from reviewpulse.factgraph.convert import to_inputs
from reviewpulse.factgraph.from_building import from_building
from reviewpulse.interpreter.assisted import assisted_draft
from reviewpulse.interpreter.checked import catalogue_from
from reviewpulse.llm.openai_compat import OpenAICompatClient
from reviewpulse.schema import BuildingModel


def ratio_pass(numerator, denominator, minimum):
    return denominator > 0 and numerator / denominator >= minimum


def summarize(report, scopes, grades):
    rows=report["rows"]
    in_scope=[r for r in rows if scopes[r["id"]]["in_scope"]]
    out_scope=[r for r in rows if not scopes[r["id"]]["in_scope"]]
    low=sum(grades.get(r["id"],{}).get("edit_bucket") in ("0","1") and grades.get(r["id"],{}).get("source_correct") is True for r in in_scope)
    candidates=[r for r in rows if r["result"].get("program")]
    reviewed=[r for r in candidates if r["id"] in grades]
    wrong=[r for r in reviewed if grades[r["id"]].get("source_correct") is not True]
    queued=sum(not r["result"].get("program") for r in out_scope)
    report["criteria_results"]={
        "in_scope_at_most_one_edit":{"count":[low,len(in_scope)],"minimum_share":.8,"pass":ratio_pass(low,len(in_scope),.8)},
        "source_wrong_validator_approvable":{"count":[len(wrong),len(reviewed)],"pass":len(reviewed)>0 and not wrong and len(reviewed)==len(candidates)},
        "out_of_scope_correctly_queued":{"count":[queued,len(out_scope)],"minimum_share":.9,"pass":ratio_pass(queued,len(out_scope),.9)}}
    report["grading_limits"]="Assistant-authored frozen labels and scope annotation; no independent review. No outputs are not semantic correctness. Zero in-scope/candidate denominators are unmeasured and do not pass. No plan-verdict accuracy or observed human effort is measured here."
    for row in rows:
        row["reference_scope"]=scopes[row["id"]]
        row["assistant_grade"]=grades.get(row["id"],{"status":"NO_DRAFT_TO_GRADE" if not row["result"].get("program") else "PENDING"})
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("labels",type=Path)
    parser.add_argument("scope_labels",type=Path)
    parser.add_argument("building",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--freeze",required=True)
    parser.add_argument("--grades",type=Path)
    parser.add_argument("--summarize-only",action="store_true")
    args=parser.parse_args()
    scopes=json.loads(args.scope_labels.read_text(encoding="utf-8"))["labels"]
    grades=json.loads(args.grades.read_text(encoding="utf-8")) if args.grades else {}
    if args.summarize_only:
        report=json.loads(args.output.read_text(encoding="utf-8"))
    else:
        dirty=subprocess.check_output(["git","diff","--name-only",args.freeze,"--","src","scripts/assisted_product_holdout.py"],text=True)
        if dirty.strip():
            raise SystemExit("Frozen pipeline differs; do not run the held-out document")
        if args.output.exists():
            raise SystemExit("Run artifact already exists; use --summarize-only, never rerun inference")
        source=json.loads(args.source.read_text(encoding="utf-8"))
        labels={r["id"]:r for r in json.loads(args.labels.read_text(encoding="utf-8"))["clauses"]}
        model=BuildingModel.model_validate_json(args.building.read_text(encoding="utf-8"))
        graph=from_building(model,complete=False)
        catalogue=catalogue_from(to_inputs(graph),graph)
        client=OpenAICompatClient.from_env("https://api.groq.com/openai/v1","GROQ_API_KEY_Reviewpulse","openai/gpt-oss-120b",
            provider="groq",structured="json_schema",seed=None,max_tokens=256,max_retries=2,rpm=10,tpm=8000)
        report={"pipeline_commit":args.freeze,"status":"STARTED","source_document":source["document"],
            "publication":source["publication"],"source_url":source["source"],"model":client.model,"rows":[]}
        args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        context_texts={"general_scope":source["general_scope_text"],**source["source_contexts"]}
        for row in source["clauses"]:
            context=bundle(source["document"],row["id"],row["text"],context_texts)
            result=assisted_draft(context,catalogue,client)
            report["rows"].append({"id":row["id"],"source":row["text"],"result":result,
                "frozen_interpretation":labels[row["id"]]["interpretation"],
                "frozen_applicability":labels[row["id"]]["applicability_and_exception_facts"]})
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        report.update(status="COMPLETED",http_events=client.events,actual_calls=len(client.events))
    report=summarize(report,scopes,grades)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("pipeline_commit","status","actual_calls","criteria_results")}))


if __name__=="__main__":
    main()
