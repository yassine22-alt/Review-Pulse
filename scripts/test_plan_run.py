"""The test cases of our test plan that are steps in the app: TC-01, TC-04, TC-05, TC-13 and TC-16.

    python scripts/test_plan_run.py [--out reports/test_plan/app.json]

Each case follows the plan's steps through the web API of the app as it is served (with accounts). TC-04 and TC-05 ask the
local drafting model (Ollama). TC-13 uses a stand-in for the hosted model that records every question, and refuses and records
any connection that leaves this machine. Prints what happened and whether each expected result was seen.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests" / "app")]

from fastapi.testclient import TestClient  # noqa: E402
from test_scenarios import wait  # noqa: E402

from reviewpulse.app import service  # noqa: E402
from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402

PASSWORD = "violet harbour ninety lamps"      # throwaway accounts in a temporary folder
CLAUSE = "Hallways must be min. 36 inches wide."
DOCUMENT = f"# Test requirements\n\nArt. 1 {CLAUSE}\n"
OUTSIDE: list[str] = []


def guard_the_network() -> None:
    real = socket.socket.connect

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if isinstance(address, tuple) and not (host.startswith("127.") or host in ("::1", "localhost", "0.0.0.0")):
            OUTSIDE.append(host)
            raise OSError(f"test: a connection outside this machine was refused ({host})")
        return real(self, address)

    socket.socket.connect = connect


def signed_in(app, email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    c.headers["x-rp-csrf"] = r.json()["csrf"]
    return c


def office(tmp: Path, llm, fallback):
    app = create_app(tmp / "data", llm=llm, fallback=fallback, workers=1)
    app.state.accounts.create_organisation("Test Office", "t@test.test", "Test Reviewer", PASSWORD)
    return app, signed_in(app, "t@test.test")


def close(app) -> None:
    app.state.preparer.close()
    app.state.jobs.shutdown()


def upload(c, pid, kind: str, path: Path) -> None:
    with path.open("rb") as f:
        r = c.post(f"/api/projects/{pid}/{kind}", files={"file": (path.name, f)})
    assert r.status_code == 202, r.text
    wait(c, pid, r.json())


def project(c, tmp: Path, plan: Path | None = None) -> str:
    pid = c.post("/api/projects", json={"name": "test case"}).json()["id"]
    if plan is not None:
        upload(c, pid, "plan", plan)
    doc = tmp / "requirements.md"
    doc.write_text(DOCUMENT, encoding="utf-8")
    upload(c, pid, "requirements", doc)
    return pid


def clause_id(c, pid) -> str:
    return next(x["id"] for x in c.get(f"/api/projects/{pid}/document").json()["clauses"] if "Hallways" in x["text"])


def tc01(tmp: Path, plan: Path) -> dict:
    app, c = office(tmp / "tc01", lambda: None, lambda: None)
    try:
        pid = c.post("/api/projects", json={"name": "TC-01"}).json()["id"]
        upload(c, pid, "plan", plan)
        view = c.get(f"/api/projects/{pid}/view").json()
        sheet = view["sheets"][0]
        counts: dict[str, int] = {}
        for e in sheet["elements"]:
            counts[e["cls"]] = counts.get(e["cls"], 0) + 1
        backdrop = c.get(f"/api/projects/{pid}/sheets/0/backdrop.png")
        analysed = c.get(f"/api/projects/{pid}").json().get("plan")
        seen = {"rooms": len(sheet["rooms"]), "elements": counts, "scale": {k: sheet.get(k) for k in ("scale", "affine", "mode")},
                "reader": sheet.get("reader"), "backdrop": [backdrop.status_code, len(backdrop.content)], "plan": analysed}
        seen["met"] = bool(sheet["rooms"] and counts.get("door") and counts.get("window") and backdrop.status_code == 200
                           and backdrop.content[:4] == b"\x89PNG")
        return seen
    finally:
        close(app)


def tc04_05(tmp: Path, plan: Path) -> tuple[dict, dict]:
    app, c = office(tmp / "tc04", service.default_llm, lambda: None)
    try:
        pid = project(c, tmp, plan)
        cid = clause_id(c, pid)
        read = c.post(f"/api/projects/{pid}/interpret/{cid}").json()
        program = json.dumps(read.get("program"))
        four = {"status": read.get("status"), "arm": read.get("arm"), "model": read.get("model"),
                "readback": read.get("readback"), "program": read.get("program"),
                "has 0.9144": "0.9144" in program, "approved": read.get("decision")}
        four["met"] = read.get("status") == "DRAFTED" and "0.9144" in program

        def findings() -> list[dict]:
            r = c.post(f"/api/projects/{pid}/check")
            if r.status_code != 202:
                return [{"refused": r.status_code, "detail": r.json().get("detail")}]
            try:
                wait(c, pid, r.json())
            except AssertionError as e:                 # the job itself says why it ran nothing
                return [{"refused": "the check job failed", "detail": str(e).splitlines()[0]}]
            return c.get(f"/api/projects/{pid}/findings").json()

        def from_clause(got) -> list:
            return [f for f in (got if isinstance(got, list) else got.get("findings", []))
                    if (f.get("source") or {}).get("clause") == cid]

        before = findings()
        decided = c.post(f"/api/projects/{pid}/decision", json={"clause": cid, "action": "approve"})
        if decided.status_code == 409:
            decided = c.post(f"/api/projects/{pid}/decision", json={"clause": cid, "action": "approve", "acknowledge": True,
                                                                    "note": "test case"})
        after = findings()
        (ROOT / "reports" / "test_plan").mkdir(parents=True, exist_ok=True)
        (ROOT / "reports" / "test_plan" / "tc05_after.json").write_text(json.dumps(after, ensure_ascii=False, indent=1, default=str),
                                                                      encoding="utf-8")
        five = {"first check": before if isinstance(before, list) and before[:1] and "refused" in before[0] else
                f"{len(from_clause(before))} findings from the draft", "approve": decided.status_code,
                "second check": [{k: f.get(k) for k in ("verdict", "rule_id", "message")} for f in from_clause(after)]}
        five["met"] = not from_clause(before) and bool(from_clause(after))
        return four, five
    finally:
        close(app)


class CannotRead:
    """A local model that answers nothing usable, so that the hosted one is wanted."""
    model, external = "local-stand-in", False

    def complete(self, system, user, schema):
        return {}


class Recorder:
    model, provider, external = "hosted-stand-in", "groq", True

    def __init__(self):
        self.sent: list[str] = []

    def complete(self, system, user, schema):
        self.sent.append(system + "\n" + user)
        return {}


def plan_lines(plan: Path) -> list[str]:
    """Whole lines of text written on the plan that could only have come from it: two words or more, or a decimal figure. One
    common room word proves nothing, since the app's own list of room names in many languages holds it."""
    import re

    import pymupdf

    with pymupdf.open(plan) as doc:
        lines = {" ".join(x.split()) for page in doc for x in page.get_text().splitlines()}
    return sorted(x for x in lines if (len(x.split()) >= 2 and len(x) >= 6) or re.fullmatch(r"\d+[.,]\d{2}( ?m.?)?", x))


