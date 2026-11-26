"""Accela Civic Platform, Document Review API (Automation 7.3.3.5 or later, agency apps, access token).

CONTRACT TESTED FROM DOCUMENTATION, NOT TESTED LIVE. We have no Accela tenant and no credentials. The shapes below follow
developer.accela.com/docs/construct-documentReview.html and the reference pages
v4.post.documentReview.documents.documentId.comments and v4.post.documentReview.records.recordId.documents.documentId.checkin,
read on 25 November 2026.

Calls:
  POST /v4/documentReview/documents/{documentId}/comments   JSON body: comment, pageNumber, status{value,text},
                                                            discipline{value,text}, createdBy, createdDate (all optional)
  POST /v4/documentReview/records/{recordId}/documents/{documentId}/checkin
                                                            multipart: uploadedFile (the PDF) and fileInfo (a JSON array string
                                                            with serviceProviderCode, fileName, type, resubmit, description)
Headers: `Authorization: <access token>` (the documentation shows the bare token, no "Bearer"), `x-accela-appid`, and
optionally `x-accela-agency` and `x-accela-environment`. The token comes from ACCELA_ACCESS_TOKEN (the office runs its own
OAuth login, see docs/progress/M26_connectors.md); ACCELA_APP_ID holds the app id.

Assumptions the documentation does not settle (a real office must confirm them on its test environment): that pageNumber counts
from 1; that the status and discipline values are the agency's configured values (we send them only when asked, with a map);
that createdBy/createdDate are best left to the server (we do not send them); the sample checkin uses `text/plain` as the part type
for a dummy file, we send `application/pdf` for a PDF.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .model import ReviewComment
from .transport import (
    ConnectorError,
    PostedLedger,
    RecordingTransport,
    Request,
    Response,
    Transport,
    UrllibTransport,
    env,
    send_with_retry,
)

DEFAULT_BASE = "https://apis.accela.com"


@dataclass
class PostResult:
    comment_id: str
    outcome: str                  # posted | dry_run | skipped_duplicate | skipped_changed | failed
    remote_id: str | int | None = None
    http_status: int | None = None
    detail: str = ""


class AccelaClient:
    def __init__(self, *, transport: Transport | None = None, dry_run: bool = True, access_token: str | None = None,
                 app_id: str | None = None, agency: str | None = None, environment: str | None = None,
                 base_url: str = DEFAULT_BASE, ledger: PostedLedger | None = None, retries: int = 3,
                 backoff: float = 0.5, sleep=None, status_map: dict[str, str] | None = None,
                 send_discipline: bool = False):
        self.dry_run = dry_run
        self.transport: Transport = RecordingTransport() if dry_run else (transport or UrllibTransport())
        self._token = access_token
        self._app_id = app_id
        self.agency, self.environment = agency, environment
        self.base = base_url.rstrip("/")
        self.ledger = ledger or PostedLedger()
        self.retries, self.backoff = retries, backoff
        self._sleep = sleep
        self.status_map, self.send_discipline = status_map or {}, send_discipline

    # -- request building ------------------------------------------------------------------------------------------
    def headers(self) -> dict[str, str]:
        token = self._token or (env("ACCELA_ACCESS_TOKEN") if not self.dry_run else "dry-run-token")
        app = self._app_id or (env("ACCELA_APP_ID") if not self.dry_run else "dry-run-app")
        h = {"Authorization": token, "x-accela-appid": app, "Accept": "application/json"}
        if self.agency:
            h["x-accela-agency"] = self.agency
        if self.environment:
            h["x-accela-environment"] = self.environment
        return h

    def comment_payload(self, c: ReviewComment) -> dict:
        body = {"comment": " ".join(filter(None, [f"{c.number}." if c.number else "", f"[{c.citation}]" if c.citation else "",
                                                  c.text]))}
        if c.page:
            body["pageNumber"] = c.page
        if c.state in self.status_map:
            body["status"] = {"value": self.status_map[c.state], "text": ""}
        if self.send_discipline and c.discipline:
            body["discipline"] = {"value": c.discipline, "text": ""}
        return body

    def _send(self, req: Request) -> Response:
        kw = {"sleep": self._sleep} if self._sleep else {}
        return send_with_retry(self.transport, req, retries=self.retries, backoff=self.backoff, **kw)

    # -- calls -----------------------------------------------------------------------------------------------------
    def post_comments(self, document_id: str, comments: list[ReviewComment]) -> list[PostResult]:
        """Post each comment once. A comment already posted (same id, same payload) is skipped; one posted before and
        changed since is reported `skipped_changed` and not reposted (updating needs PUT .../comments/{commentId})."""
        target = f"accela:{self.base}:doc{document_id}"
        url = f"{self.base}/v4/documentReview/documents/{document_id}/comments"
        out = []
        for c in comments:
            payload = self.comment_payload(c)
            seen = self.ledger.get(target, c.id)
            if seen:
                same = seen["hash"] == PostedLedger.digest(payload)
                out.append(PostResult(c.id, "skipped_duplicate" if same else "skipped_changed", seen["remote_id"]))
                continue
            resp = self._send(Request("POST", url, {**self.headers(), "Content-Type": "application/json"}, json=payload))
            if self.dry_run:
                out.append(PostResult(c.id, "dry_run", None, resp.status))
            elif resp.ok:
                remote = (resp.json().get("result") or {}).get("id")
                self.ledger.record(target, c.id, payload, remote)
                out.append(PostResult(c.id, "posted", remote, resp.status))
            else:
                out.append(PostResult(c.id, "failed", None, resp.status, resp.body[:200].decode("utf-8", "replace")))
        return out

    def checkin(self, record_id: str, document_id: str, pdf: str | Path | bytes, *, service_provider_code: str,
                file_name: str | None = None, resubmit: bool = False, description: str = "") -> PostResult:
        """Check the annotated PDF in as the next version of the reviewed document."""
        data = pdf if isinstance(pdf, bytes) else Path(pdf).read_bytes()
        name = file_name or (Path(pdf).name if not isinstance(pdf, bytes) else "reviewpulse.pdf")
        info = [{"serviceProviderCode": service_provider_code, "fileName": name, "type": "application/pdf",
                 "resubmit": "true" if resubmit else "false", "description": description or "ReviewPulse annotated set"}]
        target = f"accela:{self.base}:checkin:{record_id}/{document_id}"
        key = hashlib.sha256(data + json.dumps(info, sort_keys=True).encode()).hexdigest()[:16]
        if self.ledger.get(target, key):
            return PostResult(key, "skipped_duplicate", self.ledger.get(target, key)["remote_id"])
        url = f"{self.base}/v4/documentReview/records/{record_id}/documents/{document_id}/checkin"
        resp = self._send(Request("POST", url, self.headers(), multipart={
            "uploadedFile": (name, data, "application/pdf"), "fileInfo": (None, json.dumps(info), None)}))
        if self.dry_run:
            return PostResult(key, "dry_run", None, resp.status)
        if not resp.ok:
            return PostResult(key, "failed", None, resp.status, resp.body[:200].decode("utf-8", "replace"))
        result = resp.json().get("result")
        remote = result[0].get("id") if isinstance(result, list) and result else None
        self.ledger.record(target, key, key, remote)
        return PostResult(key, "posted", remote, resp.status)


def require_ok(results: list[PostResult]) -> None:
    bad = [r for r in results if r.outcome == "failed"]
    if bad:
        raise ConnectorError(f"{len(bad)} of {len(results)} comments failed, first: HTTP {bad[0].http_status}")
