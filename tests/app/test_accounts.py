"""Accounts: nothing is open by accident, organisations never see each other, roles hold, and decisions carry real names."""

import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("argon2")

from fastapi.testclient import TestClient  # noqa: E402

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.app.auth import Accounts, AuthError, policy  # noqa: E402

PW = "violet harbour ninety lamps"


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "data", llm=lambda: None, workers=1)


def client(app, email=None):
    c = TestClient(app)
    if email:
        r = c.post("/api/auth/sign-in", json={"email": email, "password": PW})
        assert r.status_code == 200, r.text
        c.headers["x-rp-csrf"] = r.json()["csrf"]
    return c


def join(app, admin, email, name, roles):
    token = admin.post("/api/admin/invitations", json={"email": email, "roles": roles}).json()["token"]
    r = client(app).post(f"/api/auth/invitations/{token}/accept", json={"name": name, "password": PW})
    assert r.status_code == 200, r.text
    return client(app, email)


@pytest.fixture
def office(app):
    app.state.accounts.create_organisation("North Permit Office", "ada@north.test", "Ada Admin", PW)
    admin = client(app, "ada@north.test")
    return {"admin": admin,
            "coordinator": join(app, admin, "cora@north.test", "Cora Coordinator", ["coordinator"]),
            "reviewer": join(app, admin, "rene@north.test", "Rene Reviewer", ["reviewer"]),
            "applicant": join(app, admin, "alex@applicant.test", "Alex Applicant", ["applicant"])}


def test_every_route_needs_a_session_unless_listed_as_public(app):
    anonymous = client(app)
    checked = 0
    for path, methods in app.openapi()["paths"].items():
        concrete = path.replace("{pid}", "abcdef123456")
        while "{" in concrete:
            concrete = concrete[:concrete.index("{")] + "1" + concrete[concrete.index("}") + 1:]
        for method in methods:
            if policy.is_public(method.upper(), concrete):
                continue
            r = anonymous.request(method.upper(), concrete)
            assert r.status_code == 401, (method, path, r.status_code)
            checked += 1
    assert checked > 40
    for page in ("/docs", "/openapi.json"):
        assert anonymous.get(page).status_code == 401


def test_organisations_do_not_see_each_other(app, office):
    pid = office["reviewer"].post("/api/projects", json={"name": "12 Elm Street"}).json()["id"]
    app.state.accounts.create_organisation("South Office", "sam@south.test", "Sam South", PW)
    other = client(app, "sam@south.test")
    assert other.get("/api/projects").json() == []
    for method, path in [("GET", ""), ("DELETE", ""), ("GET", "/findings"), ("GET", "/audit"), ("POST", "/check")]:
        assert other.request(method, f"/api/projects/{pid}{path}").status_code == 404, (method, path)
    assert [p["id"] for p in office["coordinator"].get("/api/projects").json()] == [pid]
    assert other.get("/api/admin/members").json()[0]["email"] == "sam@south.test"


def test_roles(office):
    pid = office["coordinator"].post("/api/projects", json={"name": "intake"}).json()["id"]
    signoff = {"discipline": "general", "result": "approved", "cycle": 1}
    for who in ("admin", "reviewer", "coordinator"):
        assert office[who].get(f"/api/projects/{pid}").status_code == 200
    assert office["coordinator"].post(f"/api/projects/{pid}/signoffs", json=signoff).status_code == 403
    assert office["coordinator"].patch(f"/api/projects/{pid}", json={"inventory_reviewed": True}).status_code == 403
    assert office["coordinator"].patch(f"/api/projects/{pid}", json={"name": "renamed"}).status_code == 200
    assert office["coordinator"].get("/api/admin/members").status_code == 403
    assert office["applicant"].get("/api/projects").status_code == 403
    assert office["applicant"].get(f"/api/projects/{pid}").status_code == 403


