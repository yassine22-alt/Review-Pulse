"""Real regulation sentences (CODE-ACCORD) against a real plan's catalogue. No reference rules exist, so this measures
what can be measured without them: how many sentences become a checked rule, how many are UNRESOLVED and why, and it
writes every drafted rule next to its sentence so the drafts can be read."""
import csv, json, random, sys
from pathlib import Path
from reviewpulse.factgraph import io as fio
from reviewpulse.factgraph.convert import to_catalogue
from reviewpulse.xeval.arms import draft_arm
from reviewpulse.xeval.demand import quantities
from reviewpulse.xeval.drafters import BoundedOllama
from reviewpulse.xeval.expr_ir import to_text
from reviewpulse.xeval.status import clause_status
from reviewpulse.xeval.synth import Item
from reviewpulse.xeval.verify import verify

SRC = next(Path("../Review-Pulse/reviewpulse/data/raw/code_accord/extracted").glob("*/annotated_data/relations/all.csv"))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
cat = to_catalogue(fio.load("data/app/projects/3ed5d6c47c2a/run/factgraph.json"))
rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
sentences = sorted({r["content"].strip() for r in rows if r["content"].strip() and 20 < len(r["content"]) < 260})
withnum = [s for s in sentences if quantities(s)]
random.Random(7).shuffle(withnum)
client = BoundedOllama()
out = Path("reports/extractor_eval/real_wording.jsonl")
with out.open("w", encoding="utf-8") as fh:
    for k, s in enumerate(withnum[:N]):
        item = Item(id=f"cc{k}", family="real", lang="en", text=s, program={}, catalogue=cat)
        d = draft_arm("expr_verify", item, client)
        status, reason = clause_status(d)
        row = {"sentence": s, "status": status, "reason": reason if status != "DRAFTED" else "", "stage": d.stage}
        if d.program is not None:
            row["rule"] = to_text(d.program.model_dump(mode="json")["requirement"])
            row["when"] = to_text(d.program.model_dump(mode="json")["applicability"])
            row["notes"] = [i.message for i in verify(d.program, s, cat, "en") if not i.blocking]
        fh.write(json.dumps(row, ensure_ascii=False) + "\n"); fh.flush()
        print(k + 1, status, s[:70], flush=True)
