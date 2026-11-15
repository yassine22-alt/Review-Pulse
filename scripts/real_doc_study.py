"""Read a random sample of clauses of a REAL requirement document through the product, on a plan, and record every answer.

    python scripts/real_doc_study.py <document.pdf|docx|md> [--n 25] [--seed 1] [--scenario 02] [--out reports/real_docs]

Why a sample and not the whole document: a long standard has hundreds of clauses and most of them do not concern a floor
plan (parking, signage, lifts). What matters is (1) what the splitter made of the document, (2) for the clauses the model
reads, whether the rule it wrote says what the sentence says, and (3) whether a clause that cannot be checked from a plan is
said to be unchecked instead of being turned into a wrong rule. The output is a table a person can read and judge; the
judgement is made by reading, there is no annotation.

Clauses are drawn at random among those that contain an obligation word (shall, must, doit, muss ...), so the sample is of
requirements and not of titles. The document is never edited and is never committed (see .gitignore: data/real_docs/).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from reviewpulse.app.api import create_app
from reviewpulse.app.interpret import SKIP_KINDS, _is_title
from reviewpulse.rules.clauses import MODALS, split_document
from reviewpulse.synth.make_plan import make_plan
from reviewpulse.synth.random_plan import random_plan
from reviewpulse.synth.scenarios import SCENARIOS
from reviewpulse.xeval.drafters import BoundedOllama


class Real:
    """The real local model for reading clauses; a canned answer for the older drafter that runs at upload."""

    def __init__(self):
        # REVIEWPULSE_LLM=openai (with the REVIEWPULSE_LLM_* settings or a .env file) reads the clauses with a hosted model
        from reviewpulse.llm import primary_from_env, setting

        hosted = primary_from_env() if setting("REVIEWPULSE_LLM") == "openai" else None
        self.real = hosted or BoundedOllama()
        self.model = getattr(self.real, "model", "qwen2.5:7b")
        self.external = bool(getattr(self.real, "external", False))

    def complete(self, system, user, schema):
        if "CLAUSE_JSON:" in user:
            return {"property": "fire_resistance", "subject": "room", "room_types": [], "avoid_room_types": [],
                    "forbidden_pairs": [], "comparison": "no_number", "number": None, "unit_written": "none",
                    "severity": "major", "title": "x",
                    "rase": {"requirement": [], "applicability": [], "selection": [], "exception": []}}
        return self.real.complete(system, user, schema)


def wait(c, pid, job):
    while True:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            assert rec["status"] == "done", rec.get("error")
            return
        time.sleep(0.3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("document")
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--scenario", default="02")
    ap.add_argument("--ids", default="", help="comma separated clause ids to read instead of a random sample")
    ap.add_argument("--out", default="reports/real_docs")
    args = ap.parse_args()
    doc = Path(args.document)
    full, clauses = split_document(doc)
    pool = [c for c in clauses if c.kind not in SKIP_KINDS and len(c.text.strip()) > 15 and not _is_title(c)
            and MODALS.search(c.text)]
    random.Random(args.seed).shuffle(pool)
    sample = sorted(pool[: args.n], key=lambda c: c.start)
    if args.ids:                                  # a chosen set: the clauses a plan could decide
        want = [x.strip() for x in args.ids.split(",") if x.strip()]
        by_id = {c.id: c for c in clauses}
        sample = [by_id[x] for x in want if x in by_id]
    name, kind, kw, _ = next(s for s in SCENARIOS if s[0].startswith(args.scenario))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    llm = Real()
    with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp) / "data", llm=lambda: llm, workers=1)) as c:
        paths = make_plan(Path(tmp) / name, png=False, **kw) if kind == "make" else random_plan(Path(tmp) / name, **kw)
        pid = c.post("/api/projects", json={"name": doc.stem, "curator": "study"}).json()["id"]
        with open(paths["dxf"], "rb") as f:
            wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": ("plan.dxf", f)}).json())
        t0 = time.time()
        with open(doc, "rb") as f:
            wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": (doc.name, f)}).json())
        shown = c.get(f"/api/projects/{pid}/document").json()
        print(f"{doc.name}: {len(clauses)} clauses split, {len(shown['clauses'])} offered for reading, "
              f"{len(pool)} with an obligation word; upload took {time.time() - t0:.0f}s; reading {len(sample)}", flush=True)
        for k, cl in enumerate(sample, 1):
            t1 = time.time()
            r = c.post(f"/api/projects/{pid}/interpret/{cl.id}").json()
            row = {"id": cl.id, "kind": cl.kind, "text": re.sub(r"\s+", " ", cl.text)[:400], "status": r.get("status"),
                   "reason": r.get("reason"), "plain": r.get("plain"), "readback": r.get("readback"),
                   "notes": r.get("notes"), "tried": r.get("tried"), "seconds": round(time.time() - t1, 1), "preview": r.get("preview")}
            rows.append(row)
            print(f"  {k:>2}/{len(sample)} {cl.id[:22]:<22} {row['status']:<10} {row['seconds']:>5}s  "
                  f"{(row['plain'] or row['reason'] or '')[:90]}", flush=True)
    (out / f"{doc.stem}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    drafted = sum(r["status"] == "DRAFTED" for r in rows)
    print(f"\n{doc.name}: {drafted} of {len(rows)} read clauses became a checked rule; "
          f"the rest were reported as not checkable, with a reason. Details: {out / (doc.stem + '.jsonl')}")


if __name__ == "__main__":
    main()