def test_comments_are_assigned_only_to_the_office_and_each_person_sees_their_own(app, office, monkeypatch):
    from reviewpulse.app import service, workflow

    pid = office["reviewer"].post("/api/projects", json={"name": "12 Elm Street"}).json()["id"]
    store = app.state.store

    def one_comment(store, pid, cycle=None):                    # stands for an analysed plan with one correction
        return {"items": [{"key": "Art. 1", "n": 1, "citation": "[Art. 1]", "wording": "Widen the door.", "dropped": False,
                           "followup": workflow.followups(store, pid).get("Art. 1")}]}

    monkeypatch.setattr(service, "correction_list", one_comment)
    names = [p["name"] for p in office["reviewer"].get("/api/people").json()]
    assert names == ["Ada Admin", "Cora Coordinator", "Rene Reviewer"]                 # no applicant, no email address
    assert set(office["reviewer"].get("/api/people").json()[0]) == {"name", "roles"}
    assert office["applicant"].get("/api/people").status_code == 403
    assert office["applicant"].get("/api/my-items").status_code == 403
    url = f"/api/projects/{pid}/correction-list/follow-up/Art. 1"
    assert office["coordinator"].put(url, json={"assignee": "Rene Reviewer"}).status_code == 403    # a review decision
    assert office["reviewer"].put(url, json={"assignee": "Alex Applicant"}).status_code == 400
    assert office["reviewer"].put(url, json={"assignee": "Nobody Known"}).status_code == 400
    assert office["reviewer"].put(url, json={"assignee": "Cora Coordinator", "due": "2026-12-04",
                                             "reviewer": "Someone Else"}).status_code == 200
    mine = office["coordinator"].get("/api/my-items").json()
    assert [(m["project"], m["n"], m["due"], m["by"]) for m in mine] == [(pid, 1, "2026-12-04", "Rene Reviewer")]
    assert office["reviewer"].get("/api/my-items").json() == []
    app.state.accounts.create_organisation("South Office", "sam@south.test", "Cora Coordinator", PW)   # the same name elsewhere
    assert client(app, "sam@south.test").get("/api/my-items").json() == []
    assert office["reviewer"].put(url, json={"resolved": True, "note": "checked"}).status_code == 200
    assert office["coordinator"].get("/api/my-items").json() == []
    assert service.assigned_to(store, "no such organisation", "Cora Coordinator") == []


def test_decisions_carry_the_account_name_not_a_typed_one(office):
    reviewer = office["reviewer"]
    created = reviewer.post("/api/projects", json={"name": "p", "curator": "Somebody Else"}).json()
    assert created["curator"] == "Rene Reviewer"
    pid = created["id"]
    r = reviewer.put(f"/api/projects/{pid}/clause-states",
                     json={"clause": "1.1", "state": "deferred", "reviewer": "Somebody Else"})
    assert r.status_code == 200, r.text
    audit = reviewer.get(f"/api/projects/{pid}/audit").text
    assert "Rene Reviewer" in audit and "Somebody Else" not in audit


def test_a_change_without_the_csrf_header_is_refused(office):
    c = office["reviewer"]
    token = c.headers.pop("x-rp-csrf")
    assert c.get("/api/projects").status_code == 200
    assert c.post("/api/projects", json={"name": "x"}).status_code == 403
    c.headers["x-rp-csrf"] = token + "x"
    assert c.post("/api/projects", json={"name": "x"}).status_code == 403


def test_cookie_flags_and_sign_out(app, office):
    c = TestClient(app)
    r = c.post("/api/auth/sign-in", json={"email": "rene@north.test", "password": PW})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    kept = c.cookies.get("rp_session")
    assert c.post("/api/auth/sign-out", headers={"x-rp-csrf": r.json()["csrf"]}).status_code == 204
    c.cookies.set("rp_session", kept)                       # a copied cookie is dead after sign out
    assert c.get("/api/projects").status_code == 401


def test_https_gets_a_secure_cookie(app, office):
    c = TestClient(app, base_url="https://testserver")
    r = c.post("/api/auth/sign-in", json={"email": "rene@north.test", "password": PW})
    assert "secure" in r.headers["set-cookie"].lower()


