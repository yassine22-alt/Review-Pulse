"""Operations behind the API. Each one is a thin composition of pipeline.py, rules/ and report/."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path

import yaml

from .. import pipeline
from ..rules.draft import OllamaClient, load_drafts, make_client
from ..schema import BuildingModel, load, load_findings
from .jobs import Job
from .store import Project, Store, now

PACKS_ROOT = Path(__file__).resolve().parents[1] / "rules" / "packs"


# -- rule packs ----------------------------------------------------------------
def base_packs() -> list[dict]:
    out = []
    for d in sorted(p for p in PACKS_ROOT.iterdir() if p.is_dir()):
        rules = pipeline.load_packs(d)
        out.append({"name": d.name, "rules": len(rules),
                    "docs": sorted({(r.source.doc or "") for r in rules if r.source and r.source.doc})})
    return out


def packs_for(store: Store, p: Project) -> list[Path]:
    packs = []
    if p.base_pack:
        base = PACKS_ROOT / p.base_pack
        if not base.is_dir() or base.parent != PACKS_ROOT:
            raise ValueError(f"unknown base pack {p.base_pack!r}")
        packs.append(base)
    own = store.pack_dir(p.id)
    if any(own.glob("*.yaml")):
        packs.append(own)
    return packs


def rules_summary(store: Store, p: Project) -> dict:
    packs = packs_for(store, p)
    rules = pipeline.load_packs(packs) if packs else []
    own = {f.stem for f in store.pack_dir(p.id).glob("*.yaml")}
    from . import interpret

    return {"total": len(rules), "approved": sum(r.status == "approved" for r in rules),
            "project": len(own), "base_pack": p.base_pack,
            "interpreted_approved": len(interpret.approved_programs(store, p.id))}


# -- LLM -------------------------------------------------------------------------
def default_llm() -> object | None:
    """The configured drafting model, or None when it is not reachable (drafting then degrades to
    clauses only: the curator writes or edits rules by hand, and the base pack still applies)."""
    backend = os.environ.get("REVIEWPULSE_LLM", "ollama")
    if backend == "none":
        return None
    try:
        client = make_client(backend, os.environ.get("REVIEWPULSE_LLM_MODEL") or None)
    except ImportError:
        return None
    if isinstance(client, OllamaClient) and not client.available():
        return None
    return client


def llm_status(factory: Callable[[], object | None]) -> dict:
    client = factory()
    if client is None:
        return {"available": False, "backend": os.environ.get("REVIEWPULSE_LLM", "ollama"),
                "model": os.environ.get("REVIEWPULSE_LLM_MODEL") or "qwen2.5:7b"}
    return {"available": True, "backend": type(client).__name__.replace("Client", "").lower(),
            "model": getattr(client, "model", "")}


# -- jobs -------------------------------------------------------------------------
def analyse(store: Store, pid: str, job: Job, then_check: bool = True) -> dict:
    """Plan upload -> inspect, extract, build (and check, when the project has rules)."""
    p = store.get(pid)
    plan = store.plan_path(p)
    if plan is None or not plan.exists():
        raise ValueError("upload a plan first")
    run = store.run_dir(pid)
    shutil.rmtree(run, ignore_errors=True)
    job.progress(0.05, "reading the drawing")
    pipeline.inspect(plan, store.dir(pid), run_id="run")
    job.progress(0.15, "extracting geometry and text")
    pipeline.extract(run)
    job.progress(0.40, "detecting walls, openings and rooms")
    pipeline.build(run)
    models = [load(BuildingModel, b) for b in sorted(run.glob("building_*.json"))]
    out = {"sheets": len(models),
           "elements": sum(len(m.elements) for m in models), "rooms": sum(len(m.rooms) for m in models),
           "tiers": [m.tier for m in models]}
    if then_check and packs_for(store, p):
        job.progress(0.80, "checking the rules")
        out["findings"] = check(store, pid, job)["summary"]
    else:
        write_view(run)
    return out


def check(store: Store, pid: str, job: Job | None = None) -> dict:
    p = store.get(pid)
    run = store.run_dir(pid)
    if not any(run.glob("building_*.json")):
        raise ValueError("the plan has not been analysed yet")
    from . import interpret

    packs = packs_for(store, p)
    programs = interpret.approved_programs(store, p.id)
    if not packs and not programs:
        raise ValueError("no rules: approve drafted rules or choose a base pack")
    summary = pipeline.check(run, packs, programs=programs, inventory_complete=p.inventory_reviewed)
    if job:
        job.progress(0.95, "preparing the viewer")
    write_view(run)
    return {"summary": summary, "rules": rules_summary(store, p)}


def draft(store: Store, pid: str, job: Job, llm_factory: Callable[[], object | None]) -> dict:
    """Requirement upload -> clauses (I3) -> drafted rules (I4) with the local model."""
    from ..rules.clauses import write_clauses
    from ..rules.draft import draft_document

    p = store.get(pid)
    doc = store.req_path(p)
    if doc is None or not doc.exists():
        raise ValueError("upload a requirement document first")
    d = store.drafts_dir(pid)
    d.mkdir(parents=True, exist_ok=True)
    job.progress(0.02, "splitting the document into clauses")
    cl = write_clauses(doc, d / "clauses.json")
    n = len(json.loads(cl.read_text(encoding="utf-8"))["clauses"])
    client = llm_factory()
    if client is None:
        return {"clauses": n, "drafted": 0, "llm": "unavailable",
                "note": "the drafting model is not reachable; clauses are listed for manual rules"}

    def progress(done: int, total: int) -> None:
        job.progress(0.05 + 0.95 * done / max(total, 1), f"drafting clause {done + 1} of {total}")

    out = draft_document(doc, client, d, progress=progress)
    drafts = load_drafts(out)
    return {"clauses": n, "drafted": sum(1 for x in drafts if x.rule), "llm": getattr(client, "model", "")}


# -- review queue -----------------------------------------------------------------
def _drafts_file(store: Store, pid: str) -> Path | None:
    files = sorted(store.drafts_dir(pid).glob("*.drafts.yaml"))
    return files[0] if files else None


def _review_file(store: Store, pid: str) -> Path:
    return store.drafts_dir(pid) / "review.json"


def _decisions(store: Store, pid: str) -> dict:
    f = _review_file(store, pid)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _save_decisions(store: Store, pid: str, dec: dict) -> None:
    _review_file(store, pid).write_text(json.dumps(dec, indent=1), encoding="utf-8")


def clauses(store: Store, pid: str) -> list[dict]:
    f = store.drafts_dir(pid) / "clauses.json"
    return json.loads(f.read_text(encoding="utf-8"))["clauses"] if f.exists() else []


def drafts(store: Store, pid: str) -> list[dict]:
    f = _drafts_file(store, pid)
    if f is None:
        return []
    dec = _decisions(store, pid)
    out = []
    for i, d in enumerate(load_drafts(f)):
        rule = dec.get(str(i), {}).get("rule") or d.rule
        out.append({"index": i, "clause_id": d.clause_id, "clause_text": d.clause_text, "checkable": d.checkable,
                    "rationale": d.rationale, "errors": d.errors, "flags": d.flags, "model": d.model,
                    "rule": rule, "rule_yaml": yaml.safe_dump(rule, sort_keys=False, allow_unicode=True) if rule else "",
                    "decision": dec.get(str(i), {"state": "pending"})})
    return out


def approve_draft(store: Store, pid: str, index: int, curator: str, rule_yaml: str | None = None) -> dict:
    from ..rules.review import approve

    p = store.get(pid)
    items = drafts(store, pid)
    if not 0 <= index < len(items):
        raise KeyError(index)
    item = items[index]
    rule = yaml.safe_load(rule_yaml) if rule_yaml else item["rule"]
    if not isinstance(rule, dict):
        raise ValueError("this clause has no rule to approve; write one in the editor first")
    base = pipeline.load_packs(PACKS_ROOT / p.base_pack) if p.base_pack else []
    try:
        ok, msg = approve(rule, store.pack_dir(pid), curator or p.curator or "curator", base)
    except Exception as e:  # noqa: BLE001 - validation errors go back to the curator
        ok, msg = False, f"invalid rule: {e}"
    dec = _decisions(store, pid)
    if ok:
        # the stored message names the rule, not the server's file path
        dec[str(index)] = {"state": "approved", "rule_id": rule.get("id"), "by": curator, "at": now(),
                           "message": msg.replace(str(store.pack_dir(pid) / f"{rule.get('id')}.yaml"),
                                                  str(rule.get("id"))),
                           "rule": rule}
        _save_decisions(store, pid, dec)
    return {"ok": ok, "message": dec[str(index)]["message"] if ok else msg,
            "decision": dec.get(str(index), {"state": "pending"})}


def reject_draft(store: Store, pid: str, index: int, curator: str, reset: bool = False) -> dict:
    items = drafts(store, pid)
    if not 0 <= index < len(items):
        raise KeyError(index)
    rule = items[index]["rule"] or {}
    if rule.get("id"):
        (store.pack_dir(pid) / f"{rule['id']}.yaml").unlink(missing_ok=True)
    dec = _decisions(store, pid)
    if reset:
        dec.pop(str(index), None)
    else:
        dec[str(index)] = {"state": "rejected", "rule_id": rule.get("id"), "by": curator, "at": now()}
    _save_decisions(store, pid, dec)
    return {"ok": True, "decision": dec.get(str(index), {"state": "pending"})}


# -- results and viewer -------------------------------------------------------------
def findings(store: Store, pid: str) -> dict:
    f = store.run_dir(pid) / "findings.json"
    if not f.exists():
        return {"findings": [], "summary": {}}
    items = load_findings(f)
    summary: dict[str, int] = {}
    for x in items:
        summary[x.verdict] = summary.get(x.verdict, 0) + 1
    return {"findings": [x.model_dump() for x in items], "summary": summary}


def triage(store: Store, pid: str, confirm=(), reject=(), unset=(), dismiss=(), restore=()) -> dict:
    run = store.run_dir(pid)
    if not run.exists():
        raise ValueError("the plan has not been analysed yet")
    return pipeline.save_triage(run, list(confirm), list(dismiss), list(reject), list(unset), list(restore))


def _affine(to_px) -> tuple:
    o, ex, ey = (to_px((0.0, 0.0)), to_px((1.0, 0.0)), to_px((0.0, 1.0)))
    return (ex[0] - o[0], ey[0] - o[0], o[0], ex[1] - o[1], ey[1] - o[1], o[1])


def write_view(run: Path) -> Path:
    """view.json (+ backdrop_<i>.png): every sheet's plan image and everything drawn on it, in image
    pixels, so the browser draws overlays without knowing about sheet coordinates."""
    from ..report.anchor import anchor_point
    from ..report.html_report import _backdrop

    fpath = run / "findings.json"
    all_findings = load_findings(fpath) if fpath.exists() else []
    tri = pipeline.load_triage(run)
    confirmed, rejected = set(tri["confirmed"]), set(tri["rejected"])
    sheets = []
    for bp in sorted(run.glob("building_*.json")):
        idx = int(bp.stem.split("_")[1])
        model = load(BuildingModel, bp)
        png, w, h, to_px = _backdrop(model)
        (run / f"backdrop_{idx}.png").write_bytes(png)
        a, b, c, d, e, f = _affine(to_px)
        k = (abs(a * e - b * d)) ** 0.5           # sheet unit -> px

        def px(pt, a=a, b=b, c=c, d=d, e=e, f=f):
            return [round(a * pt[0] + b * pt[1] + c, 1), round(d * pt[0] + e * pt[1] + f, 1)]

        def state(i: str, conf: bool) -> str:
            if i in rejected:
                return "rejected"
            if i in confirmed:
                return "confirmed"
            return "auto" if conf else "unconfirmed"

        elements = []
        for el in model.elements:
            if el.cls == "other" or not el.geom:
                continue
            item = {"id": el.id, "cls": el.cls, "state": state(el.id, el.confirmed),
                    "confidence": el.prov.confidence, "tag": el.tag,
                    "width_m": el.attrs.get("width_m") or el.attrs.get("thickness_m")}
            if el.cls == "wall":
                item["line"] = [px(q) for q in el.geom]
                item["stroke"] = round(max(1.0, (el.thickness or 0) * k), 1)
            else:
                item["poly"] = [px(q) for q in el.geom]
            elements.append(item)
        rooms = [{"id": r.id, "label": r.label, "type": r.type, "area_m2": r.area_m2,
                  "poly": [px(q) for q in r.polygon],
                  "state": state(r.id, False)} for r in model.rooms]
        fs = []
        for n, fd in enumerate(all_findings):
            if fd.evidence.get("sheet") not in (None, model.sheet.id):
                continue
            ev = fd.evidence
            anc = anchor_point(fd, model) if fd.verdict in ("FAIL", "WARNING") else None
            fs.append({"n": n, "id": ev.get("finding_id"),
                       "polygons": [[px(q) for q in poly] for poly in ev.get("polygons", []) if len(poly) >= 3],
                       "polylines": [[px(q) for q in pl] for pl in ev.get("polylines", []) if len(pl) >= 2],
                       "points": [px(q) for q in ev.get("points", []) if q],
                       "anchor": px(anc) if anc else None,
                       "subjects": fd.subject_ids, "deciding": ev.get("deciding_ids", [])})
        sheets.append({"index": idx, "id": model.sheet.id, "width": w, "height": h, "tier": model.tier,
                       "mode": model.sheet.mode, "sheet_type": model.sheet.sheet_type,
                       "scale": {"method": model.sheet.scale.method,
                                 "metres_per_unit": model.sheet.scale.metres_per_unit,
                                 "confidence": model.sheet.scale.confidence},
                       "warnings": model.sheet.warnings[:20], "elements": elements, "rooms": rooms,
                       "findings": fs})
    out = run / "view.json"
    out.write_text(json.dumps({"sheets": sheets, "triage": {"confirmed": sorted(confirmed),
                                                            "rejected": sorted(rejected),
                                                            "dismissed": tri["dismissed"]}}),
                   encoding="utf-8")
    return out
