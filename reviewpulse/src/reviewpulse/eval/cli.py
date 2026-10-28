"""E3 - ``rp eval``: score a stage on a dataset, write a report and a results.csv row.

Tasks (synthetic dataset; public adapters plug into the same functions):
    walls     R8  length-weighted P/R/F1 of centrelines
    openings  R9  polygon IoU>=0.5 P/R/F1 per class (oracle: true walls)
    rooms     R10 room P/R/F1 at IoU 0.5 and door-edge F1 (oracle: true walls+openings)
    scale     R7  relative scale error on the PDF export
    dims      R11 chain / overall detection and value agreement
    findings  end to end: recall of planted errors, false alarms on clean plans,
              attributed to perception or rules by re-running on the oracle model
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Polygon

from ..schema import BuildingModel
from .matching import length_coverage, match_polygons, prf


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _plans(n: int, workdir: Path, fmt: str = "dxf", errors_cycle: bool = False, **kw) -> list[dict]:
    from ..synth.make_plan import ERRORS, make_plan

    keys = list(ERRORS)
    out = []
    for i in range(n):
        errs = (keys[(i // 2) % len(keys)],) if errors_cycle and i % 2 else ()   # every switch in turn
        out.append(make_plan(workdir, seed=1000 + i, errors=errs, png=False, **kw))
    return out


def _model_from(path: str) -> BuildingModel:
    from ..ingest.classify import inspect_file
    from ..pipeline import build_model, extract_stub

    stub = inspect_file(path)[0]
    sheet = extract_stub(stub, Path(path).parent, preview=False)
    return build_model(sheet)


def _to_metres_poly(coords, k: float):
    return Polygon([(x * k, y * k) for x, y in coords])


def _unit_k(model: BuildingModel) -> float:
    return model.sheet.scale.metres_per_unit or 1.0


# ---------------------------------------------------------------------------
def eval_walls(plans, fmt) -> tuple[dict, list]:
    from .adapters.synth import load_truth, truth_wall_lines

    rows, worst = [], []
    P = R = 0.0
    for p in plans:
        t = load_truth(p["truth"])
        m = _model_from(p[fmt])
        k = _unit_k(m)
        pred = [(LineString([(x * k, y * k) for x, y in e.geom]), (e.thickness or 0) * k)
                for e in m.elements if e.cls == "wall"]
        true = truth_wall_lines(t)
        if fmt == "pdf":
            pred = _align_pdf(pred, t, m)
        pr, rc = length_coverage(pred, true, tol=0.05)
        P += pr
        R += rc
        worst.append((prf(pr, rc), t["name"]))
        rows.append((t["name"], pr, rc))
    n = len(plans)
    res = {"precision": P / n, "recall": R / n, "f1": prf(P / n, R / n), "n": n}
    return res, sorted(worst)[:10]


def _align_pdf(pred, t, m):
    """Map PDF sheet space (paper mm) back to metres with the generator's exact transform."""
    from shapely.affinity import affine_transform

    tr = t["pdf_transform"]
    k = 1.0 / tr["k"]
    mpu = m.sheet.scale.metres_per_unit or 1.0
    out = []
    for ln, th in pred:
        mm = affine_transform(ln, [1 / mpu, 0, 0, 1 / mpu, 0, 0])        # undo the metres conversion
        out.append((affine_transform(mm, [k, 0, 0, k, -tr["ox"] * k, -tr["oy"] * k]), th))
    return out


