# M8: closing the loop, from a requirement clause to evidence and a coverage report (November 2026)

This page records the last link of the product: what happens after a rule is written. Before this, the system could read
a clause and show a preview. Now a reviewer approves the rule, the rule runs on the plan without any model, violations
appear on the drawing with the element and the value, and a report accounts for every clause of the document.

## Why this milestone

We looked at what current research and products do (see `docs/related_work.md` for the earlier survey). Three gaps keep
coming up, and each one is something a reviewer needs:

- **Traceability.** Few systems keep the path from a clause, to the rule written from it, to the result on the plan.
  ARCHER (2026) makes the interpretation a separate document for exactly this reason.
- **Missing data is not a failure.** A recent end-to-end system (Iversen and Huang, 2026) does not tell "the plan does
  not give this value" apart from "the plan breaks the rule", and re-runs the model on every check. We keep the two apart
  and reuse approved rules, so a re-check on a new version of the plan needs no model.
- **Coverage.** Reports list what was checked. They rarely say how much of the document was left unchecked, and why.

## What a reviewer can do now

1. Upload a plan and a requirement document.
2. In the Requirements tab, read each clause. The system writes a rule and shows it in plain words, or says why it could
   not (the clause needs something the plan does not provide, or no rule matching the sentence could be written).
3. Ask for a second reading of a rule. A second model compares the rule with the clause and lists what looks wrong.
   It never approves. If it raised notes, the reviewer must say they read them, and the notes stay on record.
4. Approve or reject the rule under a name. Approval is per clause and can be withdrawn.
5. Confirm that the plan reader found every room, door and window. Until a person confirms this, a rule over every
   member can show a violation but never a pass, because an element the reader missed could hide a problem.
6. Run the check. Approved rules run next to the older rules, with no model call.
7. Open the Results tab: violations are drawn on the plan with the element, the measured value and the limit, and the
   clause and approver are on each finding. Open the coverage report for the whole document.

## What was built

| Piece | Where | What it does |
|---|---|---|
| Findings from a rule | `interpreter/findings.py` | Evaluates a rule member by member and returns one finding per failing element with the measured value, the limit, and the outline to draw. A rule that cannot be decided becomes "not evaluated" with the missing facts. A rule that does not apply makes no finding |
| Approval | `app/interpret.py`, `interpreter/review.py` | Second reading, named approval, rejection, withdrawal. Approval keeps the second reader's notes when the reviewer acknowledged them. A new reading of a clause replaces the rule and removes its approval |
| Check | `pipeline.py` (`check`) | Runs approved rules on every sheet and saves the outcome of each one in `interpreted_results.json` |
| Coverage report | `report/coverage.py` | Every clause with its status, rule, approver, outcome and elements; JSON and a printable page |
| Endpoints | `app/api.py` | `POST /api/projects/{id}/review`, `POST /api/projects/{id}/decision`, `GET /api/projects/{id}/coverage`, `GET /api/projects/{id}/coverage.html` |
| Screens | `app/static/app.js`, `app.css` | Approval controls, the inventory confirmation, the coverage line and report link in the Results tab |

### Built on the shared verdict policy

The older rule engine and the interpreter now speak one verdict language (`docs/verdict-policy.md`, `outcomes.py`): every
finding carries an assessment with an outcome, typed reasons (for example INCOMPLETE_INVENTORY, UNVERIFIED_GEOMETRY,
MISSING_CONNECTION), the authority of the rule and the facts the answer rests on. Findings from approved rules use it too:

- outcome, reasons and dependencies come from the interpreter run, with `authority = approved requirement`;
- a rule where nothing wrong was found among what the plan reader found, but a person has not confirmed that it found
  everything, is a WARNING that says so, not a silent pass and not "not evaluated";
- a rule that needs facts the plan does not give stays NOT_EVALUATED with the missing facts named;
- the coverage report says in words why a clause could not be decided, using the same reason codes.

One change touches existing interpreter code: `approve_program` takes an optional `acknowledge` flag. Without it the
policy is exactly as before: any issue or limitation from the second reader blocks approval.

## What the report says about each clause

Violated, satisfied, does not apply, could not be decided from the plan (with the missing facts), rule written and
waiting for a reviewer, approved but the check not run yet, rejected, not checked because no rule could be written (with
the reason), and not read yet. A clause that could not be decided is never counted as a pass.

## Results

### Planted errors through the whole loop (real local model, 10 generated plans)

For each plan the example requirement document was uploaded, three clauses were read (door width, bedroom size, living
room size), the written rules were approved under a reviewer's name, the inventory was confirmed, and the check was run.
The older rule engine is the reference for which element is wrong: it finds every planted error on these plans. Two plans
are clean (no planted error) and measure false alarms; the others carry one or two planted errors.

| Measure | Result |
|---|---|
| Clause readings that produced a rule | 30 of 30 |
| Readings where the older engine finds an error | 15 |
| Of those, the approved rule reports the same element | 15 of 15 |
| An element the older engine found and the approved rule missed | 0 |
| An element the approved rule reported and the older engine did not | 0 |
| Clean plans: a violation reported (false alarm) | 0 of 6 clause runs |
| Clean plans: reported as undecided | 0 of 6 clause runs |

Limits of this measurement: 10 plans from one generator, three clauses about thresholds (the shape the drafting handles
best), a scripted empty second reading (the point was drafting and execution, not the critic), and the reviewer's
confirmation that the inventory is complete. It shows that when a rule is written correctly and approved, running it
reproduces what the validated engine reports, on the same elements, with no model call. It does not show how well the
system does on clause shapes it handles badly (ratios, routes), where the reviewer matters most.

### The example document with the real second reader

On the example requirement document (24 clauses), 7 clauses produced a rule and 17 were left with a reason. The 7 rules
were approved and run. The coverage report said "7 of 24 clauses decided on this plan (29%)": 4 violated, 3 satisfied,
17 not checked, each with its reason. The second reader raised notes on all 7 rules, so every approval needed the
reviewer's acknowledgement, and the notes are kept in the report.

### Tests

11 tests cover the findings (violation, pass, unknown, not applicable, two failed conditions, route note, wording) and 5
cover the web flow with a scripted model (read, approve, check without any model call, report, acknowledgement,
rejection, parallel reads). The CI command passes.


## Limits, plainly

- The second reader is a 7B model and is noisy. On the example document it raised notes on all 7 rules, several of them
  wrong ("omits clear width" when the rule did not). That is why a person decides and why the notes need an
  acknowledgement. It should be treated as a prompt to read the rule, not as a verdict.
- A route rule ("reaches an exit without passing through ...") written by the local model was approved on the example
  document and reported three false violations. No automatic check can confirm which rooms the sentence allows a route
  to pass through, so such rules now carry a note telling the reviewer to read them carefully. Route rules are the
  riskiest shape and the one the reviewer should read hardest.
- Rules about quantities the plan reader does not measure stay unresolved and appear in the report as such.
- "Satisfied" depends on the reviewer's confirmation that the plan reader found everything. The system cannot check that
  claim itself.
- The coverage share counts clauses that were decided on this plan. It does not say anything about how many of them a
  person agreed with.
- The front end was written and checked for syntax, and exercised through the API tests; it has not had a usability
  test with a real reviewer.

## Reproduce

```
pytest tests/app/test_closed_loop.py tests/unit/test_interpreter_findings.py     # scripted model, no Ollama
python scripts/closed_loop_demo.py <project id> "Your Name"                      # real model on a running app
python scripts/closed_loop_eval.py 10                                            # planted errors, real model
```
