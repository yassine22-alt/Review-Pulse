# M23: the real public correction lists, run through ReviewPulse (step 10a)

This note is for someone who has not followed the project. A plan reviewer does not write corrections from nothing: the office keeps
a canned list, and the reviewer circles the items that apply to the submission. The product claim I wanted to test is:

> ReviewPulse pre-circles the applicable items of a real correction list, with evidence.

I took the two real lists I hold, read them as a user would (upload the document, read every item), and recorded what happened to
every item. Everything below is measured on those two documents only. Nothing here has been confirmed by a reviewer.

**Status of this note.** The splitter work and the classification of items by what reviewers do with them need no model and are
finished. The model run (local model qwen2.5:7b, on the generated benchmark plan) and the evidence run are slow on this laptop and are
reported with the number of items finished. Section 4 says exactly how far the run got when I last updated this page. Partial rows
are never presented as complete.

## 1. The documents

| | Orange County 2019 CRC correction list | LADBS counter plan check correction sheet 2026 |
| --- | --- | --- |
| Pages | 21 | 11 |
| Items the source numbers | 239 (A1 to N23, in 13 lettered sections) | 146 numbered items in lettered sections (A to M, in two parts), plus tick boxes |
| Code citation | in brackets at the end, `[CRC R302.5.1]`: 197 of 283 top level items | a bare section number at the end of the item, `12.21A5(i)1` (no brackets) |
| Blanks and choices | 12 items with `____`, 14 with tick boxes or `(a) (b)` choices | 60 items with blanks `(      )`, 55 with tick boxes or choices |

## 2. Split quality: does the splitter give one clause per item id?

I printed what the splitter made of both lists and compared with the lists. The splitter was wrong in five general ways. None of them
is specific to these two documents; each is a layout accident that any canned list or checklist exported to PDF has. I fixed them
in `src/reviewpulse/rules/clauses.py` and raised `SPLITTER_VERSION` from 11 to 13 so no cached split is reused.

| What was wrong | Effect on the Orange County list | Fix |
| --- | --- | --- |
| An item id made of a letter and a number (`A1.`, `C17.`, `H3.`) was not recognised as a clause number, so items were cut into sentences called P1, P2 ... | 190 clauses with ids like `P17`, nothing a reviewer could match to the list | A letter (one or two capitals) that starts at least three lines as `<letter><number>.` is a series of item ids, the same rule the splitter already uses for a word and a number ("Rule 5") |
| A section reference wrapped to the start of a line (`... in accordance with CRC` / `R302.2.3. [CRC R302.2.2]`) started a clause | 2 clauses called `R302.2.3.` and `R302.4.` holding only a citation, and the real item above lost its citation | A reference that starts a wrapped line and is followed by a bracket or lower case continues the sentence; the tail of a bracketed citation never starts a clause |
| A decimal at the start of a wrapped line (`... water cement ratio of` / `0.45. No special inspection`) started a clause | Item A22 split in two and A33 swallowed by the fragment | A wrapped line that starts with a decimal and a full stop is not a clause number |
| The next item printed on the same line as the end of the one before (`... at time of recheck.A20. Complete ...`, `...(____).   13. (Continuous ...)`) | Items A20 (OC) and 13 of the structural section (LADBS) were glued to their neighbour | An id that is the next in its series (A19 then A20, 12 then 13) and follows a sentence end starts a line of its own. Page offsets are shifted by the breaks |
| A number alone on its line (`1.` then the sentence on the next line) and a number followed by a tick box (`3. ☐ (One) ☐ (Two)`) or a bracket | The first item of every LADBS section was glued to the end of the section before; items 3 and 13 were lost | Such a number is joined to its sentence; a tick box or a bracket after a number is accepted when the number ends with a full stop |

One more defect hid items from the app: "along **means** of egress" and "or other **means** as described" made two items "definitions",
and definitions are not read. "means" is now a definition word only when it is not "means of", "other means", "by means" and the like.

Result, counted by me on the printed split (`reports/correction_lists/oc_split_dump.txt`, `ladbs_split_dump.txt`):

| | Orange County | LADBS |
| --- | --- | --- |
| Clauses the splitter produces | 325 | 197 |
| Items read by the app (titles, headings, definitions left out) | 315 | 186 |
| Of them, items with an id of the list (`A1`, `H3`, or `3 [C. ADMINISTRATION]`) | 240 numbered clauses (the source ids A1 to N23, with the 3 exceptions below; M14 appears twice in the source) plus 43 sub numbered (`K10.1.`) and 29 lettered sub items (`A11 a)`) | 146 numbered, 32 tick box or lettered sub items |
| Items whose bracketed citation stays inside the item text | kept in the item text, as written, for the 197 top level items that carry one | not applicable (no brackets; the bare section number stays at the end of the text) |

Items the splitter still gets wrong, all visible in the dumps:

