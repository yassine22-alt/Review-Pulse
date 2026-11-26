"""HTTP plumbing shared by the vendor connectors: an injectable transport, retries with backoff, a dry run, idempotency.

Nothing here opens a network connection unless a connector is given `UrllibTransport`. Tests and dry runs use
`RecordingTransport` or `FixtureTransport`. Secrets are read from the environment by the connectors, are redacted in every
record this module keeps, and are never written to disk (the idempotency ledger stores comment ids and hashes only).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

SECRET_HEADERS = {"authorization", "x-accela-appsecret", "x-api-key", "cookie"}
SECRET_FIELDS = {"client_secret", "refresh_token", "access_token", "password", "code"}
RETRY_STATUS = {429, 502, 503, 504}


class ConnectorError(RuntimeError):
    pass


def env(name: str, *, required: bool = True) -> str:
    """A secret or setting from the environment. The value is never logged by this package."""
    value = os.environ.get(name, "")
    if required and not value:
        raise ConnectorError(f"environment variable {name} is not set")
    return value


@dataclass
class Request:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    json: object | None = None
    form: dict[str, str] | None = None                       # application/x-www-form-urlencoded
    multipart: dict[str, tuple] | None = None                # name -> (filename or None, bytes or str, content type)
    body: bytes | None = None                                # raw bytes (storage upload)


@dataclass
class Response:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8")) if self.body else {}
        except ValueError:
            return {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class Transport(Protocol):
    def send(self, req: Request) -> Response: ...


def redact(req: Request) -> dict:
    """What a request looks like in a log or a dry run record: secrets masked, file bytes replaced by size and hash."""
    headers = {k: ("***" if k.lower() in SECRET_HEADERS else v) for k, v in req.headers.items()}
    rec: dict = {"method": req.method, "url": req.url, "headers": headers}
    if req.json is not None:
        rec["json"] = req.json
    if req.form is not None:
        rec["form"] = {k: ("***" if k in SECRET_FIELDS else v) for k, v in req.form.items()}
    if req.multipart is not None:
        parts = {}
        for name, (fname, data, ctype) in req.multipart.items():
            raw = data if isinstance(data, bytes) else str(data).encode("utf-8")
            parts[name] = {"filename": fname, "content_type": ctype, "bytes": len(raw),
                           "sha256": hashlib.sha256(raw).hexdigest()[:16]} if fname else {"value": data}
        rec["multipart"] = parts
    if req.body is not None:
        rec["body"] = {"bytes": len(req.body), "sha256": hashlib.sha256(req.body).hexdigest()[:16]}
    return rec


def _multipart(parts: dict[str, tuple]) -> tuple[bytes, str]:
    boundary = "----reviewpulse" + uuid.uuid4().hex
    out = bytearray()
    for name, (fname, data, ctype) in parts.items():
        raw = data if isinstance(data, bytes) else str(data).encode("utf-8")
        disp = f'form-data; name="{name}"' + (f'; filename="{fname}"' if fname else "")
        out += f"--{boundary}\r\nContent-Disposition: {disp}\r\n".encode()
        if ctype:
            out += f"Content-Type: {ctype}\r\n".encode()
        out += b"\r\n" + raw + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


class UrllibTransport:
    """The real transport (standard library only). Not used by any test."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def send(self, req: Request) -> Response:
        headers = dict(req.headers)
        data = req.body
        if req.json is not None:
            data = json.dumps(req.json).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif req.form is not None:
            data = urllib.parse.urlencode(req.form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif req.multipart is not None:
            data, headers["Content-Type"] = _multipart(req.multipart)
        r = urllib.request.Request(req.url, data=data, headers=headers, method=req.method)
        try:
            with urllib.request.urlopen(r, timeout=self.timeout) as resp:   # noqa: S310 (https URLs from connector config)
                return Response(resp.status, resp.read(), dict(resp.headers))
        except urllib.error.HTTPError as exc:
            return Response(exc.code, exc.read(), dict(exc.headers))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ConnectionError(str(exc)) from exc


class RecordingTransport:
    """Records every request (redacted) and answers from `responder(req)`; with no responder it answers 200 with a
    `dry_run` marker. This is the dry run: nothing leaves the machine."""

    def __init__(self, responder: Callable[[Request], Response] | None = None):
        self.responder = responder
        self.sent: list[dict] = []

    def send(self, req: Request) -> Response:
        self.sent.append(redact(req))
        if self.responder:
            return self.responder(req)
        return Response(200, json.dumps({"dry_run": True}).encode())


class FixtureTransport:
    """Answers from recorded fixtures: a list of `(method, url regex, Response or callable)`, first match wins; every
    request is kept redacted in `.sent` and unredacted in `.raw` (tests only, to check headers). An unmatched request raises,
    so a test can never reach the network."""

    def __init__(self, routes: list[tuple[str, str, Response | Callable[[Request], Response]]]):
        self.routes = routes
        self.sent: list[dict] = []
        self.raw: list[Request] = []

    def send(self, req: Request) -> Response:
        self.sent.append(redact(req))
        self.raw.append(req)
        for method, pattern, answer in self.routes:
            if method == req.method and re.search(pattern, req.url):
                if callable(answer):
                    return answer(req)
                if isinstance(answer, list):
                    return answer.pop(0) if len(answer) > 1 else answer[0]
                return answer
        raise ConnectionError(f"no fixture for {req.method} {req.url}")


def send_with_retry(transport: Transport, req: Request, *, retries: int = 3, backoff: float = 0.5,
                    sleep: Callable[[float], None] = time.sleep) -> Response:
    """Send, retrying network errors and 429/502/503/504 with exponential backoff (honours Retry-After, in seconds).

    A POST that timed out may have been applied by the server; a retry can then create a duplicate. The idempotency ledger
    prevents duplicates across runs, not inside one retried call (none of the vendors documents an idempotency key)."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = transport.send(req)
        except ConnectionError as exc:
            last, resp = exc, None
        if resp is not None and resp.status not in RETRY_STATUS:
            return resp
        if attempt == retries:
            if resp is not None:
                return resp
            raise ConnectorError(f"{req.method} {req.url}: {last}") from last
        wait = backoff * (2 ** attempt)
        if resp is not None:
            ra = resp.headers.get("Retry-After", "")
            wait = max(wait, float(ra)) if ra.replace(".", "", 1).isdigit() else wait
        sleep(min(wait, 60.0))
    raise AssertionError("unreachable")


class PostedLedger:
    """Remembers which comments were already sent where, so a second run never posts the same comment twice.

    Keys are `<target>|<comment id>`; values hold the payload hash and the remote id. With a path the ledger is a small JSON
    file written after each success (no secrets inside); without one it lives in memory."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.data: dict[str, dict] = {}
        if self.path and self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def digest(payload) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def get(self, target: str, cid: str) -> dict | None:
        return self.data.get(f"{target}|{cid}")

    def record(self, target: str, cid: str, payload, remote_id) -> None:
        self.data[f"{target}|{cid}"] = {"hash": self.digest(payload), "remote_id": remote_id}
        if self.path:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
            tmp.replace(self.path)