def test_refusals_do_not_reveal_accounts_and_guessing_pauses(app, office):
    c = client(app)
    known = c.post("/api/auth/sign-in", json={"email": "rene@north.test", "password": "wrong wrong wrong"})
    unknown = c.post("/api/auth/sign-in", json={"email": "nobody@north.test", "password": "wrong wrong wrong"})
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json()) == (401, known.json())
    for _ in range(5):
        c.post("/api/auth/sign-in", json={"email": "rene@north.test", "password": "wrong wrong wrong"})
    assert c.post("/api/auth/sign-in", json={"email": "rene@north.test", "password": PW}).status_code == 429


def test_invitations_work_once_and_deactivation_ends_sessions(app, office):
    admin = office["admin"]
    token = admin.post("/api/admin/invitations", json={"email": "new@north.test", "roles": ["reviewer"]}).json()["token"]
    c = client(app)
    assert c.get(f"/api/auth/invitations/{token}").json()["email"] == "new@north.test"
    assert c.post(f"/api/auth/invitations/{token}/accept", json={"name": "New Person", "password": "short"}).status_code == 400
    assert c.post(f"/api/auth/invitations/{token}/accept", json={"name": "New Person", "password": PW}).status_code == 200
    assert client(app).get(f"/api/auth/invitations/{token}").status_code == 404
    rid = next(m["id"] for m in admin.get("/api/admin/members").json() if m["email"] == "rene@north.test")
    assert admin.patch(f"/api/admin/members/{rid}", json={"active": False}).status_code == 204
    assert office["reviewer"].get("/api/projects").status_code == 401
    me = next(m["id"] for m in admin.get("/api/admin/members").json() if m["email"] == "ada@north.test")
    assert admin.patch(f"/api/admin/members/{me}", json={"active": False}).status_code == 409


def test_sessions_and_invitations_expire_and_secrets_are_not_stored_plainly(tmp_path):
    now = [1_000_000.0]
    accounts = Accounts(tmp_path / "a.sqlite", clock=lambda: now[0])
    admin = accounts.create_organisation("Office", "a@o.test", "Ann Admin", PW)
    token, _csrf, _user = accounts.sign_in("a@o.test", PW)
    invite = accounts.invite(admin, "b@o.test", ["reviewer"])
    stored = (tmp_path / "a.sqlite").read_bytes()
    assert PW.encode() not in stored and token.encode() not in stored and invite.encode() not in stored
    now[0] += 3 * 3600                                      # idle too long
    assert accounts.session(token) is None
    now[0] += 8 * 24 * 3600
    with pytest.raises(AuthError):
        accounts.accept(invite, "Bea Brown", PW)


def test_weak_passwords_and_bad_roles_are_refused(tmp_path):
    accounts = Accounts(tmp_path / "a.sqlite")
    for weak in ("short", "aaaaaaaaaaaaaa", "password1234"):
        with pytest.raises(AuthError):
            accounts.create_organisation("Office", "a@o.test", "Ann Admin", weak)
    admin = accounts.create_organisation("Office", "a@o.test", "Ann Admin", PW)
    for roles in (["owner"], [], ["applicant", "reviewer"]):
        with pytest.raises(AuthError):
            accounts.invite(admin, "c@o.test", roles)


def test_uploading_requirements_does_not_ask_the_model(tmp_path):
    """The review desk reads a clause when asked; drafting every clause at upload cost 18 minutes on a real checklist."""
    asked = []

    class Model:
        model = "counting"

        def complete(self, *args):
            asked.append(args)
            return {}

    app = create_app(tmp_path / "data", llm=lambda: Model(), workers=1)
    app.state.accounts.create_organisation("Office", "r@o.test", "Rae Reviewer", PW)
    with client(app, "r@o.test") as c:
        pid = c.post("/api/projects", json={"name": "p"}).json()["id"]
        job = c.post(f"/api/projects/{pid}/requirements",
                     files={"file": ("rules.md", b"# Rules\n\n6.1 Every door shall be at least 0.80 m wide.\n")}).json()
        for _ in range(300):
            record = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
            if record["status"] in ("done", "failed"):
                break
            time.sleep(0.1)
        assert record["status"] == "done", record.get("error")
        assert c.get(f"/api/projects/{pid}/document").json()["clauses"]
    assert asked == []
