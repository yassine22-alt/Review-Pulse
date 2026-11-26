"""Organisations, people, sessions and invitations in one SQLite file beside the projects, so an office can run the whole
product on its own machines. Passwords are hashed with Argon2id. Session and invitation tokens are random, shown once, and
only their SHA-256 is stored."""

from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

ROLES = ("admin", "coordinator", "reviewer", "applicant")
PASSWORD_MIN, PASSWORD_MAX = 12, 128      # length rules only, no composition rules (NIST SP 800-63B)
SESSION_MAX_S = 12 * 3600                 # a working day, then sign in again
SESSION_IDLE_S = 2 * 3600
INVITE_S = 7 * 24 * 3600
FAILS_BEFORE_PAUSE = 5
PAUSE_S = 15 * 60
COMMON = {"password1234", "123456789012", "qwertyuiopas", "reviewpulse1", "reviewpulse123", "passwordpassword"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs(id TEXT PRIMARY KEY, name TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, org TEXT NOT NULL REFERENCES orgs(id), email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL, roles TEXT NOT NULL, password TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS users_name ON users(org, lower(name));
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL,
  created REAL NOT NULL, seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS invitations(token TEXT PRIMARY KEY, org TEXT NOT NULL, email TEXT NOT NULL, roles TEXT NOT NULL,
  invited_by TEXT NOT NULL, expires REAL NOT NULL, used REAL);
CREATE TABLE IF NOT EXISTS failures(key TEXT PRIMARY KEY, count INTEGER NOT NULL, since REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events(at REAL NOT NULL, org TEXT, who TEXT, what TEXT NOT NULL);
"""


class AuthError(ValueError):
    """A refusal that is safe to show to the person."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class User:
    id: str
    org: str
    org_name: str
    email: str
    name: str
    roles: frozenset[str]

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "name": self.name, "organisation": self.org_name,
                "roles": sorted(self.roles)}


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _email(value: str) -> str:
    e = (value or "").strip().lower()
    if len(e) > 254 or not re.fullmatch(r"[^@\s|]+@[^@\s|]+", e):
        raise AuthError("enter a valid email address")
    return e


def _name(value: str, what: str = "your full name") -> str:
    n = " ".join((value or "").split())
    if not 2 <= len(n) <= 80:
        raise AuthError(f"enter {what} (2 to 80 characters)")
    return n


def _roles(roles) -> str:
    chosen = sorted(set(roles or ()))
    if not chosen or set(chosen) - set(ROLES):
        raise AuthError(f"choose roles among {', '.join(ROLES)}")
    if "applicant" in chosen and len(chosen) > 1:
        raise AuthError("an applicant cannot also hold an office role")
    return ",".join(chosen)


class Accounts:
    def __init__(self, path: str | Path, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.hasher = PasswordHasher()
        self._decoy = self.hasher.hash(secrets.token_urlsafe(24))   # verified for unknown emails: same time either way
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _log(self, db, org, who, what):
        db.execute("INSERT INTO events VALUES (?,?,?,?)", (self.clock(), org, who, what))

    def check_password(self, password: str, email: str = "") -> None:
        if not PASSWORD_MIN <= len(password or "") <= PASSWORD_MAX:
            raise AuthError(f"use a password of {PASSWORD_MIN} to {PASSWORD_MAX} characters")
        low = password.lower()
        if low in COMMON or len(set(low)) < 5 or (email and low == email.lower()):
            raise AuthError("this password is too easy to guess; a few unrelated words work well")

    # -- people ----------------------------------------------------------------
    def has_users(self) -> bool:
        with self._db() as db:
            return db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def _insert_user(self, db, org: str, email: str, name: str, roles: str, password: str) -> str:
        uid = uuid.uuid4().hex[:12]
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise AuthError("an account with this email already exists", 409)
        if db.execute("SELECT 1 FROM users WHERE org = ? AND lower(name) = lower(?)", (org, name)).fetchone():
            raise AuthError("someone in your organisation already uses this name; add a middle name or initial", 409)
        db.execute("INSERT INTO users(id,org,email,name,roles,password,created) VALUES (?,?,?,?,?,?,?)",
                   (uid, org, email, name, roles, self.hasher.hash(password), self.clock()))
        return uid

    def create_organisation(self, org_name: str, email: str, name: str, password: str,
                            roles=("admin", "reviewer")) -> User:
        """A new organisation with its first administrator, made by whoever operates the server: no default account exists."""
        email, name, chosen = _email(email), _name(name), _roles(roles)
        if "admin" not in chosen.split(","):
            raise AuthError("the first account of an organisation must be an administrator")
        self.check_password(password, email)
        org = uuid.uuid4().hex[:12]
        with self._db() as db:
            db.execute("INSERT INTO orgs VALUES (?,?,?)", (org, _name(org_name, "the organisation's name"), self.clock()))
            uid = self._insert_user(db, org, email, name, chosen, password)
            self._log(db, org, uid, "organisation created")
        return self.user(uid)

    @staticmethod
    def _user_from(row) -> User:
        return User(row["id"], row["org"], row["org_name"], row["email"], row["name"], frozenset(row["roles"].split(",")))

    def user(self, uid: str) -> User:
        with self._db() as db:
            row = db.execute("SELECT u.*, o.name AS org_name FROM users u JOIN orgs o ON o.id = u.org WHERE u.id = ?",
                             (uid,)).fetchone()
        if row is None:
            raise AuthError("no such account", 404)
        return self._user_from(row)

    def members(self, org: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT id,email,name,roles,active FROM users WHERE org = ? ORDER BY lower(name)",
                              (org,)).fetchall()
        return [{"id": r["id"], "email": r["email"], "name": r["name"], "roles": r["roles"].split(","),
                 "active": bool(r["active"])} for r in rows]

    def set_member(self, actor: User, uid: str, roles=None, active: bool | None = None) -> None:
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE id = ? AND org = ?", (uid, actor.org)).fetchone()
            if row is None:
                raise AuthError("no such account", 404)
            new_roles = _roles(roles) if roles is not None else row["roles"]
            new_active = int(row["active"] if active is None else active)
            others = db.execute("SELECT roles FROM users WHERE org = ? AND active = 1 AND id != ?", (actor.org, uid)).fetchall()
            keeps_admin = new_active and "admin" in new_roles.split(",")
            if not keeps_admin and not any("admin" in r["roles"].split(",") for r in others):
                raise AuthError("the organisation needs at least one active administrator", 409)
            db.execute("UPDATE users SET roles = ?, active = ? WHERE id = ?", (new_roles, new_active, uid))
            db.execute("DELETE FROM sessions WHERE user = ?", (uid,))      # the change takes effect at once
            self._log(db, actor.org, actor.id, f"account {uid}: roles {new_roles}, active {new_active}")

    # -- invitations -----------------------------------------------------------
    def invite(self, actor: User, email: str, roles) -> str:
        email, chosen = _email(email), _roles(roles)
        token = secrets.token_urlsafe(32)
        with self._db() as db:
            if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                raise AuthError("an account with this email already exists", 409)
            db.execute("DELETE FROM invitations WHERE org = ? AND email = ? AND used IS NULL", (actor.org, email))
            db.execute("INSERT INTO invitations VALUES (?,?,?,?,?,?,NULL)",
                       (_digest(token), actor.org, email, chosen, actor.id, self.clock() + INVITE_S))
            self._log(db, actor.org, actor.id, f"invited an account with roles {chosen}")
        return token

    def _invitation(self, db, token: str):
        row = db.execute("SELECT i.*, o.name AS org_name FROM invitations i JOIN orgs o ON o.id = i.org WHERE i.token = ?",
                         (_digest(token or ""),)).fetchone()
        if row is None or row["used"] is not None or row["expires"] < self.clock():
            raise AuthError("this invitation is not valid any more; ask your administrator for a new one", 404)
        return row

    def invitation(self, token: str) -> dict:
        with self._db() as db:
            row = self._invitation(db, token)
        return {"email": row["email"], "organisation": row["org_name"], "roles": row["roles"].split(",")}

    def accept(self, token: str, name: str, password: str) -> User:
        name = _name(name)
        with self._db() as db:
            row = self._invitation(db, token)
            self.check_password(password, row["email"])
            used = db.execute("UPDATE invitations SET used = ? WHERE token = ? AND used IS NULL", (self.clock(), row["token"]))
            if used.rowcount != 1:
                raise AuthError("this invitation was already used", 409)
            uid = self._insert_user(db, row["org"], row["email"], name, row["roles"], password)
            self._log(db, row["org"], uid, "invitation accepted")
        return self.user(uid)

    # -- signing in ------------------------------------------------------------
    def _paused(self, db, key: str) -> bool:
        row = db.execute("SELECT * FROM failures WHERE key = ?", (key,)).fetchone()
        if row is None:
            return False
        if self.clock() - row["since"] > PAUSE_S:
            db.execute("DELETE FROM failures WHERE key = ?", (key,))
            return False
        return row["count"] >= FAILS_BEFORE_PAUSE

    def sign_in(self, email: str, password: str, source: str = "") -> tuple[str, str, User]:
        """(session token, CSRF token, user). The refusal never says whether the email exists. Failures are counted per email
        and source, so someone guessing cannot lock the owner out from elsewhere."""
        email = (email or "").strip().lower()[:254]
        key = f"{email}|{source}"
        with self._db() as db:
            if self._paused(db, key):
                raise AuthError("too many attempts; wait 15 minutes and try again", 429)
            row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        try:
            self.hasher.verify(row["password"] if row else self._decoy, (password or "")[:PASSWORD_MAX + 1])
            good = row is not None and bool(row["active"])
        except (VerificationError, InvalidHashError):
            good = False
        if not good:
            with self._db() as db:
                db.execute("INSERT INTO failures VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count = count + 1",
                           (key, self.clock()))
                self._log(db, row["org"] if row else None, row["id"] if row else None, "sign in refused")
            raise AuthError("email or password is not right", 401)
        token, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(24), self.clock()
        with self._db() as db:
            db.execute("DELETE FROM failures WHERE key = ?", (key,))
            if self.hasher.check_needs_rehash(row["password"]):
                db.execute("UPDATE users SET password = ? WHERE id = ?", (self.hasher.hash(password), row["id"]))
            db.execute("DELETE FROM sessions WHERE created < ?", (now - SESSION_MAX_S,))
            db.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (_digest(token), row["id"], csrf, now, now))
            self._log(db, row["org"], row["id"], "signed in")
        return token, csrf, self.user(row["id"])

    def session(self, token: str | None) -> tuple[User, str] | None:
        if not token:
            return None
        now, key = self.clock(), _digest(token)
        with self._db() as db:
            row = db.execute("SELECT s.csrf, s.created AS began, s.seen, u.*, o.name AS org_name FROM sessions s "
                             "JOIN users u ON u.id = s.user JOIN orgs o ON o.id = u.org WHERE s.token = ?", (key,)).fetchone()
            if row is None:
                return None
            if not row["active"] or now - row["began"] > SESSION_MAX_S or now - row["seen"] > SESSION_IDLE_S:
                db.execute("DELETE FROM sessions WHERE token = ?", (key,))
                return None
            if now - row["seen"] > 60:
                db.execute("UPDATE sessions SET seen = ? WHERE token = ?", (now, key))
        return self._user_from(row), row["csrf"]

    def sign_out(self, token: str | None) -> None:
        if token:
            with self._db() as db:
                db.execute("DELETE FROM sessions WHERE token = ?", (_digest(token),))