def tc13(tmp: Path, plan: Path) -> dict:
    words_on_plan = plan_lines(plan)
    hosted = Recorder()
    app, c = office(tmp / "tc13", CannotRead, lambda: hosted)
    try:
        pid = project(c, tmp, plan)
        cid = clause_id(c, pid)
        off_status = c.post(f"/api/projects/{pid}/interpret/{cid}").status_code
        off = len(hosted.sent)
        assert c.patch(f"/api/projects/{pid}", json={"external_consent": True}).status_code == 200
        on_status = c.post(f"/api/projects/{pid}/interpret/{cid}").status_code
        sent = "\n".join(hosted.sent)
        kept = ROOT / "reports" / "test_plan" / "tc13_sent.txt"          # to be read by a person
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_text("\n\n=== NEXT QUESTION ===\n".join(hosted.sent), encoding="utf-8")
        leaked = sorted({w for w in [*words_on_plan, "requirements.md", "test case", plan.name] if w.lower() in sent.lower()})
        seen = {"consent off": {"status": off_status, "questions to the hosted model": off},
                "consent on": {"status": on_status, "questions to the hosted model": len(hosted.sent) - off,
                               "characters sent": len(sent), "has the clause": "Hallways" in sent,
                               "text lines of the plan looked for": len(words_on_plan),
                               "lines of the plan or file and project names found in what was sent": leaked,
                               "pictures sent": "base64" in sent or "image_url" in sent},
                "connections outside this machine": sorted(set(OUTSIDE))}
        seen["met"] = off == 0 and len(hosted.sent) > 0 and "Hallways" in sent and not leaked and not OUTSIDE
        return seen
    finally:
        close(app)


def tc16(tmp: Path) -> dict:
    app, c = office(tmp / "tc16", lambda: None, lambda: None)
    try:
        pid = c.post("/api/projects", json={"name": "mine"}).json()["id"]
        app.state.accounts.create_organisation("Other Office", "o@other.test", "Other Person", PASSWORD)
        other = signed_in(app, "o@other.test")
        theirs = other.post("/api/projects", json={"name": "theirs"}).json()["id"]
        secret = tmp / "tc16" / "data" / "outside.txt"
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text("NOT-OF-ANY-PROJECT", encoding="utf-8")
        tries = {}
        for name in ("../project.json", "..%2Fproject.json", "%2e%2e%2f%2e%2e%2foutside.txt", "..%5C..%5Coutside.txt",
                     "../../outside.txt", f"..%2F..%2F{pid}%2Fproject.json"):
            r = c.get(f"/api/projects/{pid}/files/{name}")
            tries[name] = {"status": r.status_code, "leaked": "NOT-OF-ANY-PROJECT" in r.text or '"external_consent"' in r.text}
        for label, who, target in (("another office's project", c, theirs), ("my project from another office", other, pid)):
            r = who.get(f"/api/projects/{target}/files/findings.json")
            tries[label] = {"status": r.status_code, "answer": r.json().get("detail") if r.status_code >= 400 else r.text[:80]}
        return {"tries": tries, "met": all(v["status"] >= 400 and not v.get("leaked") for v in tries.values())}
    finally:
        close(app)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "test_plan" / "app.json")
    args = ap.parse_args()
    guard_the_network()
    results: dict = {}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        tmp = Path(folder)
        plan = make_plan(tmp / "plan", png=False)["pdf"]
        for name, run in (("TC-01", lambda: tc01(tmp, Path(plan))), ("TC-16", lambda: tc16(tmp)),
                          ("TC-13", lambda: tc13(tmp, Path(plan))),
                          ("TC-04/05", lambda: tc04_05(tmp, Path(plan)))):
            try:
                got = run()
                if name == "TC-04/05":
                    results["TC-04"], results["TC-05"] = got
                else:
                    results[name] = got
            except Exception as e:  # noqa: BLE001 - a case that cannot run is a result too
                results[name] = {"met": False, "error": f"{type(e).__name__}: {e}"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for name, got in results.items():
        print(f"{name}: {'met' if got.get('met') else 'NOT MET'}")
        print("   ", json.dumps({k: v for k, v in got.items() if k not in ('program', 'met')}, ensure_ascii=False,
                                default=str)[:900])


if __name__ == "__main__":
    main()
