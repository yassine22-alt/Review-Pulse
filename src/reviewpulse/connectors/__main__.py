"""`python -m reviewpulse.connectors export --project <dir> --format pdf|bcf|json|csv` and friends."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bcf, filedrop, pdf_io
from .model import ReviewComment, from_findings


def load_project(project: Path, *, cycle: int = 1, author: str = "ReviewPulse", include_pass: bool = False,
                 pdf: Path | None = None) -> tuple[list[ReviewComment], Path | None]:
    """Findings of a project folder (`run/findings.json`, or the folder is the run folder) as comments, and its source PDF."""
    run = project / "run" if (project / "run").is_dir() else project
    findings_file = run / "findings.json"
    if not findings_file.exists():
        raise SystemExit(f"no findings.json in {run}")
    findings = json.loads(findings_file.read_text(encoding="utf-8"))
    if isinstance(findings, dict):
        findings = findings.get("findings", [])
    sheets: dict[str, dict] = {}
    source: Path | None = pdf
    for b in sorted(run.glob("building_*.json")):
        sheet = json.loads(b.read_text(encoding="utf-8")).get("sheet", {})
        src = Path(sheet.get("source_file", ""))
        if not src.is_absolute() and not src.exists() and (project / src).exists():
            src = project / src
        if src.suffix.lower() == ".pdf" and src.exists():
            import pymupdf

            with pymupdf.open(str(src)) as d:
                height = d[sheet.get("page", 0)].mediabox_size[1]
            sheets[sheet["id"]] = {"page": sheet.get("page", 0), "height_pt": height}
            source = source or src
    return from_findings(findings, sheets=sheets, cycle=cycle, author=author, include_pass=include_pass), source


def _export(a) -> int:
    comments, source = load_project(Path(a.project), cycle=a.cycle, author=a.author, include_pass=a.include_pass,
                                    pdf=Path(a.pdf) if a.pdf else None)
    out = Path(a.out) if a.out else Path(a.project) / f"reviewpulse_comments.{a.format if a.format != 'bcf' else 'bcf'}"
    if a.format == "json":
        filedrop.write_json(comments, out)
    elif a.format == "csv":
        filedrop.write_csv(comments, out)
    elif a.format == "pdf":
        if not source:
            raise SystemExit("format pdf needs the source PDF: pass --pdf plan.pdf")
        res = pdf_io.write_annotations(source, out, comments, author=a.author)
        print(f"annotated {res.written} comments ({res.unlocated} without a place on the page); warnings: {len(res.warnings)}")
    else:
        snaps = {}
        if source:
            for c in comments:
                if c.located and c.bbox:
                    snaps[c.id] = pdf_io.render_crop(source, c.page, c.bbox)
        bcf.export_bcf(comments, out, project_name=Path(a.project).name, pdf_name=source.name if source else "", snapshots=snaps)
    print(f"{len(comments)} comments -> {out}")
    return 0


def _read(a) -> int:
    res = pdf_io.read_annotations(a.pdf, cycle=a.cycle)
    out = Path(a.out) if a.out else Path(a.pdf).with_suffix(".comments.json")
    filedrop.write_json(res.comments, out)
    print(f"{len(res.comments)} markups of {res.annotations_seen} annotations -> {out}; warnings: {len(res.warnings)}")
    for w in res.warnings:
        print("  warning:", w)
    return 0


def _push(a) -> int:
    from .accela import AccelaClient
    from .bluebeam import BluebeamClient
    from .opengov import OpenGovClient
    from .transport import PostedLedger

    comments = filedrop.read_json(a.comments)
    dry = not a.live
    ledger = PostedLedger(a.ledger) if a.ledger else None
    if a.target == "accela":
        client = AccelaClient(dry_run=dry, ledger=ledger)
        results = client.post_comments(a.document_id, comments)
        print(json.dumps([r.__dict__ for r in results], indent=1))
        if dry:
            print(json.dumps(client.transport.sent, indent=1))
    elif a.target == "opengov":
        client = OpenGovClient(dry_run=dry, community=a.community, ledger=ledger)
        results = client.post_step_comments(a.record_id, a.step_id, comments)
        print(json.dumps([r.__dict__ for r in results], indent=1))
    elif a.target == "bluebeam":
        if not a.pdf:
            raise SystemExit("bluebeam needs --pdf (the annotated PDF to upload)")
        client = BluebeamClient(dry_run=dry)
        print(json.dumps(client.publish(a.session_name, a.pdf, a.invite or []), indent=1))
        if dry:
            print(json.dumps(client.transport.sent, indent=1))
    elif a.target == "webhook":
        resp = filedrop.post_webhook(comments, a.url, dry_run=dry)
        print("HTTP", resp.status)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m reviewpulse.connectors")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="write a project's findings as PDF markups, BCF, JSON or CSV")
    e.add_argument("--project", required=True)
    e.add_argument("--format", required=True, choices=["pdf", "bcf", "json", "csv"])
    e.add_argument("--out")
    e.add_argument("--pdf", help="source PDF when the project does not name one")
    e.add_argument("--cycle", type=int, default=1)
    e.add_argument("--author", default="ReviewPulse")
    e.add_argument("--include-pass", action="store_true")
    e.set_defaults(fn=_export)
    r = sub.add_parser("read-markups", help="read the markups of an annotated PDF into a comments JSON file")
    r.add_argument("pdf")
    r.add_argument("--out")
    r.add_argument("--cycle", type=int, default=1)
    r.set_defaults(fn=_read)
    p = sub.add_parser("push", help="send a comments JSON file to a system (dry run unless --live)")
    p.add_argument("target", choices=["accela", "bluebeam", "opengov", "webhook"])
    p.add_argument("comments")
    p.add_argument("--live", action="store_true", help="really send; tokens come from the environment")
    p.add_argument("--ledger", help="JSON file that remembers what was already sent")
    p.add_argument("--document-id")
    p.add_argument("--community")
    p.add_argument("--record-id")
    p.add_argument("--step-id")
    p.add_argument("--pdf")
    p.add_argument("--session-name", default="ReviewPulse plan review")
    p.add_argument("--invite", nargs="*")
    p.add_argument("--url")
    p.set_defaults(fn=_push)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
