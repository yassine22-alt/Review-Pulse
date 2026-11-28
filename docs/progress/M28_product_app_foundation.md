# M28: the product app, foundation

Written 26 November 2026, for anyone who will run or extend the web app. It is the first step of turning ReviewPulse from a
single user tool into an app a permit office can use. First user: the office's plan reviewer. It must run on the office's own
machines.

**Status: built and walked through in a browser by a script. No reviewer or office has used it. It has had no independent
security review.**

## Run it

```bash
pip install -e ".[app]"
cd frontend && npm ci && npm run build && cd ..
rp create-admin                 # asks for the office name, your email, name and password
rp serve                        # http://127.0.0.1:8000
```

There is no default account. The administrator invites everyone else from the Team page; the link is shown once and sent by the
administrator, so no mail server is needed. Projects made before accounts existed are given to an office with
`rp create-admin --adopt-projects`. `rp serve --no-accounts` keeps the older single user pages and works only on 127.0.0.1.

To serve other machines, put the app behind HTTPS (a reverse proxy) and set `REVIEWPULSE_SECURE_COOKIES=1`. Over plain HTTP,
passwords cross the network in clear.

## What the screens do

| Screen | What happens there |
| --- | --- |
| Sign in, invitation | Account entry. The picture beside the form is labelled as an example |
| My work | Submissions in three groups with their totals: ready for you, being read, missing something |
| Submission | Upload drawings and the code or checklist, watch progress, open the review desk or the correction list |
| **Review desk** | The drawing with numbered pins beside two lists, see below |
| Team | Invite people with a role, turn accounts off |

**The review desk.** *Requirements*: read a requirement, see the check that would run and a preview on this plan, take a second
reading, approve or reject, then run the checks. A reviewer can confirm that every room, door and window was found; without it a
check cannot report a pass. *Corrections*: choosing an item flies the drawing to its place and shows, in this order, the
requirement as written, what was read on the drawings and from where, what is needed to decide, and the comment to the applicant.
The reviewer accepts, edits or drops it, sets it aside as deferred or not applicable, then signs off by discipline and exports a
letter, marked up drawings, CSV or BCF. Keys: J and K move, Enter zooms, A accepts, E edits, D drops, Escape shows the sheet.

**Design choices and their source.** I looked at how comparable products describe their screens (CrossBeam's release notes,
CodeComply, Bluebeam's markups list, the Autodesk Build sheet viewer). These are vendor pages: they show what those products
offer, not that it works well. I took the familiar parts (numbered pins, a status filter, keys to step through findings, a sheet
strip with counts, tools on the drawing). What I want ours to be known for: the rule and the reading sit beside the drawing, an
undecided item says what is needed, no confidence number is shown, and an item that has a place on a sheet cannot be accepted
before it has been opened (see section 9 of `REVIEWER_WORKFLOW.md` on over reliance). None of this has been tried with a reviewer.

**Not there yet:** the applicant's response page, the back check screen, history across rounds, completeness and assignment,
drawing your own comment or cloud on the sheet, confirming single doors or rooms on the drawing (still only in the older pages),
accepted exit and mezzanine settings of the older pages.

## Security design

| Concern | What the code does (`src/reviewpulse/app/auth/`) |
| --- | --- |
| A route left open | One gate in front of every request; everything under `/api` needs a session unless listed as public; a route no rule names needs an administrator |
| Passwords | Argon2id; 12 to 128 characters, no composition rules; a short list of obvious ones refused |
| Sessions | Random token, only its SHA-256 stored; HttpOnly, SameSite=Strict cookie, Secure under HTTPS; ends after 2 hours idle or 12 hours |
| Forged requests | Every change needs a per session token in a header |
| Guessing | After 5 failures for one email from one address, a 15 minute pause; the refusal is the same whether the account exists |
| Between offices | Another office's project answers "not found" on every route |
| Roles | Administrator, coordinator (intake, no decisions), reviewer (decisions and sign off), applicant (no submissions yet) |
| Who signed | Approvals, sign offs, states, edits and the audit trail take the signed in account's name; a name typed in the request is ignored |
| The web pages | Everything is served by the app, with a content security policy; the walkthrough fails on any outside request |

## How it is checked

* `tests/app/test_accounts.py`, 11 tests: every route in the API description refuses a request without a session; offices are
  separated; roles hold; typed names are ignored; the forged request header; cookie flags; guessing; invitations; expiry; no
  plain password or token in the database file.
* `python scripts/web_walkthrough.py`: a real browser signs in (refused first with a wrong password), uploads a generated plan with
  one door 0.70 m wide, approves the door width check on the review desk, runs it, opens the finding, accepts it from the keyboard
  under the signed in name, signs off, opens all four exports, invites a colleague who joins in a second browser, and checks phone
  width. It fails on a script error or any request outside the server. **The clause reading model is a scripted stand in**, so this
  shows the screens and the server work together, not how well requirements are read.
* Not checked: other browsers than Edge, screen readers, large real drawing sets on the review desk, more than one sheet.

## Limits and what is missing for production

* No password reset or change, no second factor, no single sign on. An administrator cannot yet reset a password.
* The pause on guessing is per email and address; guessing across many addresses is not limited. A reverse proxy should add a
  general rate limit. Behind a proxy, the address seen is the proxy's unless it is configured to pass the real one, so the
  pause would then be shared by everyone.
* Sign in events are recorded in the account database; there is no screen or export for them.
* Uploads are read into memory (200 MB limit) and are not scanned for malware.
* Accounts live in one SQLite file next to the projects. Back up both together.
* The Docker image now builds the web pages, but I have not built or run the image.
* Reading a large drawing set against a long checklist is slow (see `M24_correction_list_and_states.md`). The review desk
  depends on fixing that.
