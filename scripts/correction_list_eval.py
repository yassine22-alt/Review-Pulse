"""Run a REAL public correction list (a canned list a plan reviewer circles) through ReviewPulse and measure what happens to every item.

    python scripts/correction_list_eval.py items    --doc data/real_docs/us_oc_crc_correction_list.pdf --out reports/correction_lists/oc
    python scripts/correction_list_eval.py run      --doc ... --out ...            # the product's read of every item, on the benchmark plan
    python scripts/correction_list_eval.py evidence --doc ... --out ... --plans data/real_plans/a.pdf data/real_plans/b.pdf
    python scripts/correction_list_eval.py summary  --doc ... --out ...

items     split the document with the product's splitter and describe every item without a model: its id, the code section in
          brackets (the citation), blanks and choices a reviewer fills in, whether it is conditional, a figure, and the kind of work a
          reviewer does with it (presence on the plan, numeric limit, calculation, administrative, other).
run       every item the app would read ("read all": triage first, then the arms) on the generated benchmark plan (scenario 01 with a
          block of general notes) with the local model. Resumable: rows already in rows.jsonl are kept.
evidence  for every item no measured rule was written for, the note of the real drawing sets that is about it, as the app does
          (interpreter/drawing_evidence.py), with its sheet and words.
summary   outcome per item and the share handled per kind of item; writes summary.json and summary.md.

Documents, drawings and reports are never committed (data/real_* is ignored; reports hold document text).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ---- describing an item, with no model -------------------------------------------------------------------------------------------

BRACKET = re.compile(r"\[([^\[\]]{2,80})\]")
TAIL_CODE = re.compile(r"(?:^|[\s.])((?:\d{3,4}(?:\.\d+)*|R\d{3}(?:\.\d+)*|11[AB]-\d+(?:\.\d+)*|\d{1,2}\.\d{2}[A-Z]?\d*(?:\([\w]+\))*\d*)"
                       r"(?:\s*[,&]\s*(?:Table\s+)?[A-Z]?\d[\w.()]*)*)\s*$")
BLANKS = re.compile(r"_{3,}|\(\s{3,}\)|\(\s*\)|☐")
CHOICES = re.compile(r"☐|\([^()]{1,24}\)\s*\([^()]{1,24}\)")
CONDITION = re.compile(r"\b(if|where|when|unless|whenever|provided that|in case|in the event|applicable|as applicable|exceed[s]?|"
                       r"only when|for new|for existing)\b", re.I)
PRESENCE = re.compile(r"^\W*(?:[A-Z]{0,2}\d{0,3}\.?\s*)?(?:revise\s+(?:\w+\s+){0,3}?to\s+)?(?:show|provide|indicate|note|add|specify|label|identify|"
                      r"detail|include|list|dimension|clearly indicate|key in|call out|submit plans? showing|demonstrate)\b", re.I)
PRESENCE_ANY = re.compile(r"\b(on (?:the )?(?:plans?|plan|cover sheet|first sheet|title sheet|sheet|all sheets|site plan|floor plan|elevations?)|"
                          r"show on|shown on|indicate on|note on|add notes?|details? (?:on|at|of)|revise (?:the )?(?:plans?|sheet|site plan))\b", re.I)
ADMIN = re.compile(r"\b(fees?|valuation|permit application|application|affidavit|forms?|expire[sd]?|expiration|extension|"
                   r"clearances?|sign-?off|recorded|notariz\w*|insurance|owner-builder|copy of|copies of|sets? of plans|"
                   r"stamped|special inspection|appointment|submit (?:\d+|three|two) sets|resubmi\w+|pay|receipt|letter|bulletin|disclosure|signed|"
                   r"separate application|grading permit|geotechnical report|contact (?:the )?\w+)\b", re.I)
CALC = re.compile(r"\b(calculations?|analysis|equation|compute[sd]?|energy (?:compliance|certificate|calculations?)|compliance documents?|"
                  r"certificate of compliance|CF1R|design(?:ed)? by)\b", re.I)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s*(?:[-–]?\s*\d+/\d+)?\s*(?:\"|”|'|’|in\b|inch(?:es)?|ft\b|feet|foot|sf\b|sq\.?\s*ft|square|%|percent|hr\b|"
                    r"hour|min\b|minutes?|psi|plf|pcf|degrees|°|mil\b|gage|gauge|:12|:1\b|btu|v\b|volts?|amps?)|\bR-?\d{1,2}\b|\d+/\d+", re.I)
LIMIT_WORD = re.compile(r"\b(min(?:imum)?|max(?:imum)?|not less than|no less than|at least|not more than|not exceed|no more than|"
                        r"less than|closer than|greater than|more than|limited to|up to|between|within|shall be (?:at least|\d)|no greater than)\b", re.I)
SITE = re.compile(r"\b(property line|lot line|setback|set back|grade plane|finish(?:ed)? grade|slope|drainage|sewer|manhole|utilities|utility (?:lines?|poles?|meters?|supply)|easement|"
                  r"street|alley|sidewalk|curb|zoning|hillside|hydrant|fire lane|parking|driveway|yard|"
                  r"neighbou?r|parcel|tract|topograph\w*|survey)\b", re.I)


def citation(text: str) -> str | None:
    """The code section a reviewer cites for the item: the last bracketed reference, else a bare section number at the end."""
    flat = " ".join(text.replace("\xa0", " ").split())
    found = BRACKET.findall(flat)
    codes = [b for b in found if re.search(r"\d", b)]
    if codes:
        return codes[-1]
    m = TAIL_CODE.search(flat)
    return m.group(1).strip() if m else None


def kind_of_work(text: str) -> str:
    """What a reviewer does with the item: presence (put it on the plans), limit (a number a drawing must meet), calculation,
    administrative (fees, forms, expiry, paperwork) or other (a statement of a requirement or something that needs site knowledge).
    The rules are keyword rules written before looking at any result; the class is then read by hand on a sample (M23)."""
    flat = " ".join(text.replace("\xa0", " ").split())
    head = flat[:160]
    if ADMIN.search(head) and not PRESENCE.match(flat):
        return "administrative"
    if CALC.search(flat) and re.search(r"\b(provide|submit|attach|include|complete|per|by)\b", flat, re.I) and not NUMBER.search(flat):
        return "calculation"
    if PRESENCE.match(flat) or PRESENCE_ANY.search(flat):
        if NUMBER.search(flat) and LIMIT_WORD.search(flat):
            return "numeric_limit"
        return "presence"
    if NUMBER.search(flat) and LIMIT_WORD.search(flat):
        return "numeric_limit"
    if CALC.search(flat):
        return "calculation"
    if SITE.search(flat):
        return "site_knowledge"
    return "other_statement"


def describe(clause) -> dict:
    flat = " ".join(clause.text.replace("\xa0", " ").split())
    blanks = bool(BLANKS.search(flat))
    return {"id": clause.id, "page": clause.page + 1, "kind": clause.kind, "text": flat, "citation": citation(flat),
            "blanks": blanks, "choices": bool(CHOICES.search(flat)), "conditional_word": bool(CONDITION.search(flat)),
            "conditional": blanks or bool(CHOICES.search(flat)) or bool(CONDITION.search(flat)),
            "has_figure": bool(NUMBER.search(flat)), "work": kind_of_work(flat)}


def app_items(clauses) -> list:
    """The clauses the app reads (the same filter as app/interpret.py `document`): titles, headings and definitions are left out."""
    from reviewpulse.app.interpret import SKIP_KINDS, _is_title

    return [c for c in clauses if c.kind not in SKIP_KINDS and len(c.text.strip()) > 15 and not _is_title(c)]


def outcome_of(row: dict) -> str:
    """One word per item, by priority: measured rule, mention rule, evidence note, question (what it seems to need), declined."""
    if row.get("outcome") == "call_failed":
        return "call_failed"
    if row.get("status") == "DRAFTED":
        return "mention" if row.get("mention") else "measured"
    if row.get("evidence_found"):
        return "evidence"
    if row.get("needs") or row.get("reason_class") == "plan lacks the fact":
        return "question"
    return "declined"


# ---- the phases -------------------------------------------------------------------------------------------------------------------


def split(doc: Path):
    from reviewpulse.rules.clauses import split_cached

    cache = Path(os.environ.get("SPLIT_CACHE", "reports/split_cache_m23")) / doc.stem
    return split_cached(doc, cache)


def cmd_items(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    full, clauses = split(Path(args.doc))
    items = [describe(c) for c in app_items(clauses)]
    (out / "items.jsonl").write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items), encoding="utf-8")
    print(f"{len(clauses)} clauses, {len(items)} read by the app; with a citation {sum(bool(i['citation']) for i in items)}; "
          f"blanks {sum(i['blanks'] for i in items)}; conditional {sum(i['conditional'] for i in items)}; "
          f"work {dict(Counter(i['work'] for i in items))}")


def read_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def cmd_run(args) -> None:
    from checklist_benchmark import call_errors, is_mention, why
    from fastapi.testclient import TestClient
    from real_doc_study import Real, wait

    from reviewpulse.app import interpret as interpretation
    from reviewpulse.app.api import create_app
    from reviewpulse.synth.make_plan import make_plan
    from reviewpulse.synth.notes_block import add_general_notes
    from reviewpulse.synth.random_plan import random_plan
    from reviewpulse.synth.scenarios import SCENARIOS

    doc, out = Path(args.doc), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "rows.jsonl"
    done = {r["id"] for r in read_rows(rows_path)}
    items = {i["id"]: i for i in map(json.loads, (out / "items.jsonl").read_text(encoding="utf-8").splitlines())}
    llm = Real()
    name, kind, kw, _ = next(s for s in SCENARIOS if s[0].startswith(args.scenario))
    with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp) / "data", llm=lambda: llm, workers=1)) as c:
        store = c.app.state.store
        paths = make_plan(Path(tmp) / name, png=False, **kw) if kind == "make" else random_plan(Path(tmp) / name, **kw)
        add_general_notes(paths["dxf"])
        pid = c.post("/api/projects", json={"name": doc.stem, "curator": "m23"}).json()["id"]
        with open(paths["dxf"], "rb") as f:
            wait(c, pid, c.post(f"/api/projects/{pid}/plan", files={"file": ("plan.dxf", f)}).json())
        with open(doc, "rb") as f:
            wait(c, pid, c.post(f"/api/projects/{pid}/requirements", files={"file": (doc.name, f)}).json())
        todo = [c_["id"] for c_ in interpretation.document(store, pid)["clauses"]]
        print(f"{len(todo)} items to read, {len(done)} already done; model {llm.model}", flush=True)
        for cid in todo:
            if cid in done:
                continue
            t0, before = time.time(), call_errors(llm)
            try:
                r = interpretation.interpret_clause(store, pid, cid, lambda: llm, None, triage=True)
            except ValueError as e:                  # the app refuses (a changed document): keep going, the item is read again next time
                print(f"  {cid}: {e}", flush=True)
                continue
            broken = call_errors(llm) - before
            if r.get("status") != "DRAFTED" and "could not be reached" in (r.get("reason") or ""):
                broken = max(broken, 1)
            ev = r.get("evidence") or {}
            row = {"id": cid, "status": r.get("status"), "arm": r.get("arm"), "mention": bool(r.get("status") == "DRAFTED" and is_mention(r)),
                   "outcome": "call_failed" if broken and r.get("status") != "DRAFTED" else None,
                   "reason": r.get("reason"), "reason_class": why(r.get("reason")), "needs": r.get("needs"),
                   "readback": r.get("readback"), "plain": r.get("plain"), "applies_when": r.get("applies_when"), "unless": r.get("unless"),
                   "tried": r.get("tried"), "notes": r.get("notes"),
                   "not_checked": (r.get("program") or {}).get("not_checked") if r.get("program") else None,
                   "app_evidence": bool(ev.get("chosen")), "text": items.get(cid, {}).get("text", "")[:400],
                   "seconds": round(time.time() - t0, 1)}
            with rows_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"  {cid[:28]:<28} {str(r.get('status')):<10} {str(r.get('arm')):<12} {(row['readback'] or row['reason'] or '')[:70]}", flush=True)


def cmd_evidence(args) -> None:
    from evidence_eval import pdf_passages
    from real_doc_study import Real

    from reviewpulse.interpreter import drawing_evidence as ev

    out = Path(args.out)
    passages = [p for plan in args.plans for p in pdf_passages(Path(plan))]
    llm, embedder, reranker = Real(), ev.default_embedder(), ev.default_reranker()
    print(f"{len(passages)} passages; embedder {getattr(embedder, 'model', None)}; cross-encoder {'on' if reranker else 'off'}", flush=True)
    rows = read_rows(out / "rows.jsonl")
    items = {i["id"]: i for i in map(json.loads, (out / "items.jsonl").read_text(encoding="utf-8").splitlines())}
    path = out / "evidence.jsonl"
    done = {r["id"] for r in read_rows(path)}
    for r in rows:
        if r["id"] in done or r["status"] == "DRAFTED" and not r["mention"]:
            continue                               # the app looks for a note only when no measured rule was written
        body = items[r["id"]]["text"]
        t0 = time.time()
        try:
            found = ev.find_evidence(body, passages, llm, embedder, reranker)
        except Exception as e:  # noqa: BLE001
            print(f"  {r['id']}: {e}", flush=True)
            continue
        row = {"id": r["id"], "chosen": found.chosen, "checks": found.checks, "summary": found.summary,
               "candidates": [c for c in found.candidates[:3]], "seconds": round(time.time() - t0, 1)}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  {r['id'][:28]:<28} {'FOUND' if found.chosen else '-':<6} {(found.chosen or {}).get('text', '')[:80]}", flush=True)


def cmd_summary(args) -> None:
    out = Path(args.out)
    items = [json.loads(x) for x in (out / "items.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = {r["id"]: r for r in read_rows(out / "rows.jsonl")}
    evid = {r["id"]: r for r in read_rows(out / "evidence.jsonl")}
    table, per = [], defaultdict(Counter)
    for it in items:
        r = rows.get(it["id"])
        if r is None:
            continue
        r = {**r, "evidence_found": bool((evid.get(it["id"]) or {}).get("chosen"))}
        o = outcome_of(r)
        table.append({**it, "outcome": o, "status": r["status"], "readback": r["readback"], "reason": r["reason"],
                      "evidence": (evid.get(it["id"]) or {}).get("chosen")})
        per[it["work"]][o] += 1
    n = len(table)
    total = Counter(t["outcome"] for t in table)
    summ = {"items": n, "outcomes": dict(total), "by_work": {k: dict(v) for k, v in per.items()},
            "work_share": {k: round(sum(v.values()) / n, 3) for k, v in per.items()} if n else {},
            "with_citation": sum(bool(t["citation"]) for t in table), "blanks": sum(t["blanks"] for t in table),
            "conditional": sum(t["conditional"] for t in table), "has_figure": sum(t["has_figure"] for t in table)}
    (out / "results.jsonl").write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in table), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["items", "run", "evidence", "summary"])
    ap.add_argument("--doc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenario", default="01")
    ap.add_argument("--plans", nargs="*", default=[])
    args = ap.parse_args()
    {"items": cmd_items, "run": cmd_run, "evidence": cmd_evidence, "summary": cmd_summary}[args.phase](args)


if __name__ == "__main__":
    main()
