"""Operations behind the API. Each one is a thin composition of pipeline.py, rules/ and report/."""

from __future__ import annotations

import json
import math
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

import yaml

from .. import pipeline
from ..rules.draft import OllamaClient, load_drafts, make_client
from ..schema import BuildingModel, load, load_findings
from .jobs import Job
from .store import Project, Store, now, publish

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
    from ..llm import setting

    backend = setting("REVIEWPULSE_LLM", "ollama")
    if backend == "none":
        return None
    try:
        client = make_client(backend, setting("REVIEWPULSE_LLM_MODEL"))
    except (ImportError, ValueError):       # not installed, or a hosted backend that is not fully configured
        return None
    if isinstance(client, OllamaClient) and not client.available():
        return None
    return client


def default_fallback() -> object | None:
    """The optional hosted model (REVIEWPULSE_FALLBACK=openai ...), or None. Used only for projects whose reviewer allowed it."""
    from ..llm import fallback_from_env

    try:
        return fallback_from_env()
    except Exception:       # a misconfigured fallback must never stop the local reading
        return None


def llm_status(factory: Callable[[], object | None]) -> dict:
    from ..llm import describe

    client = factory()
    if client is None:
        return {"available": False, "backend": os.environ.get("REVIEWPULSE_LLM", "ollama"),
                "model": os.environ.get("REVIEWPULSE_LLM_MODEL") or "qwen2.5:7b"}
    return {"backend": type(client).__name__.replace("Client", "").lower(), **describe(client)}


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
           "tiers": [m.tier for m in models],
           "not_floor_plans": [{"sheet": m.sheet.id, "kind": m.sheet.sheet_kind} for m in models
                                if m.sheet.sheet_kind and m.sheet.sheet_kind != "floor_plan"]}
    job.progress(0.75, "indexing the notes written on the drawings")
    try:
        from . import interpret

        out["notes_indexed"] = interpret.index_notes(store, pid, models)
    except Exception as e:  # noqa: BLE001 - the search then indexes on first use; reading the drawings must not fail for it
        out["notes_indexed"], out["notes_index_problem"] = 0, f"{type(e).__name__}: {e}"
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
    summary = pipeline.check(run, packs, programs=programs, inventory_complete=p.inventory_reviewed,
                              attestations=interpret.attestations(store, p.id))
    if job:
        job.progress(0.95, "preparing the viewer")
    write_view(run)
    return {"summary": summary, "rules": rules_summary(store, p)}


def draft(store: Store, pid: str, job: Job, llm_factory: Callable[[], object | None], split_only: bool = False) -> dict:
    """Requirement upload -> clauses (I3) -> drafted rules (I4) with the local model. ``split_only`` stops after the clauses: the
    review desk reads each clause when the reviewer asks, so drafting all of them at upload would be work nobody sees."""
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
    if split_only:
        return {"clauses": n, "drafted": 0, "note": "each requirement is read when a reviewer asks"}
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
    for bp in _sheet_files(run):
        idx = int(bp.stem.split("_")[1])
        model = load(BuildingModel, bp)
        png, w, h, to_px = _backdrop(model)
        publish(run / f"backdrop_{idx}.png", png)
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
                       "affine": [a, b, c, d, e, f],     # sheet space -> pixels of the backdrop: x = a x + b y + c, y = d x + e y + f
                       "mode": model.sheet.mode, "sheet_type": model.sheet.sheet_type,
                       "scale": {"method": model.sheet.scale.method,
                                 "metres_per_unit": model.sheet.scale.metres_per_unit,
                                 "confidence": model.sheet.scale.confidence},
                       "warnings": model.sheet.warnings[:20], "elements": elements, "rooms": rooms,
                       "findings": fs})
    out = run / "view.json"
    publish(out, json.dumps({"sheets": sheets, "triage": {"confirmed": sorted(confirmed),
                                                            "rejected": sorted(rejected),
                                                            "dismissed": tri["dismissed"]}}).encode("utf-8"))
    return out


# -- correction list and reviewer workflow --------------------------------------------------------------------------------
def _sheet_files(run: Path) -> list[Path]:
    """The sheet files in page order (by name, sheet 11 would come before sheet 2)."""
    return sorted(run.glob("building_*.json"), key=lambda f: int(f.stem.split("_")[1]))


_MODELS: dict[Path, tuple[tuple, list[BuildingModel]]] = {}     # run folder -> (what its files were, the models)
_MODELS_KEPT = 3


def _models(store: Store, pid: str) -> list[BuildingModel]:
    """The project's sheet models, for reading only. Loading a 22 sheet set took 9 seconds, on every correction list request, so
    they are kept until a file changes (a new plan or a new analysis)."""
    run = store.run_dir(pid)
    files = _sheet_files(run)
    seen = tuple((f.name, s.st_mtime_ns, s.st_size) for f in files for s in [f.stat()])
    kept = _MODELS.get(run)
    if kept is None or kept[0] != seen:
        kept = (seen, [load(BuildingModel, f) for f in files])
        _MODELS.pop(run, None)
        while len(_MODELS) >= _MODELS_KEPT:
            _MODELS.pop(next(iter(_MODELS)), None)
        _MODELS[run] = kept
    return list(kept[1])


