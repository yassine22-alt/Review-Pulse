# M30: a reviewer can decide any requirement

Written 27 November 2026. On the real checklist, none of the 14 items I tested with the model became a measured check
(`M29_review_desk_on_a_real_set.md`). The desk could show a note about an item but gave the reviewer no way to record what they
concluded, so most of a real checklist could not be finished in the app. This step lets a person finish it, with or without the
tool. **Status: built and tested by scripts; no reviewer has used it.**

## What a reviewer can record on any requirement

| Decision | Needed to record it | What happens |
| --- | --- | --- |
| Shown on the plans | a note or a sheet picked, or words saying what they relied on | counts as met, under their name |
| Needs correction | their comment | a numbered correction: their comment, then the requirement quoted, placed where they pointed |
| Does not apply | a reason (asked by the screen) | listed with the reason |
| Later submittal | who submits it and when (asked by the screen) | listed on the cover as deferred |

Rules kept (`report/reviewer_states.yaml`, tests in `tests/app/test_reviewer_decisions.py`):

* **The tool never marks anything shown or writes such a correction.** Both are only a person's.
* **No pass without evidence.** The server refuses "shown" with nothing to rest on, a sheet that is not part of the submission, a
  box that is not on the sheet, and a requirement the document does not have. For "does not apply" and "later submittal" the
  screen asks for a reason; the server does not insist, as before.
* The name is the signed in account's, and every decision and its withdrawal is in the audit trail.
* A decision replaces the tool's result on that requirement. When the tool had concluded otherwise, the record says what it had
  said.
* Corrections a reviewer writes are not counted as edits to the tool's proposals, so the edit burden still measures the tool.
* An undecided requirement is still never a pass.
* **A decision holds only for what it was made on.** Each one stores a digest of the drawings file and of the requirement's
  words. If the drawings are replaced or the words change, it stops counting: the item returns to "to decide" and shows the
  earlier decision with "confirm again". A deferral depends on the words only. I found this gap just before pushing: a
  "shown" recorded on one set would have kept passing after the set was replaced. Decisions stored before this have no
  digest and are taken as holding.

## On the screen

The Requirements tab is now the work list: how many are decided and how many are left, a search box, and on opening an item the
closest notes of the drawings, each with "show on the drawing" and "use as my evidence". After a decision the next undecided item
opens. The tool's measured checks are an option inside the item and in one folded line at the top. A **review record** export
lists every requirement with who decided it and why.

The note search needs no reading model (`GET /api/projects/{id}/notes`): words, meaning and reordering only.

## What the checks found

Two faults the browser walkthrough caught before this was pushed:

* every undecided card was styled as opened, hiding the requirement's words in the list (one word was used both for the group
  "left to decide" and for the opened style);
* a closed correction card written by a reviewer did not show their comment.

And one I saw in a screenshot: the top bar counted correction comments ("2 of 2 decided") while 21 requirements were left. It now
counts requirements.

## On the real permit set

On a copy of the project of M29: one item (garage separation) was recorded as shown on the plans with the garage door note as
evidence; the record and the screen updated in 1.0 s with no errors. The note search on four requirements that had not been read,
in a new process: 33 s for the first (loading), then 3.6 to 4.3 s each, over 530 notes. By my reading the wind speed requirement
got the answering note first; the first three notes for the flood zone, the site plan scale and the projection rating
requirements did not answer them.

## Limits

* The search covers written notes only: not symbols, drawing views or schedule cells as such. For many requirements it shows
  nothing useful.
* One decision per requirement. A requirement with several parts cannot be split, and a correction has at most one place.
* A decision is not tied to a review round.
* Any change to the drawings file makes every decision that rests on drawings need confirming, even if the sheet it used did not
  change. Accept, edit and sign off records are not covered by this.
* No keyboard shortcuts yet on the requirements list.
