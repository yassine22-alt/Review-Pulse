# M7: rule extraction, the facts graph and stairs (November 2026)

This page records what we built for rule extraction and the facts layer, what we measured, and where it stops. Every
number below comes from a script in this repository, and each one says what it was measured on.

## In short

ReviewPulse reads a plan into facts, reads a requirement document into rules, and judges the facts against the rules.
The judge never turns "unknown" into a pass. The weak part was rule extraction: a 7B local model asked to write a rule
from a sentence produced a correct rule in about 1 case in 10. We changed how the model is asked and added checks that
do not depend on the model. On the same test sentences the correct rate is now 83%, and the dangerous failure (a rule
that looks valid but says something different from the sentence) fell from 70% to 5%. On real regulation sentences the
system no longer writes a wrong rule: it says the clause is unresolved. On the plan side we added a stair finder,
because stairs are one of the things requirements ask about most and the plan reader did not measure them at all.

Nothing here assumes a type of project, a type of plan, a language or a document format. We did no annotation.

## The three layers

1. **Plan to facts.** A graph of the things on the plan (rooms, doors, windows, stairs, the building itself) with
   measured values. Each value carries where it came from and whether it can be trusted. Format: `schemas/factgraph.schema.json`,
   code: `src/reviewpulse/factgraph/`. Anything the reader cannot measure stays unknown.
2. **Document to rules.** A model drafts a rule for a clause, deterministic checks test the draft against the clause
   and against the facts that exist, and a person approves. Code: `src/reviewpulse/xeval/` (drafting formats, checks)
   on top of the interpreter from the `rule-interpreter` branch (`src/reviewpulse/interpreter/`).
3. **Judge.** A deterministic three-valued judge: satisfied, violated, not applicable, exempt, or unresolved.

## What we built

| Piece | Where | What it does |
|---|---|---|
| Fact graph | `factgraph/` | One file format for the facts of a building, with a reader for the interpreter and a producer from the existing plan reader |
| Expression format for drafting | `xeval/expr_ir.py`, `xeval/expr_arms.py` | The model writes the rule as one readable line such as `forall doors d: d.width_m >= 0.8 m`; our own parser builds the rule structure |
| Sentence check | `xeval/verify.py`, `xeval/cues.yaml` | Compares a draft with its sentence: dropped category, wrong or ignored number, comparison pointing the wrong way, a sum in the sentence but not in the rule. Wording tables for 9 languages live in data, not code |
| Catalogue checks | `xeval/semantic.py` | A fact read from the wrong owner, a text value that is not a declared value, a building condition placed inside a member filter, a rule about a quantity the sentence never mentions |
| Unresolved status | `xeval/status.py` | A clause with no usable rule ends as UNRESOLVED with a reason in plain words, never a silent drop and never a guess |
| Measuring harness | `xeval/` (synth, world, behavior, report, run) | Builds test sentences with known answers, scores a draft by how it behaves on generated plans, and writes the findings |
| Demand analysis | `xeval/demand.py` | Reads a body of requirements and says what they ask to be measured and whether the plan reader supplies it |
| Stair finder | `perception/stairs.py` | Finds stair flights from their tread lines and measures tread depth and width, with an uncertainty and a calibrated confidence |

### Where it is wired in

- **API:** `POST /api/interpreter/draft_checked` (in `interpreter/api.py`) takes a clause context, the plan's inputs and
  optionally its fact graph, and returns either a checked rule with a plain readback or UNRESOLVED with the reason.
  The original `/api/interpreter/draft` is unchanged.
- **App:** a Requirements tab shows the uploaded document clause by clause, what was extracted from each clause, and
  what the rule gives on the project's own plan (a preview, not an approval). Server side: `app/interpret.py` and the
  endpoints `GET /api/projects/{id}/document`, `GET /api/projects/{id}/interpreted`, `POST /api/projects/{id}/interpret`
  (all clauses, as a job) and `POST /api/projects/{id}/interpret/{clause}` (one clause).
