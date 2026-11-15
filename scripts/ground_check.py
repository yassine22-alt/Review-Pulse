import json, random
from pathlib import Path
from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.drafters import BoundedOllama
from reviewpulse.xeval.grounding import check_grounding, measured_facts
from reviewpulse.xeval.synth import read_corpus
from reviewpulse.xeval.expr_arms import draft_expr
from reviewpulse.xeval.synth import Item
from reviewpulse.factgraph import io as fio
from reviewpulse.factgraph.convert import to_catalogue
c = BoundedOllama()
items = read_corpus(Path("reports/extractor_eval/corpus.jsonl"))
random.Random(3).shuffle(items)
blocked = 0
sample = items[:80]
for it in sample:
    iss = check_grounding(Program.model_validate(it.program), it.text, it.catalogue, c)
    if iss:
        blocked += 1; print("FALSE BLOCK", it.text[:90], "|", iss[0].message[:140], flush=True)
print(f"reference rules wrongly blocked: {blocked}/{len(sample)}", flush=True)
cat = to_catalogue(fio.load("data/app/projects/3ed5d6c47c2a/run/factgraph.json"))
caught = 0
for r in [json.loads(l) for l in open("reports/extractor_eval/real_wording.jsonl", encoding="utf-8")]:
    if r["status"] != "DRAFTED": continue
    d = draft_expr("expr_verify", Item(id="x", family="real", lang="en", text=r["sentence"], program={}, catalogue=cat), c)
    iss = check_grounding(d.program, r["sentence"], cat, c) if d.program else []
    caught += bool(iss)
    print("wrong real rule caught:", bool(iss), "|", r["sentence"][:60], "|", [i.message[:100] for i in iss], flush=True)
print(f"wrong real rules caught: {caught}/4")
