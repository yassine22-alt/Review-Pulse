"""An explicit draft/review/check workflow for compound regulations."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .context import ContextBundle, assemble_context
from .draft import draft_program
from .review import ReviewArtifact, approve_program, review_program
from .runtime import run_program
from .schema import Inputs, Program

app = typer.Typer(help="Interpret compound requirements; inspect drafts before approving.")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _program(path: Path) -> Program:
    data = _read(path)
    return Program.model_validate(data.get("program", data))


@app.command()
def demo(out: Path):
    """Write three compound demonstrations and twelve boundary/exception scenario results offline."""
    from ..rules.clauses import split_text
    from .examples import demonstrations, run_demonstration

    for example in demonstrations():
        folder = out / example["name"]
        results = run_demonstration(example)
        _write(folder / "program.json", example["program"])
        _write(folder / "inputs.json", example["inputs"])
        context = assemble_context(
            example["program"]["document"], example["source"], split_text(example["source"]), "1"
        )
        _write(folder / "context.json", context.model_dump(mode="json"))
        _write(folder / "scenarios.json", {"illustrative_only": True, "scenarios": results})
        if not all(result["matches"] for result in results):
            raise typer.BadParameter(f"demonstration failed: {example['name']}")
        typer.echo(f"{example['name']}: {len(results)} scenarios matched")


@app.command()
def context(document: Path, clause: str, out: Path, links: Path | None = None):
    """Collect a clause, its subitems, parents and explicit dependencies into reviewable JSON."""
    from ..rules.clauses import split_document

    text, clauses = split_document(document)
    bundle = assemble_context(str(document), text, clauses, clause, _read(links) if links else None)
    _write(out, bundle.model_dump(mode="json"))
    typer.echo(f"{len(bundle.clauses)} clauses; {len(bundle.missing)} unresolved references -> {out}")


@app.command()
def inputs(building: Path, out: Path, complete: bool = False):
    """Export facts from a saved building; --complete declares a reviewed complete inventory."""
    from ..schema import BuildingModel
    from .building import building_inputs

    model = BuildingModel.model_validate(_read(building))
    _write(out, building_inputs(model, complete=complete).model_dump())
    typer.echo(str(out))


@app.command()
def draft(
    context_file: Path, inputs_file: Path, out: Path, backend: str = "ollama", model: str | None = None
):
    """Draft using the existing Ollama/hosted client; this never approves the model output."""
    from ..rules.draft import make_client

    bundle = ContextBundle.model_validate(_read(context_file))
    evidence = Inputs.model_validate(_read(inputs_file))
    result = draft_program(bundle, evidence.bindings, list(evidence.collections), make_client(backend, model))
    _write(out, result)
    typer.echo(f"draft; {len(result['program']['unresolved'])} unresolved issues -> {out}")


@app.command()
def review(
    program_file: Path,
    context_file: Path,
    inputs_file: Path,
    out: Path,
    backend: str = "ollama",
    model: str | None = None,
):
    """Independently review semantics and bind the report to the exact interpretation."""
    from ..rules.draft import make_client

    result = review_program(
        _program(program_file),
        ContextBundle.model_validate(_read(context_file)),
        Inputs.model_validate(_read(inputs_file)),
        make_client(backend, model),
    )
    _write(out, result)
    typer.echo(f"{len(result['review']['issues'])} semantic issues -> {out}")


@app.command()
def approve(
    program_file: Path, context_file: Path, inputs_file: Path, review_file: Path, out: Path, reviewer: str
):
    """Record explicit reviewer acceptance after inspecting a draft and its scenario results."""
    program = _program(program_file)
    bundle = ContextBundle.model_validate(_read(context_file))
    evidence = Inputs.model_validate(_read(inputs_file))
    try:
        program = approve_program(
            program, bundle, evidence, ReviewArtifact.model_validate(_read(review_file)), reviewer
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _write(out, program.model_dump())
    typer.echo(f"approved -> {out}")


@app.command()
def check(
    program_file: Path, inputs_file: Path, out: Path, preview: bool = False, building: Path | None = None
):
    """Evaluate a program and save its outcome and evidence tree; no segmentation/model calls."""
    graph = None
    if building:
        from ..schema import BuildingModel
        from .building import building_graph

        graph = building_graph(BuildingModel.model_validate(_read(building)))
    result = run_program(
        _program(program_file), Inputs.model_validate(_read(inputs_file)), include_drafts=preview, graph=graph
    )
    _write(out, result)
    typer.echo(f"{result['outcome']} -> {out}")