- **Plan reader:** `pipeline.build_model` now adds the stair flights it finds (only when the scale is known). A failure
  in the stair finder is recorded as a warning and never loses the building.
- The code shared by these lives in `xeval/` for now because it grew out of the evaluation. Moving it into the
  interpreter package is a rename, not a change of behaviour.

## Results

### Rule drafting (synthetic sentences with known answers, 60 per run, local model qwen2.5:7b)

A draft counts as right only when it behaves like the reference rule on generated plans.

| Way of asking | Valid | Right | Valid but wrong |
|---|---|---|---|
| Interpreter's original recursive format | 3% | 0% | 3% |
| Recursive format with a worked example (30 sentences) | 80% | 10% | 70% |
| Flat table of nodes (30 sentences) | 23% | 13% | 10% |
| One-line expression, no checks | 82% | 67% | 15% |
| **One-line expression + sentence check + one repair** | **88%** | **83%** | **5%** |

Numbers are on 30 or 60 sentences, so the 95% intervals are wide (for 83% on 60, about 72% to 91%). The sentences are
synthetic, in English and French. A rule that is valid but wrong is the dangerous case, because a reviewer could
approve it.

What did not help: asking three times and keeping answers that agree. The model agrees with itself even when it is
wrong (only 1 clause in 60 disagreed), at three times the time. A second model as a judge of "is the sentence about
this fact" was also tried and rejected: it either blocked correct rules (37 of 80) or missed wrong ones (3 of 4).

### The checks themselves (no model involved)

| Check | Result |
|---|---|
| Correct reference rules wrongly blocked | 0 of 250 |
| Threshold changed, caught | 384 of 384 |
| Category condition dropped, caught | 127 of 127 |
| Comparison direction flipped, caught | 328 of 384 (85%) |
| Seven meaning-preserving rewrites of the sentence (spacing, shouting, added references, unit changes) | 0 wrongly blocked |
| Scoring method: broken variants of rules caught | 392 of 392 |

### Real regulation sentences

60 sentences containing a measurement, drawn from CODE-ACCORD (public, CC BY 4.0), drafted against the facts of a
real plan. There are no reference rules for them, so we read the results.

| | Before the grounding check | After |
|---|---|---|
| Drafted as a rule | 4, all wrong ("the tread is at least 270 mm" became "every door is at least 0.27 m wide") | 0 |
| Unresolved | 56 | 60 |

Only 10 of the 60 sentences mention a door, a room, a window or an opening. Most real requirements ask about things the
plan reader does not measure, and "unresolved" is the right answer for them. One sentence was expressible (a bedroom
with a minimum area and width) and was still left unresolved because the model wrote a category that is not declared.
These numbers show the checks stop wrong rules. They do not show how many right rules real documents give.

### Stairs

Stairs are measured from geometry alone: no layer names, no text, no labels. A flight is a comb of parallel tread
lines at an even pitch. The finder fits that comb, tests it against chance, and reports the tread depth with a standard
error.

| Measured on | Result |
|---|---|
| 200 synthetic flights drawn in many styles with known truth | found 98%; tread depth error median 0.00 cm, 95th percentile 0.05 cm, largest 0.08 cm; tread count exactly right in 190 of 195; 110 flights marked trusted, none with a depth off by more than 1 cm |
| 200 synthetic drawings with clutter and no stair | a false stair on 3% |
| FloorPlanCAD, 150 drawings with labelled stairs | a labelled stair is found in 57% of cases; 88% of detections touch a labelled stair |
| FloorPlanCAD, 150 drawings with no stairs | a detection on 12% of drawings (escalators, tables and wall grids look alike) |
| Confidence model, drawings it was not fitted on | detections the model rates at 0.8 or more are real 97% of the time and keep 76% of detections |