def _sheet_rows(models: list[BuildingModel]) -> list[dict]:
    from ..report.disciplines import sheet_discipline

    rows = []
    for m in models:
        titles = " ".join(t.text for t in m.sheet.texts if t.kind == "title_block")[:300]
        rows.append({"id": m.sheet.id, "page": m.sheet.page, "width": m.sheet.width, "height": m.sheet.height,
                     "scale_method": m.sheet.scale.method, "sheet_type": m.sheet.sheet_type,
                     "discipline": sheet_discipline(m.sheet.id, titles, m.sheet.sheet_type)})
    return rows


def _note_locator(models: list[BuildingModel]):
    """Where a note sits on its sheet: the bounding box of the text runs that make up the note's words."""
    by_id = {m.sheet.id: m for m in models}

    def locate(sheet_id: str, text: str) -> list[float] | None:
        m = by_id.get(sheet_id)
        if m is None:
            return None
        words = {w for w in " ".join(text.split()).casefold().split() if len(w) > 3}
        if not words:
            return None
        hit = [t for t in m.sheet.texts if t.text.strip() and {w for w in t.text.casefold().split() if len(w) > 3} & words
               and t.text.strip().casefold()[:20] in " ".join(text.split()).casefold()]
        if not hit:
            return None
        return [min(t.bbox[0] for t in hit), min(t.bbox[1] for t in hit), max(t.bbox[2] for t in hit), max(t.bbox[3] for t in hit)]

    return locate


def checked_place(store: Store, pid: str, place: dict) -> dict:
    """The place a reviewer points at, if it exists in this project: a decision never rests on a sheet or a spot that is not
    there."""
    model = next((m for m in _models(store, pid) if m.sheet.id == place.get("sheet")), None)
    if model is None:
        raise ValueError("that sheet is not part of this submission")
    box = place.get("box")
    if box is not None:
        slack = 0.02 * max(model.sheet.width, model.sheet.height)
        ok = (len(box) == 4 and all(math.isfinite(v) for v in box) and box[0] <= box[2] and box[1] <= box[3]
              and box[0] >= -slack and box[1] >= -slack and box[2] <= model.sheet.width + slack and box[3] <= model.sheet.height + slack)
        if not ok:
            raise ValueError("that spot is not on the sheet")
    return {"sheet": model.sheet.id, "page": model.sheet.page, "box": [round(float(v), 2) for v in box] if box else None,
            "text": " ".join(str(place.get("text") or "").split())[:600]}


def clause_texts(store: Store, pid: str) -> dict[str, str]:
    """The words of every requirement of the current document; empty without one."""
    from . import interpret

    try:
        return {c["id"]: c["text"] for c in interpret.document(store, pid)["clauses"]}
    except ValueError:
        return {}


def known_clause(store: Store, pid: str, clause: str) -> None:
    if clause not in clause_texts(store, pid):
        raise ValueError(f"the requirement document has no clause {clause}")


def correction_list(store: Store, pid: str, cycle: int | None = None) -> dict:
    """The project's correction list (see report/correction_list.py), with the reviewer's edits, states and sign offs applied."""
    from ..report import correction_list as cl
    from . import interpret, workflow

    p = store.get(pid)
    f = store.run_dir(pid) / "findings.json"
    findings = [x.model_dump() for x in load_findings(f)] if f.exists() else []
    try:
        document = interpret.document(store, pid)
    except ValueError:
        document = {"name": p.requirements, "clauses": []}
    interpreted = interpret.load_results(store, pid)
    models = _models(store, pid)
    decided = workflow.holding(store, pid, {c["id"]: c["text"] for c in document["clauses"]})
    uncovered = 0
    if document["clauses"]:
        try:
            counts = interpret.coverage(store, pid)["summary"]["counts"]        # clauses a person decided are not counted here
            uncovered = sum(counts.get(k, 0) for k in ("awaiting_approval", "not_run", "rejected", "not_checked", "not_read"))
        except ValueError:
            pass
    records = workflow.signoffs(store, pid)
    if cycle is None:                                  # the round is that of the drawings under review
        cycle = max([len(p.versions), 1, *(r["cycle"] for r in records)])
    return cl.build({"name": p.name, "plan": p.plan}, findings, document, interpreted, _sheet_rows(models),
                    states=decided, edits=workflow.item_edits(store, pid), signoffs=records,
                    uncovered=uncovered, cycle=cycle, locate_note=_note_locator(models))


ROUND_COMMENTS = "comments.json"          # beside a version: the comments that were sent on it
BACK_CHECK = "back_check.json"            # beside a version: how it answers the comments of the version before


