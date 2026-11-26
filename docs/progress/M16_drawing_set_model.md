# M16: a model of the drawing set (step 1 of the general plan)

This note is for someone new to the project. It says what I built, how I measured it without labels, and where it fails.
Everything below was run on the real sets in `data/real_plans` (not committed). Numbers come from
`python scripts/drawingset_audit.py <pdfs>`; the full output of the last run is reproducible with the command at the end.

## Why

Until now ReviewPulse read each sheet as one plan with one scale. A real sheet holds several views (a plan, two details, a
schedule) at different scales, and sheets point at each other ("3/A-501", "SEE DETAIL 4"). Without a model of that, a fact read
on one view can be given the scale of another, and a reference to another sheet cannot be followed. This step builds the model
and nothing else. It does not change any existing check.

## What was built

All new code is in `src/reviewpulse/drawingset/`. No existing file was edited.

* **Pages** (`pagedata.py`): a page is text lines with boxes plus the boxes of the vector paths. A page turned by any quarter
  turn is put upright again from the direction of most of its text. OCR words can be merged in (`from_ocr_words`, `merge_ocr`).
* **Vocabularies** (`vocab.yaml`, `vocab.py`): the words for views, levels, scales, title block labels and the callout grammars
  for English, French, German and Spanish are a data file. Adding a language or a trade means adding words there.
* **Views** (`views.py`): find the title block from its labels; find view titles (a kind word plus a scale line, or a number
  bubble, or large type; a large title with both a bubble and a scale needs no kind word); cut the sheet by an X-Y cut on
  whitespace, and where no band separates the titles, by connected pieces of the drawing given to the title they touch. Each
  view gets a box in page points (its own frame), a kind, labels, a scale (with the metres per point) and, for plans, a level.
* **Scale** (`scale.py`): `1/4" = 1'-0"`, `1" = 20'`, `1:100`, `M 1:50`, `NTS`; a fraction like `1/100` only after a scale word.
* **Callouts** (`refs.py`): grammars from the YAML plus stacked "bubbles" (view number over sheet number, either way up). A
  callout is resolved to a view, or to a sheet. Where the set repeats a sheet number (the Florida file holds several designs)
  the nearest sheet that holds the view is taken.
* **Sheet index** (`setparts.py`): the index (with or without a heading) is read by rows and compared with the title blocks.
* **Legends**: each row of a legend view is kept as words plus the region of the drawn symbol beside it, for step 6.
* **Levels**: plan views get a level from title words or ordinals ("2nd floor", "Grundriss EG", "1. Obergeschoss").

Entry point: `build_from_pdf(path)` or `build_drawing_set(pages)`; both return a `DrawingSet` that saves as JSON.
To hook it into the pipeline later: call `build_from_pdf(path, ocr_pages={page: [Line, ...]})` with the OCR lines the pipeline
already has; nothing else is needed. `pyproject.toml` must list `drawingset/vocab.yaml` as package data before this is installed
as a wheel (I did not edit it).

## How it was measured (no labels)

1. **Callouts that resolve** to a view or sheet that exists in the set. Every case that does not is listed and read.
2. **Chance level**: the same measure after shuffling the view labels between callouts. A resolve rate near this is weak evidence.
3. **Kind agreement**: where a callout says "detail", is the target view a detail?
4. **Sheet index against title blocks.**
5. **Cutting methods against two simpler ones**: nearest title (`voronoi`) and one view per sheet (`sheet`), on the share of view
   area covered by other views, and on views holding a scale line that is not their own.
6. **Metamorphic**: turn every page; turn a real PDF; rename a sheet number where the set names it; move a view 8% of the page width.

## Results

