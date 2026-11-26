"""Bluebeam Studio (Studio API, `/publicapi/v1`).

CONTRACT TESTED FROM DOCUMENTATION, NOT TESTED LIVE. No Bluebeam developer account or credentials were available. Shapes follow
support.bluebeam.com/developer/studio-session-guide.html and authentication-guide.html, read on 25 November 2026.

What the API gives us and what it does not. The documented calls create a session, add a PDF in three steps, invite or add
users, finalize, snapshot and close. Creating markups through the API is NOT documented. So the supported path is the one
we use: write our findings into our own copy of the PDF as standard annotations (pdf_io.write_annotations) and upload that
PDF, so the markups arrive inside the file and show in the Markups list of the session.

Calls (base `https://api.bluebeam.com`, or the regional host, see REGIONS):
  POST   /publicapi/v1/sessions                                 {Name, Notification, Restricted, SessionEndDate, DefaultPermissions}
  POST   /publicapi/v1/sessions/{id}/files                      {Name (ends .pdf), Source, Size, CRC}  -> {Id, UploadUrl, UploadContentType}
  PUT    <UploadUrl>                                            PDF bytes; x-amz-server-side-encryption: AES256; no Bluebeam token
  POST   /publicapi/v1/sessions/{id}/files/{fileId}/confirm-upload   -> 204
  POST   /publicapi/v1/sessions/{id}/invite                     {Email, Message} -> 204
  POST   /publicapi/v1/sessions/{id}/users                      {Email, SendEmail, Message} -> 204
  PUT    /publicapi/v1/sessions/{id}                            {Status: "Finalizing"}
  POST   /publicapi/v1/sessions/{id}/files/{fileId}/snapshot    then GET the same path until Status is Complete (DownloadUrl)
  DELETE /publicapi/v1/sessions/{id}
Headers on API calls: `Authorization: Bearer <token>` (capital B) and `client_id`.

Auth. The guide documents the Authorization Code flow (a user signs in once) and the refresh token grant. We implement the
refresh grant: BLUEBEAM_CLIENT_ID, BLUEBEAM_CLIENT_SECRET and BLUEBEAM_REFRESH_TOKEN from the environment, or a ready
BLUEBEAM_ACCESS_TOKEN. Every refresh returns a NEW refresh token (unused for 7 days it dies); we hand it to `on_refresh_token`
and never store it ourselves. A client credentials grant is not in the guide, so we do not use one.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path

from .transport import (
    ConnectorError,
    RecordingTransport,
    Request,
    Response,
    Transport,
    UrllibTransport,
    env,
    send_with_retry,
)

REGIONS = {"US": "https://api.bluebeam.com", "DE": "https://api.bluebeamstudio.de",
           "AU": "https://api.bluebeamstudio.com.au", "UK": "https://api.bluebeamstudio.co.uk",
           "SE": "https://api.bluebeamstudio.se"}
API = "/publicapi/v1"


def _dry_responder(req: Request) -> Response:
    """Plausible answers for a dry run, so the multi step flow can run to its end without a server."""
    import json

    u = req.url
    if u.endswith("/oauth2/token"):
        return Response(200, json.dumps({"token_type": "Bearer", "expires_in": 3600, "access_token": "dry-run",
                                         "refresh_token": "dry-run"}).encode())
    if u.endswith(f"{API}/sessions") and req.method == "POST":
        return Response(200, json.dumps({"Id": "dry-run-session"}).encode())
    if u.endswith("/files") and req.method == "POST":
        return Response(200, json.dumps({"Id": 1, "UploadUrl": "https://storage.example.invalid/upload",
                                         "UploadContentType": "application/pdf"}).encode())
    if u.endswith("/snapshot") and req.method == "GET":
        return Response(200, json.dumps({"Status": "Complete", "DownloadUrl": "https://storage.example.invalid/dl"}).encode())
    return Response(204 if req.method in ("POST", "DELETE") else 200)


class BluebeamClient:
    def __init__(self, *, transport: Transport | None = None, dry_run: bool = True, region: str = "US",
                 client_id: str | None = None, client_secret: str | None = None, refresh_token: str | None = None,
                 access_token: str | None = None, on_refresh_token: Callable[[str], None] | None = None,
                 retries: int = 3, backoff: float = 0.5, sleep=None):
        if region not in REGIONS:
            raise ConnectorError(f"unknown Bluebeam region {region!r}, use one of {sorted(REGIONS)}")
        self.dry_run = dry_run
        self.transport: Transport = RecordingTransport(_dry_responder) if dry_run else (transport or UrllibTransport())
        self.base = REGIONS[region]
        self._cid, self._secret, self._refresh = client_id, client_secret, refresh_token
        self._access = access_token
        self.on_refresh_token = on_refresh_token
        self.retries, self.backoff, self._sleep = retries, backoff, sleep

    def _send(self, req: Request) -> Response:
        kw = {"sleep": self._sleep} if self._sleep else {}
        return send_with_retry(self.transport, req, retries=self.retries, backoff=self.backoff, **kw)

    # -- auth ------------------------------------------------------------------------------------------------------
    def _client_id(self) -> str:
        return self._cid or (env("BLUEBEAM_CLIENT_ID") if not self.dry_run else "dry-run-client")

    def refresh_access_token(self) -> str:
        cid = self._client_id()
        secret = self._secret or (env("BLUEBEAM_CLIENT_SECRET") if not self.dry_run else "dry-run-secret")
        refresh = self._refresh or (env("BLUEBEAM_REFRESH_TOKEN") if not self.dry_run else "dry-run-refresh")
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        resp = self._send(Request("POST", f"{self.base}/oauth2/token", {"Authorization": f"Basic {basic}"},
                                  form={"grant_type": "refresh_token", "refresh_token": refresh}))
        if not resp.ok:
            raise ConnectorError(f"Bluebeam token refresh failed: HTTP {resp.status}")
        data = resp.json()
        self._access = data["access_token"]
        if data.get("refresh_token"):
            self._refresh = data["refresh_token"]
            if self.on_refresh_token:
                self.on_refresh_token(data["refresh_token"])
        return self._access

    def _headers(self) -> dict[str, str]:
        if not self._access:
            token = env("BLUEBEAM_ACCESS_TOKEN", required=False)
            if token:
                self._access = token
            else:
                self.refresh_access_token()
        return {"Authorization": f"Bearer {self._access}", "client_id": self._client_id(), "Content-Type": "application/json"}

    def _call(self, method: str, path: str, **kw) -> Response:
        resp = self._send(Request(method, f"{self.base}{API}{path}", self._headers(), **kw))
        if not resp.ok:
            raise ConnectorError(f"Bluebeam {method} {path}: HTTP {resp.status}")
        return resp

    # -- session ---------------------------------------------------------------------------------------------------
    def create_session(self, name: str, *, notification: bool = True, restricted: bool = False,
                       end_date: str | None = None, permissions: dict[str, str] | None = None) -> str:
        """`permissions` maps a type (SaveCopy, PrintCopy, Markup, AddDocuments, FullControl, MarkupAlert) to Allow, Deny or
        Default. The API default is Deny, so a reviewer session needs `{"Markup": "Allow"}` at least."""
        body: dict = {"Name": name, "Notification": notification, "Restricted": restricted,
                      "DefaultPermissions": [{"Type": k, "Allow": v} for k, v in (permissions or {"Markup": "Allow"}).items()]}
        if end_date:
            body["SessionEndDate"] = end_date
        return str(self._call("POST", "/sessions", json=body).json()["Id"])

    def add_pdf(self, session_id: str, pdf: str | Path | bytes, *, name: str | None = None, source: str = "ReviewPulse") -> int:
        """The three steps: metadata block, upload to storage, confirm. Returns the Studio file id."""
        data = pdf if isinstance(pdf, bytes) else Path(pdf).read_bytes()
        name = name or (Path(pdf).name if not isinstance(pdf, bytes) else "reviewpulse.pdf")
        if not name.lower().endswith(".pdf"):
            raise ConnectorError("Bluebeam requires the file name to end in .pdf")
        meta = self._call("POST", f"/sessions/{session_id}/files",
                          json={"Name": name, "Source": source, "Size": None, "CRC": None}).json()
        # storage upload: a pre signed URL, so no Bluebeam token goes to that host
        up = self._send(Request("PUT", meta["UploadUrl"], {"x-amz-server-side-encryption": "AES256",
                                                           "Content-Type": "application/pdf"}, body=data))
        if not up.ok:
            raise ConnectorError(f"Bluebeam storage upload: HTTP {up.status}")
        self._call("POST", f"/sessions/{session_id}/files/{meta['Id']}/confirm-upload")
        return int(meta["Id"])

    def invite(self, session_id: str, emails: list[str], message: str = "") -> None:
        for e in emails:
            self._call("POST", f"/sessions/{session_id}/invite", json={"Email": e, "Message": message})

    def add_users(self, session_id: str, emails: list[str], message: str = "", send_email: bool = True) -> None:
        for e in emails:
            self._call("POST", f"/sessions/{session_id}/users", json={"Email": e, "SendEmail": send_email, "Message": message})

    def finalize(self, session_id: str) -> None:
        self._call("PUT", f"/sessions/{session_id}", json={"Status": "Finalizing"})

    def snapshot(self, session_id: str, file_id: int, *, attempts: int = 30, wait: float = 2.0, sleep=None) -> str:
        """Request a snapshot (markups merged into the PDF) and poll until it is ready; returns the download URL."""
        import time

        self._call("POST", f"/sessions/{session_id}/files/{file_id}/snapshot")
        for _ in range(attempts):
            st = self._call("GET", f"/sessions/{session_id}/files/{file_id}/snapshot").json()
            if st.get("Status") == "Complete":
                return st["DownloadUrl"]
            if st.get("Status") == "Error":
                raise ConnectorError(f"Bluebeam snapshot failed: {st.get('Message', 'no message')}")
            (sleep or time.sleep)(wait)
        raise ConnectorError("Bluebeam snapshot did not finish in time")

    def close(self, session_id: str) -> None:
        self._call("DELETE", f"/sessions/{session_id}")

    # -- the whole hand off ----------------------------------------------------------------------------------------
    def publish(self, session_name: str, annotated_pdf: str | Path | bytes, emails: list[str] | None = None, *,
                message: str = "", invite_new: bool = True) -> dict:
        """Create a session, upload the annotated PDF, invite the people. Returns ids; the session stays open."""
        sid = self.create_session(session_name)
        fid = self.add_pdf(sid, annotated_pdf)
        if emails:
            (self.invite if invite_new else self.add_users)(sid, emails, message)
        return {"session_id": sid, "file_id": fid, "invited": list(emails or []), "dry_run": self.dry_run}
