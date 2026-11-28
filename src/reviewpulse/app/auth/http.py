"""The web side: one gate in front of every request, and the sign in and administration routes."""

from __future__ import annotations

import os
import re
import secrets

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import policy
from .accounts import SESSION_MAX_S, Accounts, AuthError

COOKIE = "rp_session"
CSRF_HEADER = "x-rp-csrf"
SAFE = {"GET", "HEAD", "OPTIONS"}


class SignIn(BaseModel):
    email: str
    password: str


class Accept(BaseModel):
    name: str
    password: str


class Invite(BaseModel):
    email: str
    roles: list[str]


class Member(BaseModel):
    roles: list[str] | None = None
    active: bool | None = None


def _refuse(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def _fail(e: AuthError):
    raise HTTPException(e.status, str(e)) from None


def install(app: FastAPI, accounts: Accounts, store) -> None:
    @app.middleware("http")
    async def gate(request: Request, call_next):
        path, method = request.scope["path"], request.method
        found = accounts.session(request.cookies.get(COOKIE))
        request.state.user = found[0] if found else None
        request.state.csrf = found[1] if found else None
        if policy.needs_session(path) and not policy.is_public(method, path):
            if found is None:
                return _refuse(401, "sign in to continue")
            user, csrf = found
            sent = request.headers.get(CSRF_HEADER, "").encode()
            if method not in SAFE and not secrets.compare_digest(sent, csrf.encode()):
                return _refuse(403, "this request did not come from the app; reload the page and try again")
            m = re.match(r"/api/projects/([^/]+)", path)
            if m:                                      # another organisation's project does not exist for you
                try:
                    owner = store.get(m.group(1)).org
                except (KeyError, ValueError):
                    owner = None
                if owner != user.org:
                    return _refuse(404, f"no project {m.group(1)}")
            if not policy.allowed(user.roles, method, path):
                return _refuse(403, "your role does not allow this; ask your administrator")
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def start(request: Request, response: Response, email: str, password: str) -> dict:
        try:
            token, csrf, user = accounts.sign_in(email, password, request.client.host if request.client else "")
        except AuthError as e:
            _fail(e)
        secure = request.url.scheme == "https" or os.environ.get("REVIEWPULSE_SECURE_COOKIES") == "1"
        response.set_cookie(COOKIE, token, max_age=SESSION_MAX_S, httponly=True, samesite="strict", secure=secure, path="/")
        return {"user": user.public(), "csrf": csrf}

    @app.get("/api/auth/session")
    def session(request: Request):
        user = request.state.user
        return {"user": user.public() if user else None, "csrf": request.state.csrf, "set_up": accounts.has_users()}

    @app.post("/api/auth/sign-in")
    def sign_in(body: SignIn, request: Request, response: Response):
        return start(request, response, body.email, body.password)

    @app.post("/api/auth/sign-out", status_code=204)
    def sign_out(request: Request, response: Response):
        accounts.sign_out(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")

    @app.get("/api/auth/invitations/{token}")
    def invitation(token: str):
        try:
            return accounts.invitation(token)
        except AuthError as e:
            _fail(e)

    @app.post("/api/auth/invitations/{token}/accept")
    def accept(token: str, body: Accept, request: Request, response: Response):
        try:
            user = accounts.accept(token, body.name, body.password)
        except AuthError as e:
            _fail(e)
        return start(request, response, user.email, body.password)

    @app.get("/api/admin/members")
    def members(request: Request):
        return accounts.members(request.state.user.org)

    @app.post("/api/admin/invitations", status_code=201)
    def invite(body: Invite, request: Request):
        try:
            return {"token": accounts.invite(request.state.user, body.email, body.roles)}
        except AuthError as e:
            _fail(e)

    @app.patch("/api/admin/members/{uid}", status_code=204)
    def member(uid: str, body: Member, request: Request):
        try:
            accounts.set_member(request.state.user, uid, body.roles, body.active)
        except AuthError as e:
            _fail(e)
