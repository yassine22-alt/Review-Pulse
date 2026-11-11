"""Stage orchestration. Every stage reads and writes files in ``runs/<id>/`` (D7).

    inspect  : file            -> sheets.json
    extract  : sheets.json     -> sheet_<n>.json, preview_<n>.png
    build    : sheet_<n>.json  -> building_<n>.json, scale_report_<n>.json, rooms_<n>.png
    check    : building + pack -> findings.json, findings.csv, report.pdf, report.html
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .annotate.dimensions import build_chains, dimensions_from_pairs, link_ends
from .annotate.layout import build_layout, sheet_type
from .annotate.scale import paper_mm_assumed, recover_scale
from .annotate.schedules import associate_tags, find_schedules
from .annotate.text_classify import classify_items
from .core.tiers import apply_confirmation, tier
from .ingest.classify import SheetStub, inspect_file, read_sheets, write_sheets
from .schema import BuildingModel, Sheet, load, save


def run_id_for(path: Path) -> str:
    h = hashlib.sha1(path.read_bytes()).hexdigest()[:8]
    return f"{path.stem}_{h}"


# ---------------------------------------------------------------------------
def inspect(path: str | Path, runs_dir: str | Path = "runs", run_id: str | None = None) -> Path:
    path = Path(path)
    stubs = inspect_file(path)
    run_dir = Path(runs_dir) / (run_id or run_id_for(path))
    write_sheets(stubs, run_dir)
    return run_dir


def extract_stub(stub: SheetStub, run_dir: Path, units: str | None = None, preview: bool = True) -> Sheet:
    sheet_id = f"{Path(stub.source_file).stem}_p{stub.page}"
    if stub.file_type == "pdf":
        from .ingest.pdf_backend import PyMuPdfBackend, render_preview

        sheet = PyMuPdfBackend().extract(Path(stub.source_file), stub.page, sheet_id)
        sheet.mode = stub.mode
        sheet.warnings = stub.warnings + sheet.warnings
        if stub.mode == "raster":
            sheet.warnings.append("raster page: vector primitives are not meaningful; raster path (R13) required")
        else:
            from .ingest.outline_text import needs_ocr, ocr_outline_text

            if needs_ocr(sheet):
                ocr_outline_text(sheet, Path(stub.source_file), stub.page)
        if preview:
            render_preview(Path(stub.source_file), stub.page, run_dir / f"preview_{stub.index}.png")
    elif stub.file_type in ("dxf", "dwg"):
        from .ingest.dxf_reader import extract_dxf

        sheet = extract_dxf(Path(stub.source_file), sheet_id, units=units)
        sheet.warnings = stub.warnings + [w for w in sheet.warnings if w not in stub.warnings]
        if preview:
            _dxf_preview(sheet, run_dir / f"preview_{stub.index}.png")
    elif stub.file_type == "svg":
        from .ingest.svg_reader import extract_svg

        sheet = extract_svg(Path(stub.source_file), sheet_id)
        if preview:
            _dxf_preview(sheet, run_dir / f"preview_{stub.index}.png")
    else:
        sheet = Sheet(id=sheet_id, source_file=stub.source_file, mode="raster", coord_unit="paper_mm",
                      width=stub.width_mm or 0, height=stub.height_mm or 0,
                      warnings=stub.warnings + ["image input: raster path (R13) required"])
    classify_items(sheet.texts)
    _llm_labels(sheet)
    return sheet


def _llm_labels(sheet: Sheet) -> None:
    from .annotate.label_llm import apply_llm_labels

    n = apply_llm_labels(sheet.texts)
    if n:
        sheet.warnings.append(f"{n} room label(s) read by the local language model (verify room types)")


def extract(run_dir: str | Path, units: str | None = None) -> list[Path]:
    run_dir = Path(run_dir)
    out = []
    for stub in read_sheets(run_dir):
        sheet = extract_stub(stub, run_dir, units)
        out.append(save(sheet, run_dir / f"sheet_{stub.index}.json"))
    return out


def build_model(sheet: Sheet, calibrate: tuple | None = None, confirmed: set | None = None,
                run_dir: Path | None = None, index: int = 0, learned: bool | None = None,
                annotator=None, learned_mode: str | None = None) -> BuildingModel:
    """``learned``: run the learned primitive classifier as a second pass (None = whenever a trained
    model is present, unless env REVIEWPULSE_LEARNED=0). On by default since D8: on real CAD it lifts
    wall F1 0.28 -> 0.52, doors 0.66 -> 0.90, windows 0.20 -> 0.69 (FloorPlanCAD), with no room or
    planted error lost on generated plans (reports/v4_fuse).

    ``annotator``: what writes the per-primitive calls of the second pass (default: the classifier).
    Evaluation passes one that writes the dataset's true labels, to build a reference from true
    lines. ``learned_mode``: "fuse" or "rebuild" (default: env REVIEWPULSE_LEARNED_MODE, else fuse)."""
    if sheet.mode == "raster":
        # scans and photos: R13 raster path (same BuildingModel contract)
        from .perception.raster.build import build_raster_model

        return build_raster_model(sheet, calibrate=calibrate, confirmed=confirmed)
    from .core.normalise import fit_arcs, tag_door_leaves, tag_glazing, tag_patterns
    from .perception.openings import detect_openings
    from .perception.rooms import detect_rooms
    from .perception.walls import detect_walls

    # normalise drawing styles (arcs drawn as segments, layer-free glazing symbols)
    n_arcs = fit_arcs(sheet)
    if n_arcs:
        sheet.warnings.append(f"{n_arcs} arcs recovered from line chains")
    # R12 tables first: their text must not feed labels, tags or the scale
    schedules, table_boxes = find_schedules(sheet)
    # R7 scale
    scale, scale_rep = recover_scale(sheet, calibrate)
    sheet.scale = scale
    scale_known = scale.metres_per_unit is not None
    from .annotate.dimensions import tag_dimension_graphics

    tag_dimension_graphics(sheet, scale_rep.candidates)
    mpu = scale.metres_per_unit or paper_mm_assumed(sheet)
    if not scale_known:
        sheet.warnings.append(f"scale unknown: thresholds assume {mpu} m per unit; confidences x0.7")
    tag_glazing(sheet, mpu)
    tag_door_leaves(sheet)
    tag_patterns(sheet, mpu)
    # R5 exclusions (title block and tables)
    from .annotate.layout import title_block_box

    excl = list(table_boxes)
    tb = title_block_box(sheet)
    if tb:
        excl.append(tb)
    # R8-R10
    walls, columns = detect_walls(sheet, mpu, assumed_scale=not scale_known, exclude_boxes=excl)
    openings = detect_openings(sheet, walls, columns, mpu, scale_known)
    sheet.warnings += associate_tags(sheet, openings, mpu, scale_known)
    rooms, edges, room_warn = detect_rooms(sheet, walls, columns, openings, mpu, scale_known)
    if learned is None:
        from .perception.learned.classifier import available

        learned = os.environ.get("REVIEWPULSE_LEARNED", "1") != "0" and available()
    if learned:
        # D8 learned pass: the classifier reads the rule results; walls are fused (fuse.py), then
        # openings and rooms are rebuilt on them
        by_classifier = annotator is None    # a given annotator (true labels) is never second-guessed
        if by_classifier:
            from .perception.learned.classifier import annotate_primitives as annotator
        annotator(BuildingModel(sheet=sheet, elements=walls + columns + openings, rooms=rooms))
        from .perception.learned.fuse import fuse_walls
        from .perception.learned.openings import learned_openings
        from .perception.openings import carry_openings

        rules_pass = (walls, columns, openings, rooms, edges, room_warn)
        rebuilt, _cols = detect_walls(sheet, mpu, assumed_scale=not scale_known, exclude_boxes=excl)
        # the rules propose, the classifier disposes: rule walls stay unless the classifier rejects
        # their lines; rebuilt walls are added only where no kept wall stands
        if (learned_mode or os.environ.get("REVIEWPULSE_LEARNED_MODE", "fuse")) == "rebuild":
            walls = rebuilt              # walls from the classifier's lines only (D8 comparison)
        else:
            from .perception.learned.classifier import wall_threshold
            from .perception.learned.fuse import KEEP_MIN

            walls, fusion = fuse_walls(sheet, rules_pass[0], rebuilt, wall_threshold() if by_classifier else KEEP_MIN)
            sheet.warnings.append(f"learned classifier: {fusion['rejected']} rule wall(s) rejected, "
                                  f"{fusion['added']} added")
        openings = detect_openings(sheet, walls, columns, mpu, scale_known) if walls else []
        openings += carry_openings(rules_pass[2], openings, walls, mpu)
        openings += learned_openings(sheet, walls, openings, mpu)
        if by_classifier and not any(e.cls == "wall" for e in walls) and any(e.cls == "wall" for e in rules_pass[0]):
            # the classifier rejected every wall the rules found: a drawing style outside its training
            # data. Keep the rule result rather than an empty building.
            walls, columns, openings, rooms, edges, room_warn = rules_pass
            for p in sheet.primitives:
                p.prov.evidence.pop("learned_wall", None)
            sheet.warnings.append("learned primitive classifier found no walls where the rules did "
                                  "(drawing style outside its training data): rule result kept")
        else:
            associate_tags(sheet, openings, mpu, scale_known)
            rooms, edges, room_warn = detect_rooms(sheet, walls, columns, openings, mpu, scale_known)
            sheet.warnings.append("learned primitive classifier applied (second pass)")
    sheet.warnings += room_warn
    # R11 dimensions
    if not sheet.dimensions and scale_rep.candidates:
        # no DIMENSION entities (PDF, or exploded CAD dimensions): build them from text/line pairs
        sheet.dimensions = dimensions_from_pairs(sheet, scale_rep.candidates, mpu)
    build_chains(sheet.dimensions, mpu)
    link_ends(sheet.dimensions, walls, openings, mpu)
    # R5 layout and sheet type
    sheet.layout = build_layout(sheet, walls, table_boxes)
    sheet.sheet_type = sheet_type(sheet, walls)

    stairs: list = []
    if scale_known:                      # a tread depth in unknown units means nothing: no scale, no stairs
        from .perception.stairs import find_stairs

        try:
            stairs = find_stairs(sheet, mpu)
        except Exception as exc:  # noqa: BLE001 - stairs are an addition; a failure must not lose the building
            sheet.warnings.append(f"stair finder failed ({type(exc).__name__}): stairs not reported")
        if stairs:
            sheet.warnings.append(f"{len(stairs)} stair flight(s) found from their tread lines")
    model = BuildingModel(sheet=sheet, elements=walls + columns + openings + stairs, rooms=rooms, edges=edges,
                          schedules=[{k: v for k, v in s.items()} for s in schedules])
    model.tier = tier(sheet)
    apply_confirmation(model, confirmed)
    if run_dir is not None:
        (run_dir / f"scale_report_{index}.json").write_text(json.dumps(scale_rep.to_dict(), indent=1), encoding="utf-8")
    return model


def build(run_dir: str | Path, calibrate: tuple | None = None, confirmed: set | None = None,
          images: bool = True) -> list[Path]:
    run_dir = Path(run_dir)
    out = []
    for sp in sorted(run_dir.glob("sheet_*.json")):
        idx = int(sp.stem.split("_")[1])
        sheet = load(Sheet, sp)
        model = build_model(sheet, calibrate, confirmed, run_dir, idx)
        out.append(save(model, run_dir / f"building_{idx}.json"))
        if images:
            from .report.debug_png import rooms_png

            rooms_png(model, run_dir / f"rooms_{idx}.png")
    return out


def load_packs(pack) -> list:
    """One pack (folder or file) or a list of packs; a later pack's rule replaces an earlier one with the
    same id (a project pack refines its base pack)."""
    from .rules.schema import load_pack

    packs = pack if isinstance(pack, (list, tuple)) else [pack]
    by_id: dict = {}
    for p in packs:
        for r in load_pack(p):
            by_id[r.id] = r
    return list(by_id.values())


def apply_rejection(model: BuildingModel, rejected: set) -> None:
    """Elements the reviewer marked as wrong leave the model, with the room connections through them."""
    if not rejected:
        return
    model.elements = [e for e in model.elements if e.id not in rejected]
    model.edges = [e for e in model.edges if e.via not in rejected]


def check(run_dir: str | Path, pack, confirmed: set | None = None,
          dismissed: dict | None = None, reports: bool = True, brief: str | Path | None = None,
          programs: list | None = None, inventory_complete: bool = False) -> dict:
    """Run the rules on every sheet of a run. ``brief``: the project's brief (programme) table; it is
    kept in the run folder so later checks use it too. ``programs``: rules approved by a reviewer from the requirement
    document (interpreter programs); they run on the same plan and their findings join the others, with the full
    outcome of each saved in ``interpreted_results.json``. ``inventory_complete``: a person confirmed that every room,
    door and window was found, which is what allows a rule over "every" member to be reported as satisfied."""
    import shutil

    from .engine.run import run, summarise
    from .report.csv_out import write_csv
    from .rules.programme import attach_programme
    from .schema import save_findings

    run_dir = Path(run_dir)
    if brief is not None:
        for old in run_dir.glob("brief.*"):
            old.unlink()
        shutil.copyfile(brief, run_dir / f"brief{Path(brief).suffix.lower()}")
    briefs = sorted(run_dir.glob("brief.*"))
    n_sheets = len(list(run_dir.glob("building_*.json")))
    rules = load_packs(pack)
    triage = load_triage(run_dir)
    rejected = set(triage.get("rejected", []))
    confirmed = (set(confirmed or ()) | set(triage.get("confirmed", []))) - rejected
    dismissed = {**triage.get("dismissed", {}), **(dismissed or {})}
    all_findings = []
    models = []
    interpreted_results: list[dict] = []
    for bp in sorted(run_dir.glob("building_*.json")):
        model = load(BuildingModel, bp)
        if briefs and n_sheets == 1:
            attach_programme(model, briefs[0])
        elif briefs:
            # a brief describes the whole building: per sheet, rooms on other floors would read as missing
            model.sheet.warnings.append("brief not checked: the run has several sheets and the brief covers "
                                        "the whole building (sheets are not combined yet)")
        apply_rejection(model, rejected)
        if confirmed:
            apply_confirmation(model, confirmed)
        findings = run(model, rules, confirmed)
        if programs:
            findings += _run_programs(model, programs, inventory_complete, interpreted_results)
        for f in findings:
            key = finding_key(f)
            f.evidence["finding_id"] = key
            f.evidence["sheet"] = model.sheet.id
            if key in dismissed:
                f.evidence["dismissed"] = dismissed[key]
        all_findings += findings
        models.append(model)
    save_findings(all_findings, run_dir / "findings.json")
    (run_dir / "interpreted_results.json").write_text(json.dumps(interpreted_results, indent=1), encoding="utf-8")
    write_csv(all_findings, models, run_dir / "findings.csv")
    if reports and models:
        from .report.html_report import write_html
        from .report.pdf_overlay import write_annotated_pdf

        write_annotated_pdf(models, all_findings, run_dir / "report.pdf")
        write_html(models, all_findings, run_dir / "report.html")
    return summarise(all_findings)


def _run_programs(model, programs, inventory_complete: bool, results: list[dict]) -> list:
    """Approved interpreter programs on one sheet: findings for the viewer and one outcome record per program."""
    from .factgraph.convert import to_graph, to_inputs
    from .factgraph.from_building import from_building
    from .interpreter.findings import to_findings

    graph_facts = from_building(model, complete=inventory_complete)
    inputs, graph = to_inputs(graph_facts), to_graph(graph_facts)
    out = []
    for program in programs:
        found, explained = to_findings(program, inputs, graph, model, model.tier)
        out += found
        clause = program.sources[0].clause if program.sources else None
        results.append({
            "sheet": model.sheet.id, "program_id": program.id, "title": program.title, "clause": clause,
            "outcome": explained.outcome, "checked": explained.selected,
            "violated": [m.entity for m in explained.members if m.state == "violated"],
            "unknown": [m.entity for m in explained.members if m.state == "unknown"],
            "missing": explained.missing[:10], "issues": [i.code.value for i in explained.issues],
            "approved_by": program.approved_by})
    return out


# ---------------------------------------------------------------------------
def finding_key(f) -> str:
    h = hashlib.sha1((f.rule_id + "|" + ",".join(sorted(f.subject_ids))).encode()).hexdigest()[:8]
    return f"{f.rule_id}:{h}"


def load_triage(run_dir: Path) -> dict:
    p = run_dir / "triage.json"
    t = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for k, v in (("confirmed", []), ("rejected", []), ("dismissed", {}), ("log", [])):
        t.setdefault(k, v)
    return t


def save_triage(run_dir: Path, confirm: list[str], dismiss: list[str], reject: list[str] = (),
                unset: list[str] = (), restore: list[str] = ()) -> dict:
    """confirm / reject elements (or rooms), ``unset`` returns them to undecided; dismiss findings
    (``<finding_id>:<reason>``), ``restore`` un-dismisses them."""
    import datetime as dt

    t = load_triage(run_dir)
    now = dt.datetime.now().isoformat(timespec="seconds")
    for c in confirm:
        if c in t["rejected"]:
            t["rejected"].remove(c)
        if c not in t["confirmed"]:
            t["confirmed"].append(c)
            t["log"].append({"at": now, "action": "confirm", "id": c})
    for c in reject:
        if c in t["confirmed"]:
            t["confirmed"].remove(c)
        if c not in t["rejected"]:
            t["rejected"].append(c)
            t["log"].append({"at": now, "action": "reject", "id": c})
    for c in unset:
        if c in t["confirmed"] or c in t["rejected"]:
            t["confirmed"] = [x for x in t["confirmed"] if x != c]
            t["rejected"] = [x for x in t["rejected"] if x != c]
            t["log"].append({"at": now, "action": "unset", "id": c})
    for fid in restore:
        if t["dismissed"].pop(fid, None) is not None:
            t["log"].append({"at": now, "action": "restore", "id": fid})
    for d in dismiss:
        fid, _, reason = d.partition(":")
        # finding ids contain a colon themselves: RULE:hash:reason
        parts = d.split(":")
        if len(parts) >= 3:
            fid, reason = ":".join(parts[:2]), ":".join(parts[2:])
        t["dismissed"][fid] = reason or "dismissed"
        t["log"].append({"at": now, "action": "dismiss", "id": fid, "reason": reason})
    (run_dir / "triage.json").write_text(json.dumps(t, indent=1), encoding="utf-8")
    return t


def _dxf_preview(sheet: Sheet, out: Path) -> None:
    from .report.debug_png import sheet_png

    sheet_png(sheet, out)


def run_all(path: str | Path, pack: str | Path, runs_dir: str | Path = "runs", units: str | None = None,
            calibrate: tuple | None = None, confirmed: set | None = None) -> tuple[Path, dict]:
    run_dir = inspect(path, runs_dir)
    extract(run_dir, units)
    build(run_dir, calibrate, confirmed)
    return run_dir, check(run_dir, pack, confirmed)


__all__ = ["inspect", "extract", "build", "check", "run_all", "build_model", "extract_stub", "save_triage",
           "load_packs", "apply_rejection"]
