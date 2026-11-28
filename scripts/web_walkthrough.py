"""Walk through the product in a real browser, against a throwaway office, and keep a picture of each screen.

    python scripts/web_walkthrough.py reports/web_walkthrough

Needs the built front end (cd frontend && npm run build), ``pip install playwright`` and an installed Edge or Chrome.
It stops at the first step that does not behave, and fails if the browser reports a script error.
"""

from __future__ import annotations

import re
import secrets
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "app"))

from test_scenarios import DOC, Scripted  # noqa: E402  (a stand in for the clause reading model)

from reviewpulse.app.api import create_app  # noqa: E402
from reviewpulse.synth.make_plan import make_plan  # noqa: E402
from reviewpulse.synth.scenarios import SCENARIOS  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    planted = next(s for s in SCENARIOS if s[0] == "02_door_too_narrow")[2]      # one door is 0.70 m wide
    drawing = Path(make_plan(work / "plan", png=False, **planted)["pdf"])
    rules = work / "office_rules.md"
    rules.write_bytes(Path(DOC).read_bytes())

    app = create_app(work / "data", llm=lambda: Scripted(), workers=1)
    password = secrets.token_urlsafe(18)
    app.state.accounts.create_organisation("Demo Permit Office", "ada@example.test", "Ada Martin", password)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.1)
    base = f"http://127.0.0.1:{port}/"

    errors: list[str] = []
    outside: list[str] = []
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:
            browser = pw.chromium.launch(channel="chrome")
        context = browser.new_context(viewport={"width": 1360, "height": 860})

        def watch(page):
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if "Content Security Policy" in m.text else None)
            page.on("request", lambda r: outside.append(r.url) if not r.url.startswith((base, "data:", "blob:")) else None)

        page = context.new_page()
        watch(page)
        shot = lambda name: page.screenshot(path=str(out / f"{name}.png"), full_page=True)  # noqa: E731

        page.goto(base)
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        shot("1_sign_in")
        page.get_by_label("Email").fill("ada@example.test")
        page.get_by_label("Password").fill("not the password at all")
        page.get_by_role("button", name="Sign in").click()
        expect(page.get_by_role("alert")).to_contain_text("not right")
        page.get_by_label("Password").fill(password)
        page.get_by_role("button", name="Sign in").click()
        expect(page.get_by_role("heading", name="My work")).to_be_visible()
        shot("2_empty_queue")

        page.get_by_role("button", name="New submission").click()
        page.get_by_label("Name of the submission").fill("12 Elm Street, permit 2026-0413")
        page.get_by_label("Building use").fill("Residential, one or two homes")
        page.get_by_label("Location").fill("Aachen")
        shot("2b_new_submission")
        page.get_by_role("button", name="Open it").click()
        expect(page.get_by_role("heading", name="12 Elm Street, permit 2026-0413")).to_be_visible()
        expect(page.get_by_text("Residential, one or two homes · Aachen")).to_be_visible()
        inputs = page.locator("input[type=file]")
        inputs.nth(0).set_input_files(str(drawing))
        expect(page.get_by_text(drawing.name)).to_be_visible(timeout=30000)
        expect(page.get_by_role("button", name="Choose file")).to_be_enabled(timeout=180000)
        page.locator("input[type=file]").nth(1).set_input_files(str(rules))
        expect(page.get_by_text(rules.name)).to_be_visible(timeout=30000)
        expect(page.get_by_role("heading", name="Correction list")).to_be_visible(timeout=180000)
        shot("3_submission")
        # every button of the correction list answers, with the signed in browser's own cookie
        for label in ("Open the list", "Marked up drawings", "Download as CSV"):
            href = page.get_by_role("link", name=label).get_attribute("href")
            reply = context.request.get(base.rstrip("/") + href)
            assert reply.status == 200 and reply.body(), (label, reply.status, reply.text()[:300])

        # the review desk: read one requirement, take its second reading, approve it, run the checks
        page.get_by_role("link", name="Open the review desk").click()
        expect(page.get_by_role("tab", name="Requirements")).to_be_visible(timeout=60000)
        only = page.locator(".cid", has_text=re.compile(r"^Art\. 6\.1$"))
        clause = page.locator(".item.clause").filter(has=only)
        clause.locator(".head").click()
        clause.get_by_role("button", name="Ask the tool for a measured check").click()
        clause.get_by_role("button", name="Get a second reading").click(timeout=120000)
        approve = clause.get_by_role("button", name="Approve this check")
        expect(approve).to_be_visible(timeout=120000)
        shot("4_desk_approve")
        if clause.get_by_role("checkbox").count():
            clause.get_by_role("checkbox").check()
        approve.click()
        expect(page.get_by_role("heading", name="Covered by an approved check")).to_be_visible(timeout=60000)
        page.get_by_text("Let the tool propose measured checks").click()
        page.get_by_role("button", name="Run the approved checks").click()
        page.wait_for_timeout(1500)
        expect(page.locator(".floating")).to_have_count(0, timeout=180000)
        page.get_by_role("tab", name="Corrections").click()
        expect(page.locator(".item").first).to_be_visible(timeout=60000)
        expect(page.locator(".canvas .pin").first).to_be_attached()
        page.wait_for_timeout(700)
        shot("5_desk_findings")
        # the sheet alone, what the tool read on it, or the corrections
        view = page.get_by_role("group", name="What to show on the sheet")
        view.get_by_role("button", name="What was read").click()
        expect(page.locator(".detected polygon, .detected polyline").first).to_be_attached()
        expect(page.locator(".readout")).to_contain_text("Read on this sheet")
        expect(page.locator(".canvas .pin")).to_have_count(0)
        shot("5b_what_was_read")
        view.get_by_role("button", name="Plan only").click()
        expect(page.locator(".detected, .canvas .pin")).to_have_count(0)
        view.get_by_role("button", name="Corrections").click()
        expect(page.locator(".canvas .pin").first).to_be_attached()
        failing = page.locator(".item.bad").first
        failing.locator(".head").click()
        page.wait_for_timeout(900)
        expect(failing.locator("blockquote")).to_contain_text("0.80")
        shot("6_desk_evidence")
        # a comment is not dismissed without saying why; the reason is shown, and the dismissal can be undone
        failing.get_by_role("button", name="Dismiss D").click()
        confirm = failing.get_by_role("button", name="Dismiss it")
        expect(confirm).to_be_disabled()
        failing.get_by_label("Why is this not a correction?").fill("The schedule on this sheet already states it")
        shot("6a_dismiss_reason")
        confirm.click()
        expect(failing.get_by_text("Reason for dismissing: The schedule on this sheet already states it")).to_be_visible(timeout=30000)
        failing.get_by_role("button", name="Undo").click()
        expect(failing.get_by_role("button", name="Accept A")).to_be_visible(timeout=30000)
        page.locator("body").press("a")
        expect(failing.locator(".decided")).to_have_text("Accepted", timeout=30000)
        expect(failing.get_by_text("Accepted by Ada Martin")).to_be_visible()
        # the comment is given to a person with a date
        failing.get_by_label("Assigned to").select_option("Ada Martin")
        failing.get_by_label("Due").fill("2026-12-04")
        failing.get_by_role("button", name="Save assignment").click()
        expect(failing.get_by_role("button", name="Save assignment")).to_have_count(0, timeout=30000)
        shot("6b_assigned")
        # the reviewer decides requirements by hand: no model is needed, and the desk moves on to the next one
        page.get_by_role("tab", name="Requirements").click()
        left = page.locator(".runbar p strong").nth(1)
        before = int(left.inner_text())
        card = page.locator(".item.clause.open")
        first = page.locator(".item.clause").filter(has=page.locator(".cid", has_text=re.compile(r"^Art\. 1$")))
        first.locator(".head").click()
        # each part of the requirement is searched; ticking one as missing starts the comment from the requirement's words
        missing = card.get_by_role("button", name="It is missing").first
        expect(missing).to_be_visible(timeout=120000)
        missing.click()
        expect(card.get_by_role("button", name="Shown on the plans")).to_be_disabled()   # not while a part is missing
        card.get_by_role("button", name="Needs correction").click()
        record = card.get_by_role("button", name="Record my decision")
        expect(card.get_by_label("Comment to the applicant")).to_have_value(re.compile("^Show on the plans: .+[.]$"))
        shot("7a_parts_ticked")
        card.get_by_label("Comment to the applicant").fill("")
        expect(record).to_be_disabled()                       # a correction needs its comment
        card.get_by_label("Sheet that shows it").select_option(index=1)
        card.get_by_label("Comment to the applicant").fill("Show the exit door on the ground floor plan")
        shot("7a_deciding")
        record.click()
        expect(left).to_have_text(str(before - 1), timeout=30000)
        expect(card).to_have_count(1)                         # the next requirement is open
        # a closed card still shows the words of its requirement
        expect(page.locator(".item.clause.todo:not(.open) .quote-short").first).to_be_visible()
        shown_id = card.locator(".cid").inner_text()
        card.get_by_role("button", name="Shown on the plans").click()
        expect(record).to_be_disabled()                       # no pass without evidence
        card.get_by_label("What did you rely on?").fill("Room schedule on the ground floor sheet")
        record.click()
        expect(left).to_have_text(str(before - 2), timeout=30000)
        expect(page.get_by_text("Decided by a reviewer")).to_be_visible()
        done = page.locator(".item.clause.mine").filter(has=page.locator(".cid", has_text=re.compile("^" + re.escape(shown_id) + "$")))
        expect(done.locator(".decided")).to_have_text("Shown on the plans")
        shot("7b_decided")
        page.get_by_role("tab", name="Corrections").click()
        mine = page.locator(".item").filter(has_text="Show the exit door on the ground floor plan")
        mine.locator(".head").click()
        expect(mine.get_by_text("Written by Ada Martin")).to_be_visible()
        # the filters narrow the list and say so, and "Show all" brings every item back
        every = page.locator(".cards .item").count()
        narrowed = []
        for label in ("Filter by severity", "Filter by rule family", "Filter by room"):
            box = page.get_by_label(label)
            if box.count():
                box.select_option(index=1)
                narrowed.append((label, page.locator(".cards .item").count()))
                if narrowed[-1][1] < every:
                    expect(page.get_by_text(f"Showing {narrowed[-1][1]} of {every}.")).to_be_visible()
                    shot("5c_filtered")
                    page.get_by_role("button", name="Show all").click()
                else:
                    box.select_option(index=0)
                expect(page.locator(".cards .item")).to_have_count(every)
        assert any(n < every for _, n in narrowed), f"no filter narrowed anything: {narrowed} of {every}"
        review_record = context.request.get(base + "api/projects/" + page.url.split("/submissions/")[1].split("/")[0] + "/coverage.html")
        assert review_record.status == 200 and "Shown on the plans (decided by a reviewer)" in review_record.text()

        page.get_by_role("button", name="Sign off and export").click()
        drawer = page.get_by_role("dialog")
        drawer.get_by_role("button", name="Sign", exact=True).first.click()
        expect(drawer.get_by_text("by Ada Martin").first).to_be_visible(timeout=30000)
        shot("7_sign_off")
        for label in ("Correction letter", "Marked up drawings", "Review record", "Spreadsheet", "BCF issues"):
            href = drawer.get_by_role("link", name=re.compile(label)).get_attribute("href")
            reply = context.request.get(base.rstrip("/") + href)
            assert reply.status == 200 and reply.body(), (label, reply.status)
        drawer.get_by_role("button", name="Close").click()
        page.set_viewport_size({"width": 390, "height": 800})
        page.wait_for_timeout(500)
        assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"), "desk scrolls sideways"
        page.set_viewport_size({"width": 1360, "height": 860})

        page.get_by_role("link", name="My work").first.click()
        expect(page.get_by_role("heading", name=re.compile("Comments assigned to you"))).to_be_visible(timeout=60000)
        expect(page.get_by_text("Due 2026-12-04")).to_be_visible()
        expect(page.get_by_text("12 Elm Street, permit 2026-0413").first).to_be_visible()
        shot("8_queue")

        # the applicant resubmits: the earlier drawing is kept and last round's comments are read against the new one
        page.locator(".lane .queue a").filter(has=page.locator(".title", has_text=re.compile("^12 Elm Street, permit 2026-0413"))).click()
        revised = Path(make_plan(work / "revised", png=False)["pdf"])             # the same plan, the door no longer narrow
        revised_name = revised.with_name("revised_" + revised.name)
        revised.rename(revised_name)
        page.locator("input[type=file]").nth(0).set_input_files(str(revised_name))
        expect(page.get_by_text(revised_name.name)).to_be_visible(timeout=60000)
        expect(page.get_by_role("link", name="Open the review desk")).to_be_visible(timeout=180000)
        page.get_by_role("link", name="Open the review desk").click()
        expect(page.get_by_role("tab", name=re.compile("^Resubmission"))).to_have_attribute("aria-selected", "true", timeout=60000)
        page.get_by_role("button", name="Check the comments against the new drawings").click()
        expect(page.locator(".resubmission .answer").first).to_be_visible(timeout=180000)
        shot("8b_resubmission")
        page.get_by_role("link", name="My work").first.click()

        page.get_by_role("link", name="Team").click()
        page.get_by_label("Email").fill("rene@example.test")
        page.get_by_role("button", name="Create invitation").click()
        link = page.locator(".notice code").inner_text()
        shot("9_team")

        other = browser.new_context(viewport={"width": 1360, "height": 860})
        guest = other.new_page()
        watch(guest)
        guest.goto(link)
        expect(guest.get_by_role("heading", name="Join Demo Permit Office")).to_be_visible()
        guest.screenshot(path=str(out / "10_invitation.png"))
        guest.get_by_label("Your full name").fill("Rene Dubois")
        guest.get_by_label("Choose a password").fill(secrets.token_urlsafe(18))
        guest.get_by_role("button", name="Create my account").click()
        expect(guest.get_by_role("heading", name="My work")).to_be_visible()
        expect(guest.get_by_role("link", name="Team")).to_have_count(0)

        page.set_viewport_size({"width": 390, "height": 800})
        page.get_by_role("link", name="My work").first.click()
        expect(page.get_by_role("heading", name="My work")).to_be_visible()
        shot("11_phone_queue")
        wide = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        page.get_by_role("button", name="Sign out").click()
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        browser.close()
    server.should_exit = True
    assert not errors, errors
    assert not outside, f"the pages loaded something from outside the server: {outside}"
    assert not wide, "the phone view scrolls sideways"
    print(f"walkthrough passed; pictures in {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "reports/web_walkthrough"))