def keep_round_comments(store: Store, pid: str) -> bool:
    """Save the current correction list beside the current drawing, with each comment's place on the PDF, before a new
    version replaces it. Without this the next round could not be compared with what was asked. False: nothing to keep."""
    from ..files import publish

    p = store.get(pid)
    if not p.plan_version or not any(store.run_dir(pid).glob("building_*.json")):
        return False
    path = correction_export(store, pid, "json")
    try:
        publish(store.version_dir(pid, p.plan_version) / ROUND_COMMENTS, path.read_bytes())
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    return True


def rounds(store: Store, pid: str) -> tuple[dict | None, str]:
    """({old, new, comments}, "") for the current drawing against the one before it, or (None, why not)."""
    import json as _json

    p = store.get(pid)
    if len(p.versions) < 2 or not p.plan_version:
        return None, "only one version of the drawings has been uploaded"
    old, new = p.versions[-2], p.versions[-1]
    if not old["name"].lower().endswith(".pdf") or not new["name"].lower().endswith(".pdf"):
        return None, "two PDF versions are needed to compare them"
    kept = store.version_dir(pid, old["id"]) / ROUND_COMMENTS
    if not kept.exists():
        return None, "no comments were kept for the earlier version (it was not analysed before the new one arrived)"
    raw = _json.loads(kept.read_text(encoding="utf-8"))
    return {"old": old, "new": new, "comments": raw["comments"] if isinstance(raw, dict) else raw}, ""


def run_back_check(store: Store, pid: str, job: Job) -> dict:
    """Every comment of the previous round against the new drawings (backcheck/). A reading for the reviewer: it closes
    nothing by itself."""
    import json as _json

    from ..backcheck import back_check
    from ..backcheck.comments import from_dict
    from ..files import publish

    found, why = rounds(store, pid)
    if found is None:
        raise ValueError(why)
    p = store.get(pid)
    job.progress(0.1, "comparing the two versions of the drawings")
    comments = [from_dict(c, n) for n, c in enumerate(found["comments"])]
    result = back_check(store.version_path(p, found["old"]["id"]), store.version_path(p, found["new"]["id"]), comments)
    job.progress(0.9, "writing the answers")
    out = result.to_dict()
    out.pop("old_pdf", None), out.pop("new_pdf", None)                 # paths of this computer are not part of the answer
    out.update(old_version=found["old"], new_version=found["new"], made=now_stamp())
    publish(store.version_dir(pid, found["new"]["id"]) / BACK_CHECK, _json.dumps(out, default=float).encode("utf-8"))
    return {"comments": len(comments), "counts": out["counts"]}


def now_stamp() -> str:
    from .store import now

    return now()


def back_check_view(store: Store, pid: str) -> dict:
    """The saved back check of the current drawings, with each place on the new sheets as a box the screen can show."""
    import json as _json

    found, why = rounds(store, pid)
    if found is None:
        return {"available": False, "why": why}
    kept = store.version_dir(pid, found["new"]["id"]) / BACK_CHECK
    base = {"available": True, "comments": len(found["comments"]), "old_version": found["old"], "new_version": found["new"]}
    if not kept.exists():
        return {**base, "done": False}
    data = _json.loads(kept.read_text(encoding="utf-8"))
    sheets = {m.sheet.page: m.sheet for m in _models(store, pid)}
    pt = 72 / 25.4

    def place(spot: dict) -> dict | None:
        sheet = sheets.get((spot.get("page") or 0) - 1)
        if sheet is None or not spot.get("bbox"):
            return None
        x0, y0, x1, y1 = spot["bbox"]                                 # page points, y down; sheets are millimetres, y up
        return {"sheet": sheet.id, "text": "", "box": [round(x0 / pt, 2), round(sheet.height - y1 / pt, 2),
                                                       round(x1 / pt, 2), round(sheet.height - y0 / pt, 2)]}

    answers = [{"id": v["comment"]["id"], "comment": v["comment"]["text"], "code": v["comment"].get("code", ""),
                "status": v["status"], "reason": v["reason"], "person_must_check": v["evidence"]["person_must_check"],
                "old_value": v["evidence"]["old_value"], "new_value": v["evidence"]["new_value"],
                "place": place(v["evidence"]["new_place"])} for v in data["verdicts"]]
    return {**base, "done": True, "made": data["made"], "counts": data["counts"], "answers": answers,
            "changes_nobody_asked_for": len(data["new_issues"]), "clouds_present": data["clouds_present"],
            "changes_outside_clouds": len(data["changes_not_clouded"]), "sheets_added": data["sheets_added"],
            "sheets_removed": data["sheets_removed"]}


def correction_export(store: Store, pid: str, fmt: str, cycle: int | None = None) -> Path:
    """The correction list as pdf (the submitted PDF with annotations), bcf, json or csv, written under the run folder."""
    from ..report.correction_list import export

    p = store.get(pid)
    plan = store.plan_path(p)
    data = correction_list(store, pid, cycle)
    own = store.run_dir(pid) / "exports" / uuid.uuid4().hex[:12]     # one folder a request: two exports never share a file
    return export(data, fmt, own, _models(store, pid),
                  plan if plan is not None and plan.suffix.lower() == ".pdf" else None)