def eval_openings(plans, fmt, oracle: set) -> tuple[dict, list]:
    from ..perception.openings import detect_openings
    from ..perception.walls import detect_walls
    from .adapters.synth import load_truth, truth_columns, truth_openings, truth_walls

    per_cls = defaultdict(lambda: [0, 0, 0])   # tp, pred, true
    worst = []
    for p in plans:
        t = load_truth(p["truth"])
        m = _model_from(p["dxf"])
        sheet = m.sheet
        if "walls" in oracle:
            walls, cols = truth_walls(t), truth_columns(t)
        else:
            walls, cols = detect_walls(sheet, 1.0)
        ops = detect_openings(sheet, walls, cols, 1.0)
        true = truth_openings(t)
        f1s = []
        for cls in ("door", "window"):
            pp = [Polygon(o.geom).buffer(0.02) for o in ops if o.cls == cls]
            tt = [Polygon(o.geom).buffer(0.02) for o in true if o.cls == cls]
            mr = match_polygons(pp, tt, 0.5)
            per_cls[cls][0] += mr.tp
            per_cls[cls][1] += mr.n_pred
            per_cls[cls][2] += mr.n_true
            f1s.append(mr.f1)
        worst.append((min(f1s), t["name"]))
    res = {}
    for cls, (tp, npred, ntrue) in per_cls.items():
        pr = tp / npred if npred else 1.0
        rc = tp / ntrue if ntrue else 1.0
        res[cls] = {"precision": pr, "recall": rc, "f1": prf(pr, rc), "tp": tp, "pred": npred, "true": ntrue}
    return res, sorted(worst)[:10]


def eval_rooms(plans, oracle: set) -> tuple[dict, list]:
    from ..perception.openings import detect_openings
    from ..perception.rooms import detect_rooms
    from ..perception.walls import detect_walls
    from .adapters.synth import load_truth, truth_columns, truth_openings, truth_room_polys, truth_walls

    tp = npred = ntrue = 0
    etp = epred = etrue = 0
    worst = []
    for p in plans:
        t = load_truth(p["truth"])
        m = _model_from(p["dxf"])
        sheet = m.sheet
        if "walls" in oracle:
            walls, cols = truth_walls(t), truth_columns(t)
        else:
            walls, cols = detect_walls(sheet, 1.0)
        ops = truth_openings(t) if "openings" in oracle else detect_openings(sheet, walls, cols, 1.0)
        rooms, edges, _ = detect_rooms(sheet, walls, cols, ops, 1.0)
        tr = truth_room_polys(t)
        names = list(tr)
        mr = match_polygons([Polygon(r.polygon) for r in rooms], [tr[n] for n in names], 0.5)
        tp += mr.tp
        npred += mr.n_pred
        ntrue += mr.n_true
        p2t = {rooms[i].id: names[j] for i, j in mr.pred_to_true().items()}
        pe = {(frozenset((p2t.get(e.a, e.a), p2t.get(e.b, e.b))), e.kind) for e in edges if e.kind == "door"}
        te = {(frozenset((e["a"], e["b"])), e["kind"]) for e in t["edges"] if e["kind"] == "door"}
        etp += len(pe & te)
        epred += len(pe)
        etrue += len(te)
        worst.append((mr.f1, t["name"]))
    pr, rc = (tp / npred if npred else 1.0), (tp / ntrue if ntrue else 1.0)
    epr, erc = (etp / epred if epred else 1.0), (etp / etrue if etrue else 1.0)
    return ({"rooms": {"precision": pr, "recall": rc, "f1": prf(pr, rc)},
             "door_edges": {"precision": epr, "recall": erc, "f1": prf(epr, erc)}}, sorted(worst)[:10])


def eval_scale(plans) -> tuple[dict, list]:
    errs, worst = [], []
    for p in plans:
        m = _model_from(p["pdf"])
        t = _truth(p)
        true_mpu = t["denominator"] / 1000
        got = m.sheet.scale.metres_per_unit
        e = abs(got - true_mpu) / true_mpu if got else 1.0
        errs.append(e)
        worst.append((-e, t["name"], m.sheet.scale.method))
    return {"mean_rel_error": sum(errs) / len(errs), "max_rel_error": max(errs),
            "share_below_0.5pct": sum(e < 0.005 for e in errs) / len(errs)}, sorted(worst)[:10]


def _truth(p):
    from .adapters.synth import load_truth

    return load_truth(p["truth"])