| Set | Sheets (number read) | Views | Plan, section, elevation, detail, site views: scale from title / region / sheet default / none |
| --- | --- | --- | --- |
| Chief Architect Austin (22 pages) | 22 (22) | 139 | 53 / 3 / 10 / 23 (of 89) |
| Rebuild Florida (57 pages, several designs) | 57 (50) | 392 | 98 / 5 / 39 / 16 (of 158) |
| de_baugesuch_cleebronn (9) | 9 (8) | 9 | 0 / 0 / 7 (the 1:100 in the title block) / 0 |
| de_beispielgrundrisse_3raum (3) | 3 (0) | 3 | 3 own / 0 / 0 / 0 |
| millcreek_existing_proposed (1) | 1 (0) | 2 | all 2 have none: the sheet prints no scale |
| ch_zeichenhilfe_baugesuch (20, a drawing guide) | 20 (1) | 41 | 6 / 2 / 3 / 17 (of 28), plus 1 on its own title line |
| austin_interior_remodel (4, text pages) | 4 (0) | 4 unknown | none: no drawing structure |

Four of the 22 Chief sheets and 14 of the 57 Florida sheets hold views at more than one scale, which the old reader gave one
scale. "Sheet default" means the scale of the title block was given to the view; it is marked as such and may be wrong when the
sheet mixes scales.

### Callouts

| Set | In scope | Resolved | Unique resolved | Chance (shuffled labels) | Sheet found | Kind agreement (real / chance) |
| --- | --- | --- | --- | --- | --- | --- |
| Chief Austin | 42 | 28 (66.7%) | 13 of 19 | 34.2% (max 45.2%) | 100% | none say a kind |
| Rebuild Florida | 124 | 112 (90.3%) | 79 of 91 | 82.7% (max 86.7%) | 98.3% | 40 of 47 / 68.6% |

"In scope" leaves out callouts drawn inside a legend or index (examples, not references) and tokens that are not shaped like
this set's sheet numbers (23 on Florida, mostly `2/MTS20`, a strap product, 16 times). Other sets have no callouts the
grammars find (one drawing guide has a "Schnitt B-B 17.3" that is a room number, rejected by shape).

**Read plainly:** on Chief the gain over chance is real (67% against 34%). On Florida it is small (90% against 83%), because
every sheet has views numbered 1 to 7, so almost any label finds a view. The sheet level baseline (the sheet exists) is 98%, so
what the view level adds on Florida is the 8 points that fail it and the kind check (40 of 47 against 69% by chance). I would
not call the Florida figure a proof of correctness; it says the references are consistent with the views found.

**Every unresolved case was read.** Chief, 14 callouts (6 distinct), all stacked bubbles:
`S1`, `S3`, `S5` over sheet 12 (3 distinct on sheet 4, 1 on sheet 5), `D12` over sheet 15 and `D6` over sheet 14. The target
sheet exists in each case and the labelled view was not found among the views read on it. These details are drawn without a
title my reader recognises, so the miss is in view finding, not in the grammar.
Florida, 12: ten are bubbles `N9`, `N10`, `N15`, `8` with `A3.01`, the keynote and window tags next to the sheet marker; the
target sheet is found, and no view with that label exists on it, so these are probably not references to a view at all (not
verified by hand against the drawing). Two bubbles name sheets `N2` and `N9` that do not exist (a tag pair read as a sheet),
and `F3S / S4` is a symbol made of stacked letters in a mechanical schematic. Those last three are false callouts that the shape
test could not exclude.

### Sheet index against title blocks

* Chief: the index (it has no heading in the text layer) gives 22 entries: 21 match their title block, 1 differs (sheet 1: the
  title block title was not read, the big line there is the project name). No sheet is missing from the index.
