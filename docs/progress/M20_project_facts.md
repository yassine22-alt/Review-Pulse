# M20: project facts and applicability from the set itself (step 4 of the general plan)

Written 25 November 2026. Code: `src/reviewpulse/projectfacts/`. Tests: `tests/unit/test_projectfacts.py` (70 pass). Audit: `scripts/projectfacts_audit.py`.

## Why

Many requirements apply only in some cases ("townhouses require sprinklers", "stairs with four or more risers"). In M14 about 9 of 20
mention rules were conditional, and the checklists have the same shape. A decision needs the condition, and until now the condition
had to be typed by hand. A code analysis block, a cover sheet or a title block often states it. This step reads it, with a source, and
says "unknown" when the set does not state it.

## What I built

| Piece | File | What it does |
| --- | --- | --- |
| Field kinds as data | `fields.yaml` | Each field has a kind (number, bool, category), a unit, cue words per language (en, fr, de), words that may stand beside a cue in a label, and for categories the words a value uses (single family, townhouse, wood frame ...) and code patterns (R-3, Type V-B). Field names mirror ykram051's `metadata.yaml` where the idea is the same (`building_class`; her `occupancy` count is `occupant_load`). Fourteen fields: use, construction type, work type, storeys, sprinklered, fire alarm, occupant load, gross area (also by level), conditioned area, living area, building height, code edition, jurisdiction, and a project title line that is only scanned for a use and a kind of work. |
| Reader | `read.py`, `values.py` | Label and value pairs from the text layer: one line (`SPRINKLERS: NO`), one line without a colon (`Wohnfläche ca. 61,3 m²`), a value cell to the right of the label, a value below a header, and a column of values under an area header with a level name on each row. Numbers carry their unit and are converted (square feet to m², feet and inches to m); the locale of the label decides whether `1,092` is a thousand or a decimal. A value of `TBD` or a number with no unit anywhere is recorded as stated-but-unknown, never guessed. Rules drawn on the page are never looked at. |
| Candidates | `produce.py` | Output is `ledger.Candidate` (imported, not edited): kind `stated`, a source that names the sheet, view, layout and the label and value words, a region, family `textlayer`. A `ProjectFactsProducer` follows the `Producer` protocol (answers a request by meaning). Fields the set does not state are returned as a Candidate with `value=None` and score 0, listed in `ProjectFacts.unknown` with the reason, and `ProjectFacts.requests()` turns them into `FactRequest`s with reason `missing`, so step 8 can ask a person. |
| Derived conditions | `derive.py` | Only from data already there. Storeys from the levels the drawing set model put plan views on (kind `inferred`, score 0.4, roof plans not counted). "Stair with N or more risers" from the fact graph's trusted tread count, with three answers: true when the fewest possible risers reach N, false when even the most possible falls short, unknown in between or when no trusted flight exists. "Dwelling above another" is false only when the set states one storey or a single family dwelling, otherwise unknown. `Condition` and `evaluate` compare a project fact with a value and answer true, false or unknown. |
| Embedding arm | `embed.py` | A label the words do not know is compared with each field's document (description and cues) by bge-m3 through Ollama. Gated by `REVIEWPULSE_EMBED` (default off, so no GPU). The embedder is a parameter, tested with a stand-in. |
| Planted sheets | `planted.py` | Generated cover and code analysis sheets in en, fr, de with a known truth. |

Nothing is guessed from the look of the drawing. A category value that is not in the vocabulary is kept as the stated words with a
score of at most 0.5 and flagged as not canonical.

## What I measured

### Real sets (`data/real_plans`, 10 openable files, words only)

I read every field found. The text layers hold very little. `duluth_residential_samples.pdf` is an empty file (cannot be opened), so it
is not counted.

| Set | Found with a source | Read by me |
| --- | --- | --- |
| rebuildflorida (code data block on 4 plan sheets) | code edition (2023 Florida Building Code, Residential), work type (new construction), sprinklers no, fire alarm no, building height (3 houses), conditioned area (3), gross area (3), use | all right as stated except two: the use came from the value of a label `CONSTRUCTION TYPE` (the set writes `SINGLE FAMILY RESIDENTIAL` there), so I read it as a use and left the construction type unknown (partial, score 0.55); and a second code edition `8TH EDITION (2023).` from a general note (partial) |
| _chief_1_8 and chief_architect_austin (same set, 8 and 22 sheets) | living area 4,586 SF as `LIVABLE SF` (right, 426 m²); living area 2,662 SQ FT from a plan label `LIVING AREA` (wrong: it is one level's living area, read as the building's) | 1 right, 1 wrong in each |
| _chief_p5 (one sheet of the same set) | the same `LIVING AREA` | 1 wrong |
| de_baugesuch_cleebronn | use (single family dwelling) and work type (change of use) from the `BAUVORHABEN` title block line | 2 right |
| de_beispielgrundrisse_3raum | living area 61.3, 61.1 and 58.4 m², one per sheet | 3 right (three different flats, so the set holds three values for one field, which the ledger will see as a conflict) |
| austin_interior_remodel, ch_zeichenhilfe_baugesuch, millcreek_existing_proposed, nola_sketch | nothing | correct: these are guides and examples of what a drawing should show, none states a project fact. Every one of the 13 asked fields stays unknown with the reason "no label for it in N sheets" (4 sets x 13 = 52 fields, none filled). |

Total with a source: 25 values (counting the same set twice where `chief_architect_austin` repeats `_chief_1_8`): 20 right, 2 partial, 3 wrong
(the three `LIVING AREA` readings). The wrong ones are not hidden: they have score 0.72, below the 0.85 of a label with a colon or a
cell, and the ledger will see the conflict with the 4,586 SF figure. I did not fix this because the only fix I found is a patch
for one title ("a label that is also a plan view title"), not a general method.