def eval_findings(plans, fmt, oracle: set) -> tuple[dict, list]:
    """Planted-error recall plus attribution (E1):
    - rules:      planted errors found on the oracle (true) model;
    - perception: findings that differ between the real model and the oracle model.
    Findings the oracle produces beyond the planted list are true consequences, not false alarms."""
    from ..cli import DEFAULT_PACK
    from ..engine.run import run
    from ..rules.schema import load_pack
    from .adapters.synth import truth_model

    rules = load_pack(DEFAULT_PACK)
    planted = found_real = found_oracle = found_any = 0
    perception_diff = 0
    per_rule = defaultdict(lambda: [0, 0, 0])
    tiers: dict[str, int] = defaultdict(int)
    scale_err = []
    notes = []

    def bad(fs):
        return {(f.rule_id, f.verdict) for f in fs if f.verdict in ("FAIL", "WARNING")}

    for p in plans:
        t = _truth(p)
        m = _model_from(p[fmt])
        tiers[m.tier] += 1
        if t.get("denominator") and m.sheet.coord_unit == "paper_mm":
            got = m.sheet.scale.metres_per_unit
            scale_err.append(abs(got - t["denominator"] / 1000) / (t["denominator"] / 1000) if got else 1.0)
        dxf_sheet = m.sheet if fmt == "dxf" else _model_from(p["dxf"]).sheet
        real = bad(run(m, rules))
        orc = bad(run(truth_model(t, dxf_sheet), rules))
        for e in {(e["rule"], e["verdict"]) for e in t["expected_findings"]}:
            planted += 1
            per_rule[e[0]][2] += 1
            if e in real:
                found_real += 1
                per_rule[e[0]][0] += 1
            if any(r == e[0] for r, _v in real):
                found_any += 1          # flagged, possibly as WARNING on a lower tier (policy, not a miss)
            if e not in real:
                notes.append((t["name"], "missed on real model", e))
            if e in orc:
                found_oracle += 1
                per_rule[e[0]][1] += 1
            else:
                notes.append((t["name"], "missed on oracle model (rule/engine error)", e))
        for x in real ^ orc:
            perception_diff += 1
            notes.append((t["name"], "real only (perception false alarm)" if x in real else "oracle only (perception miss)", x))
    return ({"planted": planted, "recall_real": found_real / planted if planted else 1.0,
             "recall_real_any_verdict": found_any / planted if planted else 1.0,
             "recall_oracle": found_oracle / planted if planted else 1.0,
             "perception_disagreements": perception_diff, "plans": len(plans),
             "tiers": dict(sorted(tiers.items())),
             **({"scale_mean_rel_error": sum(scale_err) / len(scale_err)} if scale_err else {}),
             "per_rule_real/oracle/planted": {k: f"{a}/{b}/{c}" for k, (a, b, c) in sorted(per_rule.items())}},
            notes[:30])


