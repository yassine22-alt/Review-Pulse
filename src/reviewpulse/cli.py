"""rp - ReviewPulse command line (typer).

    rp inspect <file>                 -> runs/<id>/sheets.json
    rp extract <run>                  -> sheet_<n>.json, preview_<n>.png
    rp build <run>                    -> building_<n>.json, rooms_<n>.png
    rp check <run|file> --rules <pack> -> findings.json/.csv, report.pdf, report.html
    rp eval <task> --dataset <name>   -> reports/<date>_<task>_<method>.md, reports/results.csv
    rp synth <out>                    -> synthetic plans with exact truth
    rp rules validate|test <pack>
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .ingest.classify import IngestError
from .interpreter.cli import app as interpreter_app

app = typer.Typer(add_completion=False, help="ReviewPulse: automated error detection on architectural plans.")
rules_app = typer.Typer(help="Rule packs: validate, test, review.")
app.add_typer(rules_app, name="rules")
app.add_typer(interpreter_app, name="interpret")
# drawings carry any script (OCR'd labels, Arabic, CJK): a console or pipe with a narrow code page
# must show a replacement character, never crash the command
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
console = Console()

DEFAULT_PACK = Path(__file__).parent / "rules" / "packs" / "starter"


def _fail(msg: str, code: int = 2):
    console.print(f"[red]error:[/red] {msg}")
    raise typer.Exit(code)


def _calib(s: str | None):
    if not s:
        return None
    try:
        vals = tuple(float(v) for v in s.split(","))
        assert len(vals) == 5
        return vals
    except (ValueError, AssertionError):
        _fail("--calibrate expects x1,y1,x2,y2,metres")


@app.command()
def inspect(file: Path, runs: Path = typer.Option(Path("runs"), help="runs directory"),
            run_id: str | None = typer.Option(None, help="run folder name")):
    """Detect file type and per-page mode (vector / raster / mixed)."""
    from . import pipeline
    from .ingest.classify import read_sheets

    try:
        run_dir = pipeline.inspect(file, runs, run_id)
    except IngestError as e:
        _fail(str(e))
    t = Table("sheet", "type", "mode", "size", "rotation", "paths", "words", "layers", "warnings")
    for s in read_sheets(run_dir):
        size = f"{s.width_mm:.0f}x{s.height_mm:.0f} mm" if s.width_mm else "-"
        t.add_row(str(s.index), s.file_type, s.mode, size, str(s.rotation), str(s.n_path_items), str(s.n_words),
                  str(len(s.layers)), "; ".join(s.warnings))
    console.print(t)
    console.print(f"run: {run_dir}")


@app.command()
def extract(run: Path, units: str | None = typer.Option(None, help="DXF units override: mm|cm|m")):
    """Extract primitives, text and dimensions for every sheet of a run."""
    from . import pipeline

    try:
        for p in pipeline.extract(run, units):
            console.print(f"wrote {p}")
    except IngestError as e:
        _fail(str(e))


@app.command()
def build(run: Path, calibrate: str | None = typer.Option(None, help="x1,y1,x2,y2,metres in sheet units"),
          confirm: list[str] = typer.Option([], help="element id confirmed by a user")):
    """Scale, walls, openings, rooms, room graph, dimensions, schedules -> building model."""
    from . import pipeline
    from .schema import BuildingModel, load

    for p in pipeline.build(run, _calib(calibrate), set(confirm)):
        m = load(BuildingModel, p)
        n = {c: sum(1 for e in m.elements if e.cls == c) for c in ("wall", "door", "window", "opening", "column")}
        console.print(f"wrote {p}: tier {m.tier}, scale {m.sheet.scale.method} "
                      f"({m.sheet.scale.metres_per_unit}), {len(m.rooms)} rooms, {len(m.edges)} edges, {n}")
        for w in m.sheet.warnings:
            console.print(f"  [yellow]warning[/yellow] {w}")


@app.command()
def check(target: Path, rules: Path = typer.Option(DEFAULT_PACK, help="rule pack folder or file"),
          runs: Path = typer.Option(Path("runs")), units: str | None = typer.Option(None),
          calibrate: str | None = typer.Option(None),
          confirm: list[str] = typer.Option([], help="element id confirmed by the reviewer"),
          dismiss: list[str] = typer.Option([], help="<finding_id>:<reason>"),
          brief: Path | None = typer.Option(None, help="the project brief (programme): CSV, XLSX, DOCX, PDF or MD table")):
    """Run approved rules. TARGET is a run folder or a drawing file (runs the whole pipeline)."""
    from . import pipeline
    from .schema import load_findings

    try:
        if target.is_file():
            run_dir = pipeline.inspect(target, runs)
            pipeline.extract(run_dir, units)
            pipeline.build(run_dir, _calib(calibrate), set(confirm))
        else:
            run_dir = target
        if confirm or dismiss:
            pipeline.save_triage(run_dir, list(confirm), list(dismiss))
        summary = pipeline.check(run_dir, rules, set(confirm), brief=brief)
    except IngestError as e:
        _fail(str(e))
    findings = load_findings(run_dir / "findings.json")
    t = Table("id", "rule", "verdict", "tier", "message")
    style = {"FAIL": "red", "WARNING": "yellow", "PASS": "green", "NOT_EVALUATED": "dim"}
    for f in findings:
        if f.verdict == "PASS":
            continue
        t.add_row(f.evidence.get("finding_id", ""), f.rule_id, f"[{style[f.verdict]}]{f.verdict}[/]", f.tier,
                  f.message[:140])
    console.print(t)
    console.print(f"summary: {summary}")
    console.print(f"reports: {run_dir / 'report.pdf'}  {run_dir / 'report.html'}")


@app.command()
def synth(out: Path, n: int = typer.Option(1), seed: int = typer.Option(0),
          errors: list[str] = typer.Option([], help="planted error switch (repeatable)"),
          denominator: int = typer.Option(100), rotate: int = typer.Option(0),
          strip_layers: bool = typer.Option(False), suite: bool = typer.Option(False, help="fixed 120-plan suite")):
    """Generate synthetic plans (DXF + PDF + PNG + truth.json)."""
    from .synth.make_plan import ERRORS, make_plan, make_suite

    bad = [e for e in errors if e not in ERRORS]
    if bad:
        _fail(f"unknown errors {bad}; choose from {sorted(ERRORS)}")
    if suite:
        res = make_suite(out, n if n > 1 else 120)
        console.print(f"wrote {len(res)} plans to {out}")
        return
    for i in range(n):
        p = make_plan(out, seed=seed + i, errors=tuple(errors), denominator=denominator, rotate=rotate,
                      strip_layers=strip_layers)
        console.print(p)


@app.command("eval")
def eval_(task: str = typer.Argument(..., help="prims|walls|openings|rooms|scale|findings"),
          dataset: str = typer.Option("synth"), n: int = typer.Option(30), method: str = typer.Option("rules"),
          oracle: str = typer.Option("off", help="comma list of true inputs, e.g. walls,doors"),
          out: Path = typer.Option(Path("reports")), data: Path = typer.Option(Path("data"))):
    """Score a stage against ground truth and write a report (task 'drafting' scores the LLM, I4)."""
    from .eval.cli import run_eval, write_report

    if task == "drafting":
        from .eval.drafting import run_drafting_eval
        from .rules.draft import make_client

        backend, _, model = method.partition(":") if method != "rules" else ("ollama", "", "")
        client = make_client(backend, model or None)
        res, rows = run_drafting_eval(client)
        path, row = write_report("drafting", "i4_gold", f"{backend}-{client.model}".replace(":", "_"),
                                 res["all"]["clauses"], "off", res, rows, out)
        console.print(row)
        console.print(f"report: {path}")
        return
    try:
        path, row = run_eval(task, dataset, n=n, method=method, oracle=oracle, out_dir=out, data_dir=data)
    except NotImplementedError as e:
        _fail(str(e), 1)
    console.print(row)
    console.print(f"report: {path}")


@rules_app.command("validate")
def rules_validate(pack: Path = typer.Argument(DEFAULT_PACK)):
    """Validate every rule of a pack against the schema, vocabulary and registry."""
    from .rules.schema import RuleError, load_pack

    try:
        rs = load_pack(pack)
    except RuleError as e:
        _fail(str(e), 1)
    console.print(f"{len(rs)} rules valid ({sum(r.status == 'approved' for r in rs)} approved)")


@rules_app.command("clauses")
def rules_clauses(doc: Path, out: Path = typer.Option(None, help="clauses.json path")):
    """I3: split a requirement document (PDF / Markdown / text) into clauses with offsets."""
    from .rules.clauses import write_clauses

    out = out or Path("drafts") / f"{doc.stem}.clauses.json"
    p = write_clauses(doc, out)
    import json

    n = len(json.loads(p.read_text(encoding="utf-8"))["clauses"])
    console.print(f"{n} clauses -> {p}")


@rules_app.command("draft")
def rules_draft(doc: Path, out: Path = typer.Option(Path("drafts")),
                backend: str = typer.Option("ollama", help="ollama (local, free) | claude (hosted, paid)"),
                model: str = typer.Option(None, help="model id (default qwen2.5:7b for ollama)"),
                only: list[str] = typer.Option([], help="clause id to draft (repeatable)")):
    """I4: draft rules from a requirement document with an LLM (clause text only; local by default)."""
    from .rules.draft import OllamaClient, draft_document, load_drafts, make_client

    try:
        client = make_client(backend, model)
    except ImportError:
        _fail('the claude backend needs: pip install -e ".[llm]"', 1)
    if isinstance(client, OllamaClient) and not client.available():
        _fail(f"Ollama model {client.model} not available at {client.host}: install Ollama "
              f"(https://ollama.com), then `ollama pull {client.model}`", 1)
    p = draft_document(doc, client, out, only=list(only) or None)
    drafts = load_drafts(p)
    t = Table("clause", "checkable", "rule", "errors / flags")
    for d in drafts:
        t.add_row(d.clause_id, d.checkable, (d.rule or {}).get("id", "-"), "; ".join(d.errors + d.flags)[:90])
    console.print(t)
    console.print(f"drafts -> {p}  (review with: rp rules review {p} --pack <pack dir>)")


@rules_app.command("review")
def rules_review(drafts: Path, pack: Path = typer.Option(..., help="pack folder that receives approved rules"),
                 curator: str = typer.Option(..., prompt=True, help="your name, stored as approved_by")):
    """I5: curator review - approve / edit / reject each draft; approval requires a passing self-test."""
    import yaml

    from .rules.draft import load_drafts
    from .rules.review import approve
    from .rules.schema import load_pack

    base = load_pack(DEFAULT_PACK)
    for d in load_drafts(drafts):
        console.rule(f"{d.clause_id}  ({d.checkable})")
        console.print(d.clause_text)
        if d.rule is None:
            console.print(f"[dim]no rule: {d.rationale}[/dim]")
            continue
        for e in d.errors:
            console.print(f"[red]error:[/red] {e}")
        for f in d.flags:
            console.print(f"[yellow]flag:[/yellow] {f}")
        rule = d.rule
        while True:
            console.print(yaml.safe_dump(rule, sort_keys=False, allow_unicode=True))
            act = typer.prompt("[a]pprove [e]dit [r]eject [s]kip [q]uit", default="s").lower()[:1]
            if act == "e":
                edited = typer.edit(yaml.safe_dump(rule, sort_keys=False, allow_unicode=True), extension=".yaml")
                if edited:
                    rule = yaml.safe_load(edited)
                continue
            if act == "a":
                try:
                    ok, msg = approve(rule, pack, curator, base)
                except Exception as e:  # noqa: BLE001 - show validation errors and keep reviewing
                    ok, msg = False, f"invalid rule: {e}"
                console.print(("[green]" if ok else "[red]") + msg + "[/]")
                if ok:
                    break
                continue
            if act == "q":
                return
            break


@rules_app.command("test")
def rules_test(pack: Path = typer.Argument(DEFAULT_PACK), out: Path = typer.Option(Path("reports/rule_tests.md"))):
    """Run each rule on generated passing/failing plans (I5)."""
    from .rules.tester import test_pack

    ok, report = test_pack(pack, out)
    console.print(report)
    if not ok:
        raise typer.Exit(1)


@app.command()
def serve(host: str = typer.Option("127.0.0.1", help="interface to listen on (0.0.0.0 in a container)"),
          port: int = typer.Option(8000), data: Path = typer.Option(Path("data/app"), help="projects folder"),
          workers: int = typer.Option(2, help="background jobs that may run at once")):
    """Run the ReviewPulse web app (projects, uploads, rule review, results) on http://HOST:PORT."""
    try:
        import uvicorn

        from .app.api import create_app
    except ImportError:
        _fail('the web app needs: pip install -e ".[app]"', 1)
    console.print(f"ReviewPulse on http://{host}:{port}  (projects in {data.resolve()})")
    uvicorn.run(create_app(data, workers=workers), host=host, port=port, log_level="info")


@app.command()
def doctor():
    """Check this installation: packages, a generated plan with planted errors, and the web app."""
    from .selfcheck import run

    raise typer.Exit(run())


def main():  # pragma: no cover
    try:
        app()
    except IngestError as e:
        console.print(f"[red]error:[/red] {e}")
        sys.exit(2)


if __name__ == "__main__":  # pragma: no cover
    main()