* Orange County `N.12` (a typing error in the source, a dot after the letter) is glued to `N11`; `K44 A.` (no dot) is glued to the
  exception above it; `I6.1` is the only trace of `I6`. Three source items out of 239 are not their own clause.
* Orange County `A23` to `A32` do not exist in the source (the list jumps from A22 to A33); I did not invent them.
* LADBS ids are the number plus the section heading, `3 [C. ADMINISTRATION]`, because the numbers restart in every section. They are
  unique and a reviewer can find them, but they are not the short `C.3` a person would write. Two sections whose heading line is
  not all capitals are sometimes missed, so a few items carry the number alone.
* LADBS has 5 table rows and 2 table headers that are the form header (plan check number, engineer, phone). They are not items.
  The roman numeral `II.` heading text is glued to LADBS instruction 6.
* The 55 tick box entries of LADBS (`☐ Floor Plans`, `☐ Use of Each Room`) are each a clause. They are options of an item, not
  instructions, and are counted as items in this note because the app reads them as clauses.

Regression check on the nine other real documents of the project (`scripts/split_audit.py`, same measures as M13): see section 6.
Tests: `tests/unit/test_correction_list_eval.py` (10 tests; ids, glued items, citation fragments, decimals, offsets, lone numbers).

The citation is kept as part of the item text, as written. It is not yet a field of its own: the product shows the clause as a quote
and a reviewer reads the bracket there. A separate `citation` field would be needed for the numbered correction letter (step 10b);
`scripts/correction_list_eval.py` already extracts it for measuring.

## 3. What reviewers do with each item (no model; keyword rules fixed before reading any result)

`scripts/correction_list_eval.py items` gives each item one class:

* **presence**: put it on the plans ("Show", "Provide", "Indicate", "Note on plan", "Add notes", "Specify ... on plans")
* **numeric limit**: a figure and a limit a drawing must meet ("minimum 36 in", "not less than 70 sf")
* **calculation**: calculations, analyses, compliance documents to attach
* **administrative**: fees, valuation, forms, affidavits, expiry, copies, sets of plans, appointments
* **site knowledge**: depends on the lot, the street, the zone, the grade, utilities (setbacks, sewer, hydrants, parking)
* **other statement**: a requirement written as a statement with no figure and no instruction verb ("Doors ... shall be self-closing")

I read 70 items (45 Orange County, 25 LADBS, a fixed random sample) against these classes. On the first version of the rules I found
5 wrong classes in the 45 Orange County items (a calculation word, "submit a schedule" read as paperwork, two "site" words that
were only a utility room and an outdoor light). I narrowed those words and kept the rest. The remaining wrong ones I found in the same
sample are 2 of 45 (an electrical circuit item read as site knowledge, an outdoor lighting item), so the accuracy of the class is
about 90 to 95% on the sample I tuned on and unknown elsewhere. Treat the shares as "about" within a few points.

| Class | Orange County (315 items) | LADBS (186 items) |
| --- | --- | --- |
| presence | 66 (21%) | 37 (20%) |
| numeric limit | 101 (32%) | 46 (25%) |
| calculation | 6 (2%) | 8 (4%) |
| administrative | 13 (4%) | 15 (8%) |
| site knowledge | 23 (7%) | 18 (10%) |
| other statement | 106 (34%) | 62 (33%) |

Facts about the items themselves:

| | Orange County | LADBS |
| --- | --- | --- |
| Items with a code citation | 206 of 315 | 78 of 186 (bare section numbers) |
| Items with a figure and unit | 118 | 59 |
| Items with a blank to fill (`____`, `(    )`) | 12 | 60 |
| Items with choices or tick boxes | 14 | 55 |
| Items with a condition word (if, where, when, exceeds ...) | 35 | 21 |
| Items conditional in any of those three ways | 59 (19%) | 89 (48%) |

A blank or a choice means the reviewer fills the item in for this project ("Provide ( ) paved parking spaces", "(36") (44")").
ReviewPulse reads the item with the blank as it stands. The missing piece is a form step: the reviewer states the value of the blank
and the item then becomes an ordinary item. Today a blank can end up as a rule with no number or be declined. A condition word means
the item applies only when something is true ("If house was constructed prior to 1994", "where windows are not provided"). The
requirement graph of M19 and M21 holds a condition for a sentence, and applicability has to be decided from project facts
(M20: use, storeys, sprinklers). I did not measure how many conditions it resolves; that is for section 5 once the run ends.

## 4. What the product did with each item (partial: 53 of 315 Orange County items, 3 of 186 LADBS items)

The run is slow on this laptop (about 25 seconds an item, triage then the arms). When I last updated this page it had finished the
first 53 items of the Orange County list (A1 to B12, in document order, so the sample is the start of the list and not random) and 3
of the LADBS sheet. **The shares below are for those 53 items only and say nothing yet about the whole list.** Evidence on the real
drawing sets has not started. The disk of this laptop was also full (0 MB free) while I worked; I did not delete anything, and the
job kept writing.

