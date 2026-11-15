import json
from pathlib import Path
from reviewpulse.interpreter.schema import Program
from reviewpulse.xeval.synth import read_corpus
from reviewpulse.xeval.semantic import hoist
from reviewpulse.xeval.verify import verify, blocking
items = {i.id: i for i in read_corpus(Path("reports/extractor_eval/corpus.jsonl"))}
fb = 0
for it in items.values():
    ref = Program.model_validate(it.program)
    if blocking(verify(ref, it.text, it.catalogue, it.lang)):
        fb += 1; print("FALSE BLOCK", it.text, [i.message for i in blocking(verify(ref, it.text, it.catalogue, it.lang))][:2])
print("reference rules wrongly blocked:", fb, "/", len(items))
for name in ("vote", "expr2", "expr3"):
    rows = [json.loads(l) for l in open(f"reports/extractor_eval/{name}_rows.jsonl", encoding="utf-8")]
    caught = lost = kept_wrong = 0
    for r in rows:
        if r["stage"] != "ok": continue
        it = items[r["item"]]
        prog = Program.model_validate(hoist(r["program"]) if False else r["program"])
        bad = bool(blocking(verify(prog, it.text, it.catalogue, it.lang)))
        if not r["equivalent"]:
            caught += bad; kept_wrong += not bad
        elif bad:
            lost += 1; print("  RIGHT RULE BLOCKED", it.text)
    print(name, "wrong now caught", caught, "still passing", kept_wrong, "right rules newly blocked", lost)
