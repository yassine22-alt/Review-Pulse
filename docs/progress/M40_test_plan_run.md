# M40: our test plan, run

Written 28 November 2026, on branch `product-app`, on one laptop (6 GB graphics card), with the trained drawing model installed
and `qwen2.5:7b` as the local reading model.

**16 of the 19 test cases gave the expected result, 1 did not as it is written, and 2 were not run.** These are runs by the
team, not acceptance by users: no plan reviewer took part.

| Case | Result | What was seen |
| --- | --- | --- |
| TC-01 plan upload reads a generated plan | Met | 7 rooms, 7 doors, 6 windows; scale found from the dimensions; trained model used; backdrop served |
| TC-02 planted errors found end to end | Met | `rp doctor`: 3 of 3 through DXF, PDF and the web app |
| TC-03 requirement document read into clauses and tables | **Not met as written** | UK volume: **164 of 167** table references reach a table; the case asks for at least 165 of 168. Same result on two runs. The three that do not resolve are the same tables (8.1, 9, 10) as before, recorded then as tables of other documents. The code of the day the old figure was written gives 164 of 167 today too, so later changes did not cause the difference; why the old note says 165 of 168 I could not find out |
| TC-04 a sentence becomes a correct rule | Met | Local model: every room of type corridor at least 0.9144 m wide, as a draft |
| TC-05 no rule runs without approval | Met | Before approval the check refuses to run; after it, the rule's finding is listed. It is a warning, not a pass, because nobody had confirmed that every room was found |
| TC-06 unknown is never a pass | Met | With one door width removed the finding is "not decided" and names the missing fact and the door |
| TC-07 conflicting sources stay a conflict | Met | Automated test: both values and both sources shown, none chosen, rule undecided |
| TC-08 a wrong rule is rejected | Met | Automated tests: the changed copy differs and the node to repair is named |
| TC-09 a quote outside the clause is refused | Met | Automated tests of the grounding check: "quote not found in the clause" |
| TC-10 evidence found in the drawing notes | Met, **with a defect found** | The smoke alarm note is shown with its sheet and words, with no verdict. See below |
| TC-11 no invented evidence on a set with no answers | Met | 44 of 46 lines return no note (at least 43 asked) |
| TC-12 a dash for a fire rating is not a failure | Met, after a fix | The door is "not decided", never failed. The message used internal names; now it says what is not established, for which door, and asks to check |
| TC-13 hosted model needs consent | Met | A stand in for the hosted model got nothing with consent off, and 4 questions with it on: the clause and the list of facts. None of 35 text lines of the plan, no file or project name, no picture. No connection left the machine. No real hosted model was called |
| TC-14 scanned French checklist keeps its lines | Met | 60 of 60 lines; 185 of 187 accented words keep their accents. The scan is one the test script makes from the text, not paper put through a scanner |
| TC-15 callouts resolve | Met | 28 of 42 resolve to a view; each other one is listed with its reason (the sheet exists, the view was not found on it); rotating pages changes nothing. Renaming a sheet did change the counts, which this case does not ask about |
| TC-16 file endpoint refuses path tricks | Met | Six path tricks and two requests across offices: all refused with 404 |
| TC-17 reading time of a long standard | Met | ADA 2010: 102 s and 105 s (limit 180 s), same 2773 clauses. **Not tried on a second machine** |
| TC-18 reviewer correction list | **Not run** | Needs a real reviewer |
| TC-19 coverage against a real correction letter | **Not run** | Needs a submission with its real correction letter |

## What the run found, and what I changed

* **A note's figure could look like proof that a requirement is met.** For "windows with sills 24 in or less above the floor need
  a protection device", the evidence search chose a note about safety glass within 24 in of a door, and said the figures
  "agree". The units and numbers matched; the subject did not. **The choice of note is not fixed.** The wording is: the app now
  asks the reviewer to check first that both figures are about the same thing, and no longer says the note meets the
  requirement. The one planted contradiction on that run was not caught, for the same line.
* **Undecided findings were written with internal names** ("missing d0.fire_rating_min"). They are now in words.
* A grammar mistake in a warning was corrected.
* **A long requirement document was read twice**: once at upload, and again when the review screen first asked for it. The first
  read is now kept; the review screen then gets the document in 0.1 s. My first timing of TC-17 (208 s and 213 s) ran the app
  without accounts, a mode for scripts that reads and drafts everything at upload. The times above are of the app as served.

## How to run it again

    rp doctor                                                        TC-02
    python scripts/table_refs.py data/real_docs                      TC-03
    python scripts/test_plan_run.py                                  TC-01, 04, 05, 13, 16
    python scripts/evidence_eval.py --plans <drawing set .pdf>       TC-10, 11
    python scripts/format_robustness.py --docs <checklist .pdf>      TC-14
    python scripts/drawingset_audit.py <drawing set .pdf>            TC-15
    python scripts/tc_long_standard.py data/real_docs/ada_2010.pdf   TC-17

TC-07 to 09 are in `tests/unit` (`test_ledger.py`, `test_normative.py`, `test_rule_quality_checks.py`). TC-06 and TC-12 were run
on the small hand made plan of the tests; `test_interpreter_findings.py` now checks their wording. The real documents and
drawing sets are not in the repository.
