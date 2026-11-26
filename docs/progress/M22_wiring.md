# M22: the new packages in the real review path

Written 25 November 2026. M16 to M19 built a drawing set model, a fact request ledger, a general sheet table reader and a
regulation graph beside the review path. This step connects them to it, each behind a switch, with new logic in new modules and
small edits in the existing files.

## What is wired and how to turn it off

| Piece | Where it enters | Switch | Default |
| --- | --- | --- | --- |
| Ledger | `pipeline._run_programs` and `app/interpret._plan` build the rule inputs with `ledger/wiring.build_inputs` instead of `to_inputs` | `REVIEWPULSE_LEDGER=off` gives the old conversion and no resolutions | on |
| Finding wording | `interpreter/findings.to_findings(..., resolutions=)`: a NOT_EVALUATED finding lists the unsettled facts (`Resolution.explain()`, which names both sources of a conflict) and the reviewer question (`followup()`) | follows the ledger switch (no resolutions, old wording) | on |
| Attestations | `app/interpret.attest` writes `drafts/attestations.json` (name and source mandatory); `app/service.check` passes them to `pipeline.check` | follows the ledger switch | on |
| Sheet tables, schedule reader | `annotate/schedules.find_schedules` merges the general reader's door fire ratings (`schedules/legacy.py`); the old reader stays and is tried first | `REVIEWPULSE_SHEET_TABLES=off` | on |
| Sheet tables, ledger producer | `ledger/sheet_tables.py`: table cells bound to drawn elements by tag become candidates (family `sheet_table`, fact `fire_rating_min` only) | `REVIEWPULSE_SHEET_TABLES=off` | on |
| Regulation graph | `app/interpret` wraps `assemble_context` with `regs/context.with_resolved_context` | `REVIEWPULSE_REGGRAPH=off` | on |
| Drawing set summary | `app/interpret.coverage` adds `drawing_set` (views per sheet, callouts resolved, index mismatches) and the coverage page prints it | `REVIEWPULSE_DRAWINGSET=on` | off |
| Package data | `pyproject.toml` lists `drawingset/vocab.yaml`, `regs/cues.yaml`, `schedules/vocabulary.yaml`; a test checks they are present | none | n/a |

Existing files touched, each by a few lines: `pipeline.py`, `interpreter/findings.py`, `app/interpret.py`, `app/service.py`,
`annotate/schedules.py`, `factgraph/from_building.py` (`schedule_rows` reads `fire_rows`), `report/coverage.py`, `pyproject.toml`.
New modules: `ledger/wiring.py`, `ledger/sheet_tables.py`, `schedules/legacy.py`, `regs/context.py`, `drawingset/summary.py`.

## Decisions worth knowing

* **A dash is unknown, not zero.** A fire cell of "-", "--" or "TBD" now means no rating stated. Before, the old reader and the
  general reader both turned it into 0 minutes, so a door with a dash failed a "20 minute" rule. Now that door makes the rule
  undecided. "NR", "none" and "not rated" still mean 0, because they say so. This is a change of results on purpose, and the
  one place where the output differs from before.
* **Row counters see nothing new.** The consistency checks count schedule rows. Door ratings that only the general reader finds are
  stored in a separate schedule with an empty `rows` and a `fire_rows` map, so no "tag has no schedule row" finding appears or
  disappears because of this step.
* **Only the fire rating is offered to the ledger from tables.** A width from a schedule is not offered for `width_m`: the fact
  graph measures the drawn width, and the two differ by the frame, which would turn most door width checks into conflicts. Wider
  use needs a fact for the schedule width of its own.
* **Regulation graph context adds clauses, it loosens nothing.** The clauses added are real clauses of the same document with their
  own offsets. `ContextBundle.check_span` still accepts a quote only inside a clause of the bundle at the exact offsets, so a quote
  from the target or from the text it cites is accepted and any other text is refused (tested). Clause body reading, grounding,
  round trip and verifiers read the target clause and were not touched. At most 12 clauses are added.
* **A reviewer answer in the app** has a function (`app/interpret.attest`) but no screen or web route yet.

## What I measured

All from tests, no model call.

* `tests/unit/test_wiring.py`: 12 tests pass. Switch off gives the same `Inputs` as `to_inputs` and no resolutions; a planted
  schedule against table disagreement (20 minutes against "NR") gives a NOT_EVALUATED finding that names both sources and asks the
  question, the same rule without resolutions is worded as before; an agreeing table gives PASS with higher trust; an attestation
  outranks, is restored after reload, a nameless one is refused and a damaged file attests nothing; a dash is not a rating, "NR"
  is 0; merge keeps row counts; the sheet table switch off changes nothing; a quote outside the bundle is still refused; the
  three word lists are in the package data.
* `tests/unit/test_sheet_tables.py`: the dash test was changed from "zero minutes" to "no value", and the door fire special case
  test (general path equals the old reader on planted schedules) still passes.
* Full suite (`pytest -m 'not slow'`): 1166 passed, 4 skipped, 54 deselected (it was 1140 passed before; the 26 new passes are my
  12 tests and tests added by parts built at the same time). `tests/app/test_scenarios.py` is part of it and passes unchanged.
* Self check: 3 of 3 planted errors on DXF, PDF and the web app.
* Ruff on `src tests`: clean at the end of the run.

## Losses and limits

* **Dash doors change from fail to undecided.** Intended, but a plan whose schedule uses "-" for "not rated" will now show
  NOT_EVALUATED where it showed a failure. The reviewer question asks for the value.
* **Longer finding text** for undecided findings when the ledger holds the facts. A test that compared the exact message of such a
  finding would see the difference.
* **Unknown facts are not listed.** The ledger resolves the facts a door or room already has. A fact that is absent from the node
  (no producer wrote it) is still reported by the old "missing" text; the ledger does not add a line for it.
* **One table read per sheet and per clause**, cached by sheet. It costs time on plans with many words; I did not time it on a
  large set.
* **The regulation graph is built once per document text** (cache of four). A very large requirement document is slower to open.
* **The drawing set summary covers PDFs only** and appears in the coverage report, not in the review pack file; it is off by
  default because it reads every page.
* **No web route for attestations**, and `Resolution.fact()` still writes the reviewer into the source text.

## Still owed (needs a model or the GPU, not run)

* The local model checklist benchmark with the added regulation graph context: the prompt now holds more clauses for some targets,
  so the drafting rate has to be re-measured before this switch is claimed to help or to cost nothing. Switch it off to compare.
* The embedding header match of the table reader (`REVIEWPULSE_EMBED`), unchanged and still unmeasured.
* Timing of the table reader and the drawing set model on a real 40 sheet set.
