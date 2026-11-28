# M26: connectors, so findings reach the systems reviewers and engineers already use

Written 25 November 2026, for anyone who joins the project or has to switch a connector on in a permit office.

## Why this exists

In `docs/REVIEWER_WORKFLOW.md` we found that a finding which cannot enter the reviewer's own process does not get used. Reviewers
mark PDFs in Bluebeam, inside Accela or OpenGov, and engineers exchange issues as BCF files. So I built one neutral shape for a
correction item and one adapter per route. The code is in `src/reviewpulse/connectors/`, the tests in `tests/unit/test_connectors.py`.

**What is and is not proven.** The 38 tests pass. They prove that our code builds the requests and files the vendor documents
describe, and that what we write we can read back. They do not prove that any vendor system accepts our requests: we have no
Accela, Bluebeam or OpenGov tenant and no credentials. Every vendor connector below is labelled **contract tested from
documentation, not tested live**. Nothing here is confirmed by a reviewer, so by our own rule it is "built", not "working".

## The neutral model

`ReviewComment` (`model.py`) holds: id, item number, discipline, code citation and its document, text, sheet, page (from 1),
box on the page in PDF points (unrotated page, origin top left, y down), state, severity, evidence quote, source facts (detected,
required, missing), cycle number, author, dates, status history and replies. `json_schema()` gives its JSON Schema, and
`from_findings()` builds comments from plain `findings.json` dicts without importing any other module of the project.

States: open, information requested, deferred, not applicable, addressed, verified, rejected, dismissed. A failed or warning
finding is `open`; a finding the plan could not decide (NOT_EVALUATED) becomes `information_requested`; a dismissed one is
`dismissed`. Passes are left out unless asked for. Sheet polygons (paper millimetres, y up) become page boxes with the same
conversion the annotated report uses; a page with a rotation is not handled (the box would be wrong), and I did not test it on
findings from real rotated sheets.

## What each connector does

| Route | What we build | Status |
| --- | --- | --- |
| PDF markups (`pdf_io.py`) | Write: a cloud (Polygon with `/BE` cloud effect) carrying the item (Subject = item number, Contents, T = author), a FreeText callout (`/IT /FreeTextCallout`, `/CL` leader), a sticky note, status as a reply with `/IRT`, `/StateModel (Review)`, `/State`. Read: any annotated PDF back into comments, with replies and status | Round trip tested; foreign style PDFs built with PyMuPDF; **never opened in Bluebeam Revu** |
| BCF 2.1 (`bcf.py`) | One topic per item, labels, priority, status, comments, viewpoint stub, snapshot crop, our `extensions.xsd`. Import of our files and of a hand written file from another tool | Validated against the buildingSMART release_2_1 XSDs; **not opened in Solibri, Revit or Trimble** |
| Accela Document Review (`accela.py`) | `POST .../documents/{id}/comments`, `POST .../checkin` (multipart) | Contract tested from documentation, not tested live |
| Bluebeam Studio (`bluebeam.py`) | Refresh token auth, create session, three step PDF upload, invite, finalize, snapshot, close | Contract tested from documentation, not tested live |
| OpenGov (`opengov.py`) | Plain text comments on a record's workflow step | Contract tested from documentation, not tested live; large limits below |
| File drop, webhook (`filedrop.py`) | JSON, CSV, a drop folder, a signed webhook | Our own formats, read back in tests; no office system has accepted them |