* Florida: 64 entries from four index views (the file holds several designs): 28 match, 20 differ, 16 name sheets not in the
  file. The differences read are almost all a title block title that carries the project name after the real title ("STRUCTURAL
  PLAN VIEWS REBUILD FLORIDA - HURRICANE HOUSING ..."), so the sheet title reading is too greedy there.

### Cutting methods

| Set | Method | Overlap of views | Views with a foreign scale line | Views with a scale |
| --- | --- | --- | --- | --- |
| Chief | X-Y cut then pieces | 0.286 | 2 of 78 | 78 |
| Chief | nearest title | 0.308 | 2 of 78 | 78 |
| Chief | one view per sheet | 0 (trivially) | 0 of 15 | 15 |
| Florida | X-Y cut then pieces | 0.309 | 3 of 143 | 143 |
| Florida | nearest title | 0.310 | 3 of 143 | 143 |
| Florida | one view per sheet | 0 (trivially) | 1 of 36 | 36 |

The X-Y cut is hardly better than nearest title on these sets. The reason is measured: on the Chief and Florida sheets with two
or more titles, a whitespace band that separates titles existed on only about 7 of 65, because real sheets are dense and views
overlap in both directions. The work is done by the second stage (connected pieces of the drawing given to the title they touch),
which on the Chief elevation sheet separated two overlapping elevations that nearest title could not. The X-Y cut matters on
sparse sheets (the generated test sheets, the German set). One view per sheet has no overlap by construction but gives each
view no scale of its own: it finds 15 and 36 scaled views where the cut finds 78 and 143. Overlap of 0.29 to 0.31 is high: boxes
of views that interleave overlap even when the contents are separate; text is given to the smallest box that holds it.

### Metamorphic checks

| Change | Chief | Florida |
| --- | --- | --- |
| Turn every page 90, 180, 270 | callouts and views identical (42, 139) | identical (147, 392) |
| Real PDF with /Rotate 90, first pages | identical | identical |
| Rename a sheet number where the set names it | 95.2% of callouts the same; 9 new callouts appear (42 to 51) | 96.6% the same, none new |
| Move a view 8% of the page width | callouts identical, 96.4% of views the same | 96.6% of callouts the same, 2 lost (147 to 145), 98.2% of views |

The rename on Chief is a weakness, not a pass: once the renamed number looks like a sheet number, 9 stacked tags that were not
accepted before are accepted. The two lost callouts when a view moves are collisions: the moved view landed on a neighbour.
(An earlier run printed "1 callout" for sets with none; that was a bug in the report, since fixed.)

### Legends, levels

Chief: 96 legend rows, 92 with a symbol region. Florida: 2492 rows, 1150 with a symbol, but the legend view boxes there include
text that is not a legend row, so I do not trust that count. Levels: Chief plan views get levels 1, 2 and roof; the Swiss
Cleebronn set gets basement, ground and attic. The ordinal "first floor" is rank 1, so a US "first floor" (ground) and a
European one are not unified; a set that has a "ground" and a "first" will keep them apart.

## What is not done, and losses

* **Vision model alternative not run.** The plan asked to test a Qwen3-VL class model against the structural parser. I was told
  not to use the GPU, so it was not tried. Nothing here is a claim about it.
* **Scans.** Text layer only. OCR lines can be merged in (tested on synthetic OCR words, not on a scanned set); layout detection
  on scans was not measured.
* **AEC-Bench intra drawing tasks** were not run.
* **Levels from stairs** that appear on two plans: not built. Levels come from title words only.
* The title bar of a view with no kind word needs both a bubble and a scale; titles without them are missed (the 14 Chief
  misses). Lettered views stacked over a lettered sheet number that is not a sheet of the set are missed by design.
* Sheet title reading takes the largest type of the title block and so adds the project name on some sheets.
* Callouts to details are not checked against the drawn arrow or detail mark; the drawn symbol is not located.
* Florida legend boxes are too loose; the legend row count there is an upper bound.

Decision: I keep the structural parser as the default. The only comparison done is against simpler structural baselines, and
the model gives each view its own scale where the baseline cannot.

## Tests and how to rerun

```text
PYTHONPATH=src python -m pytest tests/unit/test_drawingset.py     54 tests: scales, four language vocabularies, grammars, views,
                                                                  resolution, index, legend, levels, rotation, rename, move,
                                                                  a real generated PDF at four rotations, OCR merge
ruff check src tests
PYTHONPATH=src python scripts/drawingset_audit.py data/real_plans/chief_architect_austin.pdf \
    data/real_plans/rebuildflorida_floorplans.pdf --json reports/drawingset_audit.json
```

The audit takes about three minutes for the two big sets.