| Outcome of the first 53 Orange County items | Items |
| --- | --- |
| measured rule written | 8 (all of them wrong or partial, see section 5) |
| mention or presence rule | 0 |
| declined by triage "not checkable from a plan" | 31 |
| declined by the arms, with a "seems to need" phrase (my "question" outcome) | 13 |
| refused by grounding or the checks | 1 |

What the first 53 items show:

* **The triage declines most "put it on the plans" items.** A3 "Indicate a job address on all sheets", A6 "List all deferred submittals on
  cover sheet", A15 "show a property address on the street elevation", A17 "show location of all required BMPs" are presence items a
  reviewer circles on sight, and the local model's one question ("can a plan decide this?") says no with reasons such as "addresses" or
  "cover sheet". For a pre-circle product that is the wrong question: the item is applicable and the drawings can show it or not.
  The evidence step is what should answer these. It has not run yet.
* **Seven wrong measured rules, one cause, fixed.** Every one is a lettered sub item of A11 ("Provide a completely dimensioned
  plot plan showing: a) existing grades, ... j) show location of sewer line ...") that became the rule "the drawing carries dimension
  annotations". The sub item is read together with its lead sentence, the lead says "dimensioned plot plan", and the sheet rule
  fired on the lead; a pass of that rule says nothing about a sewer line. The general cause: a rule about the drawing as a whole
  was allowed for a list item, whose own content is a thing to be shown. In `xeval/relation_arm.py` a list item no longer gets the
  sheet level rule; the lead sentence itself keeps it, with the note that the items under it are not checked. Test:
  `test_a_list_item_under_a_sheet_level_lead_is_not_a_sheet_requirement`. The Orange County rows of these seven were produced by the
  code before the fix and will be read again once the run ends (the run resumes from `rows.jsonl`).

## 5. Hand grading (partial)

I read every measured rule written so far and every other finished item (45, more than the 40 asked for). Grades: right means the
outcome is correct and the reason shown is sensible; partial means the outcome is defensible but the reason shown is misleading or
the item is only half covered; wrong means a false claim about the item. The full list is in `reports/correction_lists/hand_grades.json`.

| | right | partial | wrong |
| --- | --- | --- | --- |
| 8 measured rules | 0 | 1 (A11 itself: "the drawing is dimensioned" is faithful to "completely dimensioned", with the list not checked) | 7 (the sub items above) |
| 45 other items (declined or questions) | 28 | 13 | 4 |

The 4 wrong declines are the presence items above (A3, A6, A15, A17): "not checkable from a plan" is false for a sentence whose
whole content is "show X on the plan". The 13 partial ones are mostly the same family with a less clear case (a note on the cover
sheet, a blank to fill in, a stamp and signature) and one decline whose reason is nonsense (B9 says it needs a conversion from feet
to meters). The 28 right ones are administrative items (fees, forms, permits), items that need the lot (fire separation distance),
and the A10, A11 sub items, which come back as a question that names what the item needs ("lot dimensions, bearings, easements and
setbacks"). B2 shows a refusal doing its job: the model proposed a door rule the sentence does not state and the grounding check
refused it.

## 6. Regression of the splitter on the other documents

I ran `scripts/split_audit.py` on the nine other real documents (the M13 audit) with the new splitter and compared with the audit
of 16 November (`reports/m14_split_audit2.json`).

| Document | Clauses before, after | Fragmented sentences | Clauses starting mid sentence |
| --- | --- | --- | --- |
| ADA 2010 standard | 2775, 2773 | 16, 15 | 15, 15 |
| UK Approved Document B | 2014, 2020 | 21, 21 | 4, 4 |
| St. Petersburg checklist | 132, 142 | 0, 0 | 0, 0 |
| Allentown, Berkeley, Bloomfield Hills, three French texts | unchanged | unchanged | unchanged |

What changed, read in the clause ids: St. Petersburg gained 10 clauses, the items `1.` to `10.` of its first list, which used to be
glued to the heading above (a lone number on its line). UK Approved Document B gained `B1` to `B5`, the regulation numbers, in place of
ids such as `Regulations 2010 (a)`. ADA lost four paragraph fragments and gained three `EXCEPTION` clauses. One of my first rules
(a wrapped line starting with `0.`) would have removed the UK paragraph numbers `0.5`, `0.10`; the audit showed it and I narrowed
it to a decimal followed by a full stop. The labels of the checklist benchmark are keyed by clause id and none of the labelled ids
moved. I did not re run the benchmark with the model for this note.

## 7. Run log

* Local model qwen2.5:7b, plan scenario 01 with the block of general notes, triage on, as "read all" does.
* Evidence on `data/real_plans/chief_architect_austin.pdf` and `rebuildflorida_floorplans.pdf` together.
* Files: `reports/correction_lists/oc/`, `reports/correction_lists/ladbs/` (`items.jsonl`, `rows.jsonl`, `evidence.jsonl`,
  `summary.json`). Documents and reports hold document text and are not committed.
