# What changed today, in plain words

This sits on top of the last commit ("Close the loop"). That commit let a reviewer approve a rule and get findings on the
plan plus a coverage report. Today I made ReviewPulse understand more kinds of requirements, work for subjects that are not
buildings, and be easier to show and to trust.

## A user can now

**1. Check rules about connections, not only measurements.**
"Every room reaches an exit without passing through a bathroom", "no door joins a garage to a bedroom", "a room with one
door has a window", "the walk to an exit is at most 15 m". Before, these clauses came back as "not checked yet". Now the
rule is written, checked, approved and reported like any other.

**2. Use requirement documents with any unit, and in French.**
Litres, bar, minutes, kg/m3 and many more now work, not just metres. "500 L" in a document matches a fact stored in m3. A
French copy of the example document is included. Words like "WC" or "habitable room (bedroom, living room, kitchen)" are
understood, and a clause title like "Circulation." no longer blocks a correct rule.

**3. Read every rule in plain words before approving it.**
The Requirements tab and the coverage report now say, for example, "For every room where room type is bedroom: floor area is
at least 9 m2 and minimum width is at least 2.2 m", with the exact form underneath. This came from a real mistake the model
made: a rule that read like code hid that it was about every room instead of the whole dwelling.

**4. Get a definite answer when there is no exit.**
A plan with no door to the outside now fails the route rules clearly instead of saying "unknown".

**5. Show the work on 13 different plans.**
Each plan shows something different: a clean plan, a narrow door, small rooms, a bedroom reached only through the
bathroom, a garage next to a bedroom, a dead end, an exit too far, no exit, an isolated room, the same error on a rotated
page at another scale, several errors at once, another drawing style, and an L-shaped plan with furniture. The right answer
is written next to each one. A gallery page lists them with a report per plan.

**6. Use the same engine for something that is not a building.**
A water network (tanks, valves, pipes, an outlet) goes through the whole chain in an automated test: clause, rule, check,
finding, report. The core no longer assumes rooms, doors or an "exit".

## How we know

- All 13 variant plans, run through the whole product with a scripted model, agree with the older validated engine on which
  elements are wrong. This is automated: `pytest tests/app/test_scenarios.py`.
- The full test command passes (`pytest -q -m "not slow"`: 461 passed, 4 skipped, none failed).
- The sentence check did not get worse: 0 of 250 correct rules wrongly blocked, same catch rates as before.
- With the real local model on three plans (narrow door, bedroom through bathroom, rotated page) the right clauses were
  reported. It also showed one wrong rule (a per-room reading of "every dwelling has an exit"), which led to the fixes in
  point 3 and in the exit handling above.

## What it does not do yet

- Ratio rules ("at least 40 % of ...") are still the weakest kind the local model writes.
- Reading a 24-clause document with the local model takes about 15 minutes.
- Language support is tested on English and French only.
- A different domain still needs its own reader for its drawings or data; only the checking engine is shared.
- No real reviewer has used the screens yet.

The full list, with the reason and the next step for each, is in `docs/progress/M9_generality_variants_and_the_sweep.md`.

## Try it yourself

Every command, from setting up the terminal to testing in the browser, is in `docs/RUNBOOK.md`.