# ---------------------------------------------------------------------------
def run_eval(task: str, dataset: str, n: int = 30, method: str = "rules", oracle: str = "off",
             out_dir: Path = Path("reports"), data_dir: Path = Path("data"), fmt: str = "dxf") -> tuple[Path, dict]:
    if "learned" in method:
        from ..perception.learned.classifier import available, model_dir

        if not available():
            # otherwise every drawing crashes (public sets) or silently runs rules only (synthetic)
            raise SystemExit(f"method {method!r}: no primitive model at {model_dir()}")
    if task == "raster":
        # R13: CubiCasa5K test scans, rules vs model vs fusion (method "all") or one method
        from .raster_eval import run as run_raster

        methods = ("rules", "model", "fusion", "model_scan") if method in ("all", "") else tuple(method.split(","))
        res, worst = run_raster(n=n, methods=methods)
        return write_report(task, "cubicasa5k", method, n, oracle, res, [str(w) for w in worst], out_dir)
    if dataset != "synth":
        from .adapters import public

        return public.run_public_eval(task, dataset, n=n, out_dir=out_dir, data_dir=data_dir, method=method,
                                      oracle=oracle)
    orc = set() if oracle in ("off", "", None) else set(oracle.split(","))
    if method in ("rules", "learned"):
        # the method named in the report is the one scored, whatever the pipeline default is
        os.environ["REVIEWPULSE_LEARNED"] = "1" if method == "learned" else "0"
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        if task == "walls":
            res, worst = eval_walls(_plans(n, wd), fmt)
        elif task == "walls_pdf":
            res, worst = eval_walls(_plans(n, wd), "pdf")
        elif task == "openings":
            res, worst = eval_openings(_plans(n, wd), fmt, orc)
        elif task == "rooms":
            res, worst = eval_rooms(_plans(n, wd), orc)
        elif task == "scale":
            from ..synth.make_plan import make_plan

            plans = [make_plan(wd, seed=2000 + i, denominator=d, png=False)
                     for i, d in enumerate([50, 100, 200] * max(1, n // 3))]
            res, worst = eval_scale(plans)
        elif task in ("random", "random_pdf"):
            from .perception import run_random_eval

            res, worst = run_random_eval(n, "pdf" if task.endswith("pdf") else "dxf", out_dir)
        elif task == "findings_outlined":
            # vector PDFs whose text is drawn as outlines (CAD SHX export): OCR path
            from ..synth.outline_text import outline_pdf

            plans = _plans(n, wd, errors_cycle=True)
            for p in plans:
                p["pdf_outlined"] = str(outline_pdf(p["pdf"], Path(p["pdf"]).with_name(Path(p["pdf"]).stem + "_outl.pdf")))
            res, worst = eval_findings(plans, "pdf_outlined", orc)
        elif task in ("findings", "findings_pdf"):
            res, worst = eval_findings(_plans(n, wd, errors_cycle=True), "pdf" if task.endswith("pdf") else fmt, orc)
        else:
            raise NotImplementedError(f"unknown task {task!r}")
    return write_report(task, dataset, method, n, oracle, res, worst, out_dir)


def write_report(task, dataset, method, n, oracle, res, worst, out_dir: Path) -> tuple[Path, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    date = dt.date.today().isoformat()
    path = out_dir / f"{date}_{task}_{method}.md"
    commit = _commit()
    lines = [f"# Evaluation: {task}", "", f"- dataset: {dataset} (public data only: no real plans scored yet)",
             f"- items: {n}", f"- method: {method}", f"- oracle inputs: {oracle}", f"- commit: {commit}",
             f"- date: {date}", "", "## Metrics", "", "```", _fmt(res), "```", "", "## Worst items / misses", ""]
    lines += [f"- {w}" for w in worst] or ["- none"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    row = {"date": date, "task": task, "dataset": dataset, "method": method, "oracle": oracle, "n": n,
           "commit": commit, "metrics": _flat(res)}
    csv_path = out_dir / "results.csv"
    new = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date", "task", "dataset", "method", "oracle", "n", "commit", "metrics"])
        w.writerow([row[k] for k in ("date", "task", "dataset", "method", "oracle", "n", "commit", "metrics")])
    return path, row


def _fmt(d, indent=0) -> str:
    out = []
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(" " * indent + f"{k}:")
            out.append(_fmt(v, indent + 2))
        elif isinstance(v, float):
            out.append(" " * indent + f"{k}: {v:.4f}")
        else:
            out.append(" " * indent + f"{k}: {v}")
    return "\n".join(out)


def _flat(d, prefix="") -> str:
    parts = []
    for k, v in d.items():
        if isinstance(v, dict):
            parts.append(_flat(v, prefix + k + "."))
        elif isinstance(v, float):
            parts.append(f"{prefix}{k}={v:.4f}")
        else:
            parts.append(f"{prefix}{k}={v}")
    return " ".join(parts)
