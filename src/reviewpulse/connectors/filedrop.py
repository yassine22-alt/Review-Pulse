"""The generic path for offices with no API: a JSON file, a CSV file, a drop folder, or a signed webhook.

These are our own formats, so there is nothing to be "tested against documentation": the tests read back what is written. What
we cannot say is that any office system accepts the files; the office must map the columns.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

from .model import STATES, ReviewComment, dump, load
from .transport import RecordingTransport, Request, Response, Transport, UrllibTransport, env, send_with_retry

CSV_COLUMNS = ["number", "id", "discipline", "citation", "text", "sheet", "page", "x0", "y0", "x1", "y1", "state", "severity",
               "evidence_quote", "detected", "required", "cycle", "author", "created"]


def write_json(comments: list[ReviewComment], out: str | Path) -> Path:
    out = Path(out)
    out.write_text(json.dumps(dump(comments), indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def read_json(path: str | Path) -> list[ReviewComment]:
    return load(json.loads(Path(path).read_text(encoding="utf-8")))


def write_csv(comments: list[ReviewComment], out: str | Path) -> Path:
    out = Path(out)
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:        # BOM so Excel reads accents
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for c in comments:
            b = c.bbox or ["", "", "", ""]
            w.writerow([c.number, c.id, c.discipline, c.citation, c.text, c.sheet, c.page or "", *b, c.state, c.severity,
                        c.evidence_quote, c.source_facts.get("detected", ""), c.source_facts.get("required", ""), c.cycle,
                        c.author, c.created])
    return out


def read_csv(path: str | Path) -> list[ReviewComment]:
    """Read our CSV back (also a hand edited copy). Columns we do not know are ignored; the state must be one of ours."""
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            state = row.get("state") or "open"
            if state not in STATES:
                raise ValueError(f"unknown state {state!r} in row {row.get('number')}")
            bbox = [float(row[k]) for k in ("x0", "y0", "x1", "y1")] if all(row.get(k) for k in ("x0", "y0", "x1", "y1")) else None
            page = int(row["page"]) if row.get("page") else None
            facts = {k: row[k] for k in ("detected", "required") if row.get(k)}
            out.append(ReviewComment(
                id=row.get("id") or f"csv-{row.get('number')}", number=int(row.get("number") or 0),
                discipline=row.get("discipline", ""), citation=row.get("citation", ""), text=row.get("text", ""),
                sheet=row.get("sheet", ""), page=page, bbox=bbox, located=bool(page and bbox), state=state,
                severity=row.get("severity", ""), evidence_quote=row.get("evidence_quote", ""), source_facts=facts,
                cycle=int(row.get("cycle") or 1), author=row.get("author", ""), created=row.get("created", ""), origin="csv"))
    return out


def drop(comments: list[ReviewComment], folder: str | Path, *, project: str = "project") -> list[Path]:
    """Write `<project>_<time>.json` and `.csv` into a folder another system watches. Each file is written under a
    temporary name and renamed, so a watcher never sees half a file."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    paths = []
    for ext, writer in (("json", write_json), ("csv", write_csv)):
        final = folder / f"{project}_{stamp}.{ext}"
        tmp = folder / f".{final.name}.part"
        writer(comments, tmp)
        tmp.replace(final)
        paths.append(final)
    return paths


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(body: bytes, signature: str, secret: str) -> bool:
    return hmac.compare_digest(sign(body, secret), signature)


def post_webhook(comments: list[ReviewComment], url: str, *, transport: Transport | None = None, dry_run: bool = True,
                 secret: str | None = None) -> Response:
    """POST the comments file as JSON to a URL. The body is signed (HMAC SHA256, header `X-ReviewPulse-Signature`) with the
    secret from REVIEWPULSE_WEBHOOK_SECRET so the receiver can check where it came from. One POST for the whole list."""
    body = json.dumps(dump(comments), ensure_ascii=False).encode("utf-8")
    key = secret or (env("REVIEWPULSE_WEBHOOK_SECRET") if not dry_run else "dry-run")
    t = RecordingTransport() if dry_run else (transport or UrllibTransport())
    headers = {"Content-Type": "application/json", "X-ReviewPulse-Signature": sign(body, key)}
    resp = send_with_retry(t, Request("POST", url, headers, body=body))
    if dry_run:
        resp.headers["recorded"] = json.dumps(t.sent[-1]) if isinstance(t, RecordingTransport) else ""
    return resp

