"""Show what the model wrote for one clause of a project's document and why it was or was not accepted."""
import json, sys
from pathlib import Path
from types import SimpleNamespace
from reviewpulse.app.store import Store
from reviewpulse.app import interpret as I
from reviewpulse.interpreter.checked import catalogue_from, clause_body
from reviewpulse.interpreter.context import assemble_context
from reviewpulse.rules.clauses import split_document
from reviewpulse.xeval.arms import draft_arm
from reviewpulse.xeval.drafters import BoundedOllama

pid, cid = sys.argv[1], sys.argv[2]
store = Store("data/app"); p = store.get(pid); path = store.req_path(p)
full, clauses = split_document(path)
ctx = assemble_context(path.name, full, clauses, cid)
graph, inputs, _ = I._plan(store, pid)
cat = catalogue_from(inputs, graph)
item = SimpleNamespace(id=cid, text=clause_body(ctx), catalogue=cat, lang=None, ctx=ctx)
d = draft_arm("expr_verify", item, BoundedOllama())
print("TEXT:", item.text); print("STAGE:", d.stage, "|", d.detail[:400]); print("RAW:", json.dumps(d.raw)[:600])
print("CATALOGUE collections:", {k: v["facts"] for k, v in cat["collections"].items()}, "kinds:", {k: v for k, v in cat["kinds"].items()})