Command line: `python -m reviewpulse.connectors export --project <dir> --format pdf|bcf|json|csv`, plus `read-markups <pdf>` (a
previous cycle's markups into a comments file) and `push accela|bluebeam|opengov|webhook <comments.json>`, which is a dry run
unless `--live` is given. The export test builds a project folder by hand (findings, one building file, a PDF); I did not run it on
a real pipeline run folder.

## PDF annotations: what was measured and what was not

* Written files reread by PyMuPDF give back the text, citation, evidence quote, discipline, number, author, colour, state, status
  history with author, date and note, and replies. The box comes back within 2 points (the cloud's border widens it).
* Reading was tried on a hand made PDF in the style of other tools: a cloud polygon with a Revu style subject and author, a reply
  chain, Review status replies (Completed then Accepted gives state `verified`), highlight (text under it is kept as the quote), ink,
  line, stamp, a link (ignored), a rotated page, a reply to an object that does not exist and two annotations replying to each
  other. All were read without error, and the two broken cases are reported as warnings or kept as comments of their own. An
  encrypted PDF is refused with a message.
* **Limit.** That PDF was made with PyMuPDF, not exported from Revu. Real Revu files may use features I have not seen (for
  instance Bluebeam's own custom columns, which we do not read, or `Marked` models, which we read as `open`).
* **Limit.** I could not check how Revu draws our cloud and callout. The cloud is a Polygon with the cloud border effect and no
  custom appearance stream; whether Revu shows scallops from `/BE` or a plain outline I do not know. The callout leader line is
  stored in `/CL` but PyMuPDF's appearance stream draws only the box.
* **Limit.** Bluebeam's status is a five value model (None, Accepted, Rejected, Cancelled, Completed); ours has eight states.
  Reading a foreign status is exact; writing ours into Review is lossy, so our own state is also stored in a custom key
  (`/RPState`) and the whole item in `/RPJson`. A tool that rewrites the PDF and drops unknown keys will lose them, and a
  round trip then falls back to the Review status and the visible text.
* The task asked for "title = item number". In PDF, `/T` is the title bar and Bluebeam shows it as the author, so I put the item
  number in Subject and the author in `/T`.

## BCF

* Our findings come from PDF drawings, not an IFC model. So the viewpoint file is a stub (`VisualizationInfo` with a Guid only; no
  camera, no components) and the location is a **2D page reference in a snippet**: a `BimSnippet` of type
  `ReviewPulse2DPageReference` pointing at `page_reference.json` (file, page, box, sheet). A BCF viewer shows the topic with
  title, text, labels, status, priority, comments and a picture of the page crop, but cannot go to a place in a 3D model.
* Validation: I fetched `markup.xsd`, `visinfo.xsd`, `project.xsd` and `version.xsd` from `buildingSMART/BCF-XML`, branch
  `release_2_1`, saved them in `tests/fixtures/bcf21/`, and every file we write passes. The 2.1 repository has no
  `extensions.xsd`; `project.bcfp` names an extension schema by URI, so I wrote our own `extensions.xsd` (statuses, priorities,
  labels). It is well formed but has **not** been checked against any official schema, because none exists in 2.1.
* Round trip: export then import returns the same text, state, page, box, citation, discipline, number, severity, quote, status
  history and replies. A hand written BCF from "another tool" (status `Closed`, priority `High`) imports as `verified` and
  `major`. Status names we do not know become `open`.
* Not tested: BCF 3.0 (we only write 2.1), opening in any viewer, files from Solibri or Revit.

## Accela

Sources read on 25 November 2026: the Document Review page and the reference pages for Create Document Review Comments and
Checkin Document Review (the site blocked direct downloads, so I read them through a fetch tool), plus the HTTP headers page.
Implemented: `POST /v4/documentReview/documents/{documentId}/comments` with `comment`, `pageNumber`, optional `status` and
`discipline` objects; `POST /v4/documentReview/records/{recordId}/documents/{documentId}/checkin` as multipart with `uploadedFile`
and `fileInfo` (a JSON array with `serviceProviderCode`, `fileName`, `type`, `resubmit`, `description`). Headers:
`Authorization` with the bare token (the page shows no "Bearer"), `x-accela-appid`, optional agency and environment.

What a real office must do to switch it on:
1. Run Civic Platform (Automation) 7.3.3.5 or later with Document Review (EDR) enabled, and create an agency app in the Accela
   developer portal. Get the app id, agency name and environment name from the Accela administrator.
2. Get an access token for a dedicated third party user (Accela recommends one) with scope `documents`, using their OAuth login
   (authorization code or password flow). We do not implement the login; put the token in `ACCELA_ACCESS_TOKEN` and the app id in
   `ACCELA_APP_ID`. Tokens expire (the examples show 3600 and 28800 seconds), so the office's own job must renew them.
3. Find the document id and record id of the submittal, and the service provider code.
4. Learn the agency's configured status and discipline values (we send them only when you pass a map and the flag) and confirm on
   a test environment that `pageNumber` counts from 1 and that a PDF may be sent as `application/pdf` in `fileInfo` (the sample uses
   `text/plain` for a dummy file).
5. Run the dry run first (it is the default), read the recorded requests, then `--live` on a test record.

Limits: no update call (a changed comment is reported `skipped_changed`, not corrected); no read back of what Accela stored; a
timed out POST that is then retried can create a duplicate, because Accela documents no idempotency key.

## Bluebeam Studio

Sources: the Studio Session Guide and the Authentication Guide, read on 25 November 2026. **The API has no documented way to
create markups.** So the supported path is: write our findings into our own copy of the PDF, create a session, upload that PDF
(metadata block, `PUT` to the returned storage URL, confirm), and invite people. The markups then arrive inside the file. A
snapshot call merges session markups into a PDF for download, so a back check can read the reviewer's markups with `read_annotations`.

To switch it on: a Bluebeam developer account (the portal is for active customers and partners), a registered app with client id
and secret, one manual sign in to get the first refresh token with scopes `full_user offline_access`, then `BLUEBEAM_CLIENT_ID`,
`BLUEBEAM_CLIENT_SECRET`, `BLUEBEAM_REFRESH_TOKEN` in the environment (or a ready `BLUEBEAM_ACCESS_TOKEN`), and the right regional
host. Each refresh returns a new refresh token that must be kept by the office's own secret store (the callback `on_refresh_token`
receives it; we never write it); it dies after 7 days unused. Session default permissions are Deny through the API, so we set
`Markup: Allow`. PDF/A files are not supported by Studio. The guide does not say how long uploads or snapshots take, how big a file
may be, or what the snapshot call returns; I poll up to 30 times.

## OpenGov

The public API (v2, `api.plce.opengov.com/plce`) has **no document comment endpoint**. It has comments on workflow steps of a
record (text only, JSON:API), and a two step file upload that attaches files to a record. So the connector posts each item as a
step comment with the citation, sheet and page written into the text. It cannot put a cloud on a page, set a status, or attach
the annotated PDF (the upload and association shapes were read only in outline, so I did not write that part; use the file drop
for the PDF). Step comments are documented as visible to the applicant in v1, which I could not confirm for v2: treat every posted
item as applicant visible. The portal contradicts itself on authentication (one page says API key, the schema says OAuth2 client
credentials), so the module takes a ready bearer token from `OPENGOV_ACCESS_TOKEN` and does not fetch one. To switch it on, the
office needs API credentials with the Comment Write permission from OpenGov, the community subdomain, and the record and step ids.

## File drop and webhook

For offices with no API: JSON (our schema), CSV (UTF-8 with a byte order mark so Excel reads accents; the office maps columns),
a drop folder (files are written under a temporary name and renamed so a watcher never sees half a file), and one signed webhook
POST per list (HMAC SHA256 in `X-ReviewPulse-Signature`, secret from `REVIEWPULSE_WEBHOOK_SECRET`). The CSV comes back through
`read_csv`, so a reviewer can edit states in Excel; an unknown state is refused.

## Safety rules held in the code

* Tokens and secrets are read from the environment (or passed in memory) and nowhere else. Every request kept for a dry run or a
  test is redacted (authorization headers, `client_secret`, `refresh_token`, file bytes). A test checks that no secret and not even
  the dry run placeholder appears in what we keep. The posted ledger holds comment ids, a payload hash and the remote id only.
* The Bluebeam token is never sent to the storage host (the upload URL is pre signed); a test checks it.
* Dry run is the default everywhere, including the command line; it cannot reach the network because it uses a recording transport.
  The tests replace `urlopen` with a function that fails, so any accidental network use fails the test.
* Posting is idempotent per target: the same comment with the same payload is skipped on a second run, also across runs when a
  ledger file is given. 429, 502, 503, 504 and connection errors are retried with exponential backoff and `Retry-After`.

## What is not done

Not tested against any live system; not opened in Revu, Solibri, Revit or Trimble; no BCF 3.0; no Accela update or delete; no
OpenGov file upload; no automatic OAuth login for any vendor; no reading of Bluebeam custom columns; no handling of rotated
sheets when converting findings to page boxes. Each of these is a task for the first office that adopts a connector, starting with
a session with a real reviewer using the annotated PDF in their own tool.
