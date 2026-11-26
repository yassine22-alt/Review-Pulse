"""Who may do what. One table, checked in one place for every request. Anything under /api that is not listed here as public
needs a session, and a route nobody listed falls to the strictest rule that fits it, so a new route is never open by accident."""

from __future__ import annotations

import re

OFFICE = frozenset({"admin", "coordinator", "reviewer"})
REVIEWER = frozenset({"reviewer"})
ADMIN = frozenset({"admin"})
ANYONE = None                                   # any signed in person

PUBLIC = [("GET", r"/api/health"), ("POST", r"/api/auth/sign-in"), ("GET", r"/api/auth/session"),
          ("GET", r"/api/auth/invitations/[^/]+"), ("POST", r"/api/auth/invitations/[^/]+/accept")]

_P = r"/api/projects/[^/]+"
RULES = [                                       # the first rule that fits decides
    ("POST", r"/api/auth/sign-out", ANYONE),
    ("*", r"/api/admin(/.*)?", ADMIN),
    ("GET", r"/api/(packs|reviewer-states)", ANYONE),
    ("GET", r"/api/projects(/.*)?", OFFICE),
    ("POST", r"/api/projects", OFFICE),                                    # intake: open, upload, run
    ("PATCH", _P, OFFICE),
    ("DELETE", _P, OFFICE),
    ("POST", _P + r"/(plan|requirements|draft|check)", OFFICE),
    ("*", r"/api/projects/.*", REVIEWER),                                  # every other change is a review decision
    ("*", r"/api/interpreter/.*", REVIEWER),
]


def is_public(method: str, path: str) -> bool:
    return any(method == m and re.fullmatch(rx, path) for m, rx in PUBLIC)


def needs_session(path: str) -> bool:
    return path == "/api" or path.startswith(("/api/", "/docs", "/redoc", "/openapi.json"))


def required_roles(method: str, path: str) -> frozenset[str] | None:
    method = "GET" if method == "HEAD" else method
    for m, rx, roles in RULES:
        if m in ("*", method) and re.fullmatch(rx, path):
            return roles
    return ADMIN


def allowed(user_roles: frozenset[str], method: str, path: str) -> bool:
    roles = required_roles(method, path)
    return roles is ANYONE or bool(user_roles & roles)