The tread depth and width on real drawings could not be checked against truth, because FloorPlanCAD labels which lines
are a stair but gives no measurements. The synthetic stairs are what show the measurement is accurate.

Because the finder reaches about half of the stairs that are drawn, the fact graph never says its list of stairs is
complete. A rule over stairs reads UNRESOLVED instead of passing because none were found.

### What requirements ask for

From 862 CODE-ACCORD sentences: 19% contain a number, 5% are counts without units, and 76% contain no quantity. Of the
sentences without a number, most ask for a route, a connection or the presence of something, which a graph can answer.
With stairs added, the share of quantity requests the plan reader can supply fully or partly went from 47% to 56%.

## Decisions and why

- **Ask the model for a one-line expression, not a nested structure.** Same model, same sentences: right went from 10%
  to 67%. The structure is built by code we control.
- **Check the draft against its sentence with code, not with another model.** The code checks never blocked a correct
  rule in 250 tries. The model judge did.
- **Block a rule that restricts to a category the sentence never names, and a rule that measures something the
  sentence never mentions.** Both found by reading the wrong rules, then confirmed on 250 correct rules.
- **Report unresolved, with the reason, rather than the best guess.** A missed clause is visible. A wrong rule is not.
- **Test stairs with a statistical model, not hand-tuned thresholds.** The first stair finder used tuned cut-offs and
  found 66% with 100% precision on one sample, but we could not say why it worked. The second states a model of a
  flight and a chance bound, and the confidence is calibrated on drawings it was not fitted on.
- **A stair is not trusted unless the fit is tight, the chance of a false flight is very small and the calibrated
  confidence is at least 0.8.**

## Limits, plainly

- Drafting was measured on synthetic sentences with one 7B model. The real-sentence test shows safe behaviour, not
  coverage.
- The wording check and the grounding check are strongest in English and French. The other seven languages in
  `cues.yaml` are covered by unit tests only. The grounding check runs only on English.
- The grounding check needs the fact descriptions to share words with the sentence. A sentence that uses a synonym the
  catalogue lacks comes back unresolved, never passed.
- The stair finder misses curved and spiral stairs, stairs drawn with only tick marks, and short flights with fewer than
  four treads. The calibration was fitted on one dataset (FloorPlanCAD) and may need refitting on other drawing styles.
- Heights, storeys, occupants and loads are not read from plans. They are building data that a user supplies or that a
  schedule gives; until then rules about them are unresolved.
- Ratio requirements ("at least 40% of the sum of ...") are the weakest shape: none of 6 matched the reference exactly. Two
  of them are the right rule written as a product instead of a quotient, which differs only when the denominator is
  empty; the other four were rejected by the unit and scope checks.
- Route requirements ("reaches an exit without passing through ...") are supported by the rule format and the judge, and
  tested end to end with a scripted model, but the 7B model does not yet write them reliably: on the example document
  they come back unresolved.
- Three rules in sixty are still valid and wrong, and no current check sees them (two differ only on an edge case: a ratio over no members).

## Reproduce

All commands run from the repository root with `PYTHONPATH=src`.

```
python -m reviewpulse.xeval setup                 # check the local model and build the test corpus
python -m reviewpulse.xeval scorer                # the scoring method catches broken rules
python -m reviewpulse.xeval verifier              # the sentence check on 250 rules and seven rewrites
python -m reviewpulse.xeval ablate --n 60         # compare ways of asking (long: background job)
python -m reviewpulse.xeval.report ablate         # write the findings page
python scripts/stairs_synth.py 200                # stair accuracy against known truth
python scripts/stairs_eval.py 150                 # stairs against FloorPlanCAD labels
python scripts/stairs_calibrate.py 600            # refit the stair confidence model
python scripts/walkthrough.py                     # drive the running app through a plan and a requirement document
```

Raw data is fetched by `scripts/fetch_datasets.py` and is not in git. Reports go to `reports/extractor_eval/`.
