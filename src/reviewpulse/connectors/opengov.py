"""OpenGov Permitting & Licensing (API v2, `https://api.plce.opengov.com/plce`).

CONTRACT TESTED FROM DOCUMENTATION, NOT TESTED LIVE. Read on 25 November 2026 from developer.opengov.com/catalog/plc-api
(record-workflow-step-comments, files, schema).

What exists. The public API has comments, but on WORKFLOW STEPS of a record, as plain text:
  POST /v2/{community}/records/{recordID}/workflow-steps/{stepID}/comments      permission "Comment Write"
  body (JSON:API, Content-Type application/vnd.api+json):
  {"data": {"type": "workflowStepComment", "attributes": {"commentType": "COMMENT", "comment": "..."}}}
So we can post each correction item as a step comment. What we cannot do: attach a comment to a page or a box of a document
(no field for it), or set a status. The page, sheet and code citation therefore go into the text. The documentation says step
comments are visible to public contacts of the record (applicant, guests) in v1; we have not confirmed that for v2, so treat
every comment as visible to the applicant. We know no value for an employee-only note, and we do not guess one.

Files: v2 has a two step upload (create a file entry, PUT to a pre signed Azure Blob URL) and association as a record attachment.
We read those pages only in outline, so this module does not upload the annotated PDF; use the file drop for that.

Auth. One page of the portal says "API Key", the schema and the v1 page say OAuth2 client credentials (token endpoint
accounts.viewpointcloud.com/oauth/token). The two disagree, so this module takes a ready bearer token from OPENGOV_ACCESS_TOKEN
and does not fetch one.
"""

from __future__ import annotations

from .accela import PostResult
from .model import ReviewComment
from .transport import (
    PostedLedger,
    RecordingTransport,
    Request,
    Response,
    Transport,
    UrllibTransport,
    env,
    send_with_retry,
)

BASE = "https://api.plce.opengov.com/plce"
CONTENT_TYPE = "application/vnd.api+json"


class OpenGovClient:
    def __init__(self, *, transport: Transport | None = None, dry_run: bool = True, community: str, access_token: str | None = None,
                 base_url: str = BASE, ledger: PostedLedger | None = None, retries: int = 3, backoff: float = 0.5, sleep=None):
        self.dry_run = dry_run
        self.transport: Transport = RecordingTransport(lambda r: Response(201, b'{"data": {"id": "dry-run"}}')) if dry_run \
            else (transport or UrllibTransport())
        self.community, self.base = community, base_url.rstrip("/")
        self._token = access_token
        self.ledger = ledger or PostedLedger()
        self.retries, self.backoff, self._sleep = retries, backoff, sleep

    @staticmethod
    def comment_text(c: ReviewComment) -> str:
        where = ", ".join(x for x in (f"sheet {c.sheet}" if c.sheet else "", f"page {c.page}" if c.page else "") if x)
        head = " ".join(x for x in (f"{c.number}." if c.number else "", f"[{c.citation}]" if c.citation else "") if x)
        return " ".join(x for x in (head, c.text, f"({where})" if where else "") if x)

    def payload(self, c: ReviewComment, comment_type: str = "COMMENT") -> dict:
        return {"data": {"type": "workflowStepComment",
                         "attributes": {"commentType": comment_type, "comment": self.comment_text(c)}}}

    def post_step_comments(self, record_id: str, step_id: str, comments: list[ReviewComment]) -> list[PostResult]:
        token = self._token or (env("OPENGOV_ACCESS_TOKEN") if not self.dry_run else "dry-run")
        url = f"{self.base}/v2/{self.community}/records/{record_id}/workflow-steps/{step_id}/comments"
        target = f"opengov:{self.community}:{record_id}/{step_id}"
        out = []
        for c in comments:
            body = self.payload(c)
            seen = self.ledger.get(target, c.id)
            if seen:
                same = seen["hash"] == PostedLedger.digest(body)
                out.append(PostResult(c.id, "skipped_duplicate" if same else "skipped_changed", seen["remote_id"]))
                continue
            kw = {"sleep": self._sleep} if self._sleep else {}
            resp = send_with_retry(self.transport, Request("POST", url, {"Authorization": f"Bearer {token}",
                                                                        "Content-Type": CONTENT_TYPE, "Accept": CONTENT_TYPE},
                                                          json=body), retries=self.retries, backoff=self.backoff, **kw)
            if self.dry_run:
                out.append(PostResult(c.id, "dry_run", None, resp.status))
            elif resp.status == 201:
                remote = (resp.json().get("data") or {}).get("id")
                self.ledger.record(target, c.id, body, remote)
                out.append(PostResult(c.id, "posted", remote, resp.status))
            else:
                out.append(PostResult(c.id, "failed", None, resp.status, resp.body[:200].decode("utf-8", "replace")))
        return out