Levels derived from the drawing set model (`--derive`, sets under 5 MB): `_chief_1_8` 2 storeys (right: 1st and 2nd floor plans),
`de_baugesuch_cleebronn` 2 above ground (ground floor and attic plans, basement counted apart; plausible, I did not check against the
building), `_chief_p5` 1 (only one sheet of a two storey set: a lower bound), the Swiss guide 1 (it is a guide, not a project).

Two mistakes the audit found and I removed before this count: a `FRONT/REAR HEIGHT` label with two values (dropped from the cue list;
that figure is now unknown) and sentence fragments such as `AUTHORITY HAVING JURISDICTION.` followed by the next note (a label that
ends with a full stop is a sentence, not a label). The first run had about a dozen junk jurisdiction and construction type values on the Florida set; the
second has none. A value that looks like another label ("NEW CONSTRUCTION") is accepted as the value when it reads as one for the
current field, which fixed `TYPE OF WORK` taking the code of the next column.

### Planted sheets (480 pages: 3 languages x 3 layouts x ruled or not x unit in cell or header, plus imperial English)

| Arm | Recall | Precision | Level areas | Metamorphic |
| --- | --- | --- | --- | --- |
| words | 1.000 (3840 of 3840 values) | 1.000 | 1440 of 1440 | 180 cases, 0 failed (changing the storeys or the sprinkler value changed exactly that fact) |
| words plus embedding | not run | not run | not run | not run (no ollama or GPU allowed here) |

This number is by construction: the planted labels come from the cue lists, so words reach all of them. It shows the layouts, the
locales, the units and the unit conversions work, that rules on the page change nothing, and that nothing else changes when one value
does. It does not show the reader copes with labels it has not seen. For that I wrote 12 held-out labels that are not in the cue
lists (for example `Levels above grade`, `Fire suppression system`, `Anzahl der Stockwerke`, `Niveaux hors sol`): words read
0 of 12. This is the gap the embedding arm is for; I have not measured whether it closes it. A stand-in embedder test only proves the
wiring. Sentences that carry the cue words ("INSTALL SPRINKLER HEADS PER MANUFACTURER") produced 0 values on 10 sheets of notes.

### Conditional checklist lines (qualitative reading)

I read the 46 `needs_fact` lines (reports in `data/real_docs`, labels in `benchmarks/checklist_labels.json`) and the lines of the four
checklists with a condition word. The script `projectfacts_audit.py checklist` only lists lines by keyword (it found 12 with a condition
word and a project field word and is not a measurement); the counts below are my reading.

Of the 46, 11 are conditional on the building:

| Condition | Lines | Can a condition now be known? |
| --- | --- | --- |
| use (townhouse, two family) | Allentown items 2, 3, 23 | yes where stated: known false (single family dwelling) on Cleebronn and, partly, Florida; unknown on the other 8 readable sets, so a question is asked instead of a refusal |
| level (basement, 2nd floor or above, each story, lower floor) | Allentown 13, 22, 24, St Pete 52 | the levels of the plan views are available (2 of the 10 sets have labelled levels); I did not wire "a basement exists" as a condition yet |
| risers (6 or more, 4 or more) | Allentown 8, 20 | computable from a trusted stair flight; the benchmark plan has none and I did not run the stair finder on the real sets, so 0 of 2 measured |
| "if required by ...", "if applicable" | Allentown 25, St Pete 62 | no: not a project fact, stays unknown |

Three `not_plan` lines (Bloomfield grading, St Pete minor alterations, Berkeley existing and proposed work) depend on the work type, which is
now read on 2 sets. So 7 of 11 conditional lines have a condition that is now computable, and it is known on 2 of the 10 readable real sets
at best. The others carry an explicit unknown. I claim no change to the checklist benchmark: the conditions are not yet wired into the
rule interpreter, so no line outcome has changed.

## Losses and limits

* Real sets rarely state project facts in the text layer. 2 of 10 sets gave a use, 1 gave sprinklers, none gave storeys, occupancy or
  jurisdiction. Most answers will be unknown and become questions.
* `LIVING AREA` read from a plan view label gives a wrong building value (3 cases above).
* A set that writes the sprinkler system as a standard (`NFPA 13R`) instead of yes or no is rejected, not read as yes.
* Free text without a colon, a cell or a header (`Gemeinde Cleebronn`) is not read for jurisdiction or project title, to avoid
  sentences. The field is unknown then.
* Level names in an area table are read with the level words of the drawing set vocabulary; `MAIN:` and `SECOND:` rows under `LIVABLE SF` in the Chief set are not
  (unknown).
* Scans need OCR first; with no text layer the reason says so.
* The embedding arm was not run. Words only are measured.
* The planted result is by construction and optimistic; the held-out figure (0 of 12) is the honest one for unseen labels.

## How to run

```
set PYTHONPATH=src PYTHONIOENCODING=utf-8 REVIEWPULSE_LABEL_LLM=0
.venv\Scripts\python.exe scripts\projectfacts_audit.py real --derive
.venv\Scripts\python.exe scripts\projectfacts_audit.py planted --n 10
.venv\Scripts\python.exe scripts\projectfacts_audit.py checklist
```

The Florida set takes about a minute (19 787 text lines). The embedding arm turns on with `REVIEWPULSE_EMBED=on` when bge-m3 is served.

## Next

Wire `Condition` into the normative form of step 5 so that a conditional line reads its condition from here, add "a level exists" as a
derived condition, and run the embedding arm when the GPU is free to see whether the 0 of 12 moves.
