# M24: the correction list, reviewer states and sign off

Written 26 November 2026. This is steps 10b and 10c of `docs/PLAN_general_reviewpulse.md`. Code: `src/reviewpulse/report/correction_list.py`,
`report/reviewer_states.{py,yaml}`, `report/disciplines.{py,yaml}`, `app/workflow.py`, the Corrections tab in `app/static/`.
Tests: `tests/unit/test_correction_list.py`, `tests/unit/test_reviewer_states.py`, `tests/app/test_correction_list_api.py`.
Following our own rule in `docs/REVIEWER_WORKFLOW.md`, all of this is "built", not "working": no real reviewer has used it.

## What I built

* **The correction list.** The findings of a project become numbered items grouped by discipline, then by code chapter (the heading
  the requirement document puts above the clause when the document has two or more distinct headings, otherwise the clause number up
  to its first dot). Each item quotes the clause as written (the sentence the rule cites, else the clause), with the citation in
  brackets as the document gives it (`[CRC R311.6]`, else the clause number). No model writes any wording: it is a template from
  `reviewer_states.yaml` plus the quote plus, for a failure, the detected and required values. Each item also carries the sheet and
  the quarter of the sheet where the evidence is, the facts with their source, the state, and for an undecided item one question
  (the ledger's follow up question when there is one, else a fixed question built from the missing facts, the unconfirmed
  inventory, or "does this apply here" for an advisory pointer).
* **Formats.** `GET /api/projects/{pid}/correction-list?format=json|html|txt|pdf|bcf|csv` (and `file=true` for the JSON exchange
  file), plus `correction-list.pdf`. PDF, BCF, CSV and the exchange JSON reuse the connectors package (`ReviewComment`,
  `pdf_io.write_annotations`, `bcf.export_bcf`, `filedrop`); I did not duplicate it and did not change it. The PDF is a copy of the
  submitted PDF with the connectors' annotations (a cloud polygon on the evidence box, a callout, a note), item number in Subject. A
  non PDF plan is redrawn as vector pages first. An item with no spot on a sheet gets a note at the top left of its sheet's page.
* **Reviewer states, one data file.** `reviewer_states.yaml` maps verdicts and outcomes to the six statuses (Approved, Approved with
  comments, Information requested, Revision required, Not applicable, Deferred submittal), the roll up of each to an overall result,
  the order Rejected > Revision required > Approved with comments > Approved > Not required, and the wording templates. FAIL is
  Revision required; WARNING and NOT_EVALUATED are Information requested; nothing undecided rolls up to Approved
  (`check_policy()` is tested). The tool never proposes Rejected; while any clause was not decided on the plan, the proposal is no
  better than Approved with comments. The internal verdict policy is untouched.
* **Deferred and not applicable** are set by a named reviewer per clause (`PUT /clause-states`). A deferred clause leaves the list,
  appears on the cover (text and HTML) and is neither a correction nor a failure.
* **Discipline tags.** `disciplines.yaml` has cue words in en, fr, de, es for nine disciplines plus sheet number prefixes; a clause or
  sheet title scores one point per cue, accents and case ignored, whole word (a starred cue matches a word start, for German
  compounds). No code names a discipline.
* **Edit burden.** The Corrections view lets the reviewer accept, edit the wording, or drop each item, set a clause deferred or not
  applicable, sign off per discipline, and export. Edits are stored under the project; the list reports items, accepted, edited,
  dropped, not reviewed, the edit count and the mean share of text changed in edited items.
* **Sign off and audit.** `POST /signoffs` needs a reviewer name, a known discipline and result, and a cycle; every sign off is kept
  and the latest per cycle and discipline counts. `GET /audit` lists who, what, when for edits, states, sign offs and rule decisions.

## What I measured

Everything below is from tests with generated demo plans (`synth/scenarios.py`) and a scripted model; no Ollama.

* `tests/unit/test_reviewer_states.py` and `test_correction_list.py`: 45 tests pass, covering the mapping, the overall result, 16
  clause texts tagged in four languages, sheet tags, grouping, citations, deferred, edits, the marked up PDF (also on a rotated
  page) and every export format reading back.
* `tests/app/test_correction_list_api.py`: 9 tests pass on scenario 02 (one door 0.70 m against 0.80 m) as PDF and DXF and on scenario
  10 (page rotated 90 degrees, 1:50). The planted door becomes one item, Revision required, `[Art. 6.1]`, with its measured value and
  source; in the marked up PDF the cloud annotation lands on drawn content (checked independently with the page's own vector
  drawings), also on the rotated page. Name required for edits, states and sign off; audit trail lists who, what, when.

* **The real plan and checklist run is not finished.** I ran `scripts/correction_list_demo.py` on
  `data/real_plans/chief_architect_austin.pdf` with `data/real_docs/us_stpete_residential_checklist.pdf`, without a model.
  * The first run found a bug: after the plan analysis, uploading the checklist failed because the project's empty folders were
    gone. No app code removes them; I believe something outside the app cleaned the temporary folder, but I have not confirmed it.
    The app now restores missing project folders (`app/store.py`, tests in `tests/unit/test_store_folders.py`).
  * The second run passed the upload and split the checklist into 142 clauses. It had read 18 of them about 20 minutes later, with
    other jobs on the laptop, and I stopped it. Reading a long checklist against a large drawing set is too slow today.
  * No number about the resulting correction list is claimed.

## What a reviewer would still have to do

* Read every item. Nothing here has been confirmed by a reviewer, and edit burden, time and trust (measures 4, 5, 7 of section 6 of
  the workflow page) are not measured on real submissions.
* Write the many items that are not in the list: only clauses that became an approved rule produce items, and the rest are counted
  as not decided, not listed.
* Judge wording. A quoted clause is faithful but not always an instruction: "Every door has a clear width of at least 0.80 m" after
  "Revise the plans to comply" reads stiffly, and a clause with a blank to fill is not filled.
* Decide "Information requested" items that only ask for a confirmed inventory; the question is generic.
* Open the PDF in Bluebeam Revu. We have not: the annotations are standard types written by PyMuPDF and read back by it.
* Place evidence: the box is the evidence polygon of the rule, or the matched note text; an item without a spot is a note at the
  top left of the sheet.

## Losses and limits

* Grouping by document heading is skipped when the document has only one heading, so a document with no headings is grouped by
  clause number.
* Two rules for one clause become one item (keyed by clause); their facts are deduplicated only when they name the same element.
* Discipline tags are cue counts: a short clause may fall to "general", and a clause with cues of two disciplines goes to the
  first in `tie_order`.
* Raster plans: the markup PDF has no copy to annotate (the redraw has only vector content).
* No evidence crop picture in the HTML or text list (BCF topics carry a crop).
* The connectors package's own limits apply (`docs/progress/M26_connectors.md`).
