# NOTES: experiment log

One entry per measured result: date, step, command, commit, metrics. A number counts only if it
came from `rp eval` (or `rp rules test`) and is written here. Commit: `uncommitted` until the team
commits this folder.

## 2026-10-24: first implementation sprint

### Environment
Python 3.11.0, PyMuPDF 2.0, ezdxf 1.4.5, Shapely 2.2.0, Windows 11. Fast suite: 151 tests, ruff clean.

### R7 scale: `rp eval scale --n 30`
30 synthetic PDFs at 1:50 / 1:100 / 1:200: mean relative error 0.0000, max 0.0000, 100% < 0.5%.
Target (< 0.5%) met.

### R8–R10 generality: `rp eval random --n 60`, `rp eval random_pdf --n 60`
Randomised plans (rotation, units, scale, layer schemes, wall and door styles), synthetic only.

| metric | DXF | PDF |
|---|---|---|
| walls F1 (length-weighted) | 0.9997 | 0.9996 |
| doors P / R | 0.998 / 1.000 | 0.998 / 1.000 |
| windows P / R | 1.000 / 0.997 | 1.000 / 1.000 |
| rooms P / R (IoU 0.5) | 1.000 / 1.000 | 1.000 / 1.000 |
| door-edge F1 | 1.000 | 1.000 |

Fixes that took this from walls 0.69 / doors 0.74 / edges 0.60 (first run) to the table above, all
general: arc fitting from line chains; OCS handling of mirrored DXF blocks; pier and pilaster
survival in the spur rule; same-material rule for pairing; short-overlap pairing for continuous
outlines; dimension graphics, glazing and door leaves kept out of wall pairing; two-point door
matching; filled PDF paths as polygons. One generator bug found and fixed (PDF text rotated the
wrong way).

### End-to-end findings: `rp eval findings --n 72`, `rp eval findings_pdf --n 72`
72 plans per format, every one of the 18 error switches planted twice (46 expected findings):
DXF recall 46/46 real and 46/46 oracle, 0 perception disagreements; PDF identical. All 18 rule ids
with a planted error covered.

**Evaluation bug found and fixed:** the error cycle `keys[i % len(keys)]` on odd `i` with 18 error
switches only ever planted the odd-indexed switches (9 of 18). The earlier "recall 1.00 on 60 plans"
rows covered only those 9 and were removed from `reports/results.csv`. Fixed to
`keys[(i // 2) % len(keys)]`.

### Rule pack: `rp rules test`
22 approved rules: 19 OK (silent on the clean plan, fire on their planted error), 3 untested
(C-D3W, C-D3L, C-T5: no planted error targets them).

### Engine bug found by the I5 self-test
With both a drawn and a scheduled door width, C-D1 used the smaller value whatever the operator.
That is conservative for a minimum but not for a maximum. It now takes the larger value for
`<=` / `<`.

## 2026-10-24 (evening): clutter round and local LLM

### Generality with clutter: `rp eval random --n 60`, `rp eval random_pdf --n 60`
Clutter (furniture, fixtures, counters, exploded hatch, frame, grid axes) in ~70% of plans.
First run: walls P 0.966 (DXF) / 0.977 (PDF), rooms R 0.981 / 0.994, edges F1 0.971 / 0.989.
After rules A9-A11: walls F1 0.9986 / 0.9985, rooms 474/474 both, edges 551/551 both, windows
0.998 / 1.000, every style combination at room/edge F1 1.00.
Two attempts made things worse before being corrected: the isolated-cluster rule first deleted piers
between openings (wall recall 0.82); the first pattern tagger mixed lines of different walls (a rotated
hatched PDF lost 4 of 5 rooms) and then tagged wall faces + axis dashes + a sofa edge as a "pattern".

### End to end: `rp eval findings --n 72`, `rp eval findings_pdf --n 72`
After the clutter rules: still 46/46 real and oracle on both formats, 0 perception disagreements.

### I4 drafting, local Qwen2.5-7B via Ollama: `rp eval drafting`
30 hand-made gold clauses (5 not checkable). Dev = odd ids, held-out test = even ids.
- Full-rule design: label 0.633, fn recall 0.48, scope recall 0.077, 14.4 s/clause.
- Frame design (A12): label 0.933 (test 0.933), fn 0.76 (test 0.75), op/value 0.93 (test 0.86),
  scope 0.92 (test 1.00), exact rules 19/30 (test 9/15), 7.9 s/clause. Tuning stopped here.

### Tests
185 passed (including the slow 30-plan sweep), ruff clean.

## 2026-10-25: rooms at scale, 25-rule pack, snapshots (M3b)

Report: [docs/progress/M3b_rooms_rules.md](docs/progress/M3b_rooms_rules.md).

### R10 on ResPlan: `rp eval rooms --dataset resplan --n 1632`
Barrier = true walls/doors/windows (R10 tested alone). Spaces F1 0.9929 -> 0.9944 (9,718/9,783),
door edges F1 0.9906 -> 0.9936 (10,971/11,046) after door-prior scale (A20) and envelope-leak sealing
(A21). Doors labelled EXIT 3,882 vs 1,629 true front doors: unlabelled balcony doors (known limit).

### Rule pack
25 approved rules (the M1/M2 count of 22 was wrong: it was 21). New C-D5, C-V2, P-5, P-6; planted
errors now cover C-D3W, C-D3L, C-T5. `rp rules test`: 25/25 ok. Generator windows capped at 2.9 m
because R9 misses openings wider than 3.0 m.

### Snapshots and reports
`tests/golden/test_snapshots.py` (10 plans, `--snapshot-update`), `tests/golden/test_reports.py`
(triage audit log, rotated page markers, multi-sheet PDF).

### End to end: `rp eval findings --n 100`, `rp eval findings_pdf --n 100`
72 planted errors over all 25 rules: 72/72 real and oracle on both formats, 0 perception
disagreements (after fixing `metric_living_small`, which planted a 14.1 m2 "small" living room on
deep layouts). Tests: 175 passed (`-m "not slow"`), ruff clean.

## 2026-10-25: raster path: scans and photos (M3, R13)

Report: [docs/progress/M3_raster_path.md](docs/progress/M3_raster_path.md).

### Model: `scripts/train_raster_seg.py --epochs 34`
U-Net / ResNet34 (ImageNet), classes background/wall/door/window, CubiCasa5K train (4,200 scans,
longest side 1,024 px), 512 crops, AMP, seed 7, RTX A1000 6 GB: 98 min. Best val (400 scans)
IoU wall 0.822, door 0.717, window 0.815, mean 0.785. First attempt lost: the laptop slept (one
epoch in 714 wall-clock minutes); second: `torch.save` over a best.pt that a test had memory-mapped
(Windows error 1224) -> checkpoints now atomic in `train/`, `--resume`, model test marked slow.

### CubiCasa5K test, 100 scans: `rp eval raster --n 100 --method all`
| | walls F1 (3 px) | walls IoU | doors F1@0.5 | windows F1@0.5 | rooms F1@0.5 |
|---|---|---|---|---|---|
| rules | 0.694 | 0.406 | – | – | 0.337 |
| model | **0.954** | **0.798** | **0.837** | **0.796** | **0.873** |
| fusion | 0.841 | 0.639 | 0.837 | 0.796 | 0.819 |
| oracle barrier | | | | | 0.974 |
Fusion lost on precision -> default is model only (A18). Rules fail on hollow (outline-only) walls,
common in CubiCasa; no reliable rule for their gap width was found (background-gap histograms have
no peak), so none was added.

### OCR spike S-D: `scripts/spike_ocr.py`
FP-TXT boxes mapped to CubiCasa by re-implementing its replication rule (945/1000 images, sizes
checked). CVC-FP is no longer downloadable. Recognition, 25 hand-transcribed crops: PaddleOCR CER
0.120 (18 exact), EasyOCR 0.612 (9). Detection, 30 test pages, IoU 0.3: Paddle P 0.83 R 0.78,
EasyOCR P 0.88 R 0.20. Paddle chosen (A15); cost ~2 min/page on CPU with 4 rotations.

### Rule baseline fix
Exterior walls twice the partitions made the dominant-width opening erase every partition
(synthetic filled-wall plan: 1 room of 5). The opening now uses the thinnest wall class (A16): 5/5.

### Pipeline scale handling: `rp eval raster --n 100 --method model_scan`
First end-to-end runs fed the model at x2.15 on plan 1191 (ink thickness 6.5 px = wall outlines;
real walls 18 px): 776-3,360 wall fragments, rooms 9x too large. An upscaled pass makes the model
mark only outlines, which then "confirms" the wrong size, so the thickness is now measured on the
model's wall mask from two downscaled probes (A14). On full-resolution test scans through this
entry: walls F1 0.952, doors 0.850, windows 0.814, rooms 0.900 (vs 0.873 on pre-scaled renders).

### End to end on a French synthetic scan
OCR 15/15 texts; R7 failed until (a) OCR dedupe preferred upright reads (horizontal dimensions had
been stored as 90 deg) and (b) LSD primitives stopped claiming a stroke width (all were dropped by
the 0.3 mm PDF filter). Then 1:50 recovered (truth 1:50, confidence 0.75 -> T3), 5/5 doors,
4/4 windows, 5/5 rooms within 2% of true area.

### Open (other streams)
P-1 / P-5 presence rules FAIL at T3 on OCR'd scans (Finnish labels outside the room vocabulary,
no opening tags on CubiCasa plans); the text classifier has French/English room words only.

## M4: real-world robustness (stream C, 25-26 Oct 2026)

### Room labels in any language: `scripts/mine_room_labels.py`, `scripts/eval_room_labels.py`
CubiCasa5K model.svg keeps the printed label of each space (`TextLabel NameLabel`) next to its class:
51,585 / 4,788 / 5,011 labelled spaces in train / val / test. FloorPlanCAD has no text (0/50 sampled)
and ResPlan none, so CubiCasa is the only real label source. Mining bug on the way: nested
`SpaceDimensionsLabel` groups matched the `Space` prefix and doubled every pair (fixed).
Label -> type on the 5,011 test spaces (lexicon built from train+val only):
FR/EN keywords 6.5% correct; curated multilingual lexicon 85.6% (optimistic: its Finnish entries were
written after seeing plan 1191, a test plan); curated + mined 99.95%; the LLM alone 59.3% correct
(precision 0.68: OH -> other, KH -> kitchen, PARVEKE -> storage), so it is a fallback only (A27).

### Labels through OCR: `scripts/eval_ocr_labels.py` (20 test scans, cached PaddleOCR words)
| | labels correct | stated areas read | bare numbers read as dimensions |
|---|---|---|---|
| before (FR/EN, no stacking) | 0.6% | 8.8% | 27 |
| lexicon + stacking (A25, A28) | 47.0% | 16.6% | 14 |
| + fuzzy OCR matching (A26) | 50.8% | 16.6% | 14 |
| + LLM fallback (A27) | 53.0% | 17.1% | 14 |
Of the remaining misses, 41/181 spaces have no OCR text inside at all and 50 have text that is
misread beyond safe matching (two-letter "UH" for MH). The "duplicated vertical labels" of M3 were
two lines of one label (name over area): the real defect was the area line read as a dimension.

### Opening rectangles: `scripts/eval_opening_rects.py` (100 CubiCasa test plans, model masks)
Oversized window rectangles 42 -> 32, doors 11 -> 8; rectangle F1 windows 0.791 -> 0.806, doors
0.849 -> 0.852; mask scores and room F1 (0.873) unchanged (A30).

### SVG text (A31)
Exported SVG (PyMuPDF) put positions on tspans: every label sat at one point, R7 found 7 candidates
and 0 inliers, the SVG of a T1 PDF fell to T3. Per-run placement through the transform: 8/8 inliers, T1.

### Acceptance suite (A32): `python scripts/acceptance.py`
All 7 vector cases pass (DXF, random-style DXF, vector PDF, SVG, 2-page PDF, no dimensions, no
labels): planted errors found, no unsafe FAIL. Scans: PNG, scanned PDF, skewed+noisy, rotated 90 pass
(no crash, T2/T3, no unsafe FAIL); planted exit error found on 3/4; the low-dpi scan crashed the CLI
printing an OCR'd "口" to a cp1252 pipe (fixed: output never crashes on encoding).
Time per scan page 380-900 s with another training job on the machine: OCR is 97% (profile: 1,262 of
1,297 s; 2 tiles x 4 rotations, recognition 900 s).

### "Not to scale" (A33)
colorful/10052 reads only 2 OCR words on CPU and GPU: correct. The plan prints no room labels (its
spaces are colour fills, ground truth mostly UNDEFINED); the only text is the footer
"SUUNTAA-ANTAVA, EI MITTAKAAVASSA" (indicative, not to scale) and the CUBICASA logo. The footer is now
read: a not-to-scale sheet never measures above T3.

### OCR configuration on GPU and CPU (A34): 8 CubiCasa test scans
GPU (paddlepaddle-gpu, RTX A1000): 4 rotations medium 10.2 s/page, labels 39.8%; 2 rotations 6.5 s,
31.3%; small recognition 16.4 s, 36.1%. CPU: 229 s / 95 s / 421 s (beside training jobs: upper bounds);
the CPU Paddle build segfaulted twice under load. Default kept: 4 rotations, medium, GPU when present.

### Wrong scan scale at T2 found by the acceptance suite (A35, A36)
PNG scan: dimension texts paired with wall/door edges 10 mm away (true dimension ticks lost in the scan,
the edges' perpendicular jamb lines passed as ticks): 3 half-length pairs agreed on 1:186 at confidence
1.0, rooms 3.4x too large, doors 1.63 m. Nearest-line pairing removes the false pairs; the door check
(median door 0.6-1.3 m) catches any scale that slips through. A text-box line-join was tried first and
removed: it was not the cause. Acceptance now requires T1/T2 sheets to measure rooms within 10% of truth.
Final: 12/12 cases, 230 fast tests pass.

## M4: product app (stream B, 25-26 Oct 2026), [report](docs/progress/M4_product_app.md)

### `rp serve`: FastAPI service + single-page UI (`src/reviewpulse/app/`)
Projects on disk; background jobs (thread pool, one per project, records in `jobs/`, interrupted
jobs marked failed at start-up); analyse / draft / review / check / triage reuse pipeline.py,
rules/ and report/. Viewer data (`view.json`) is in image pixels via the report's own
sheet-to-pixel function, so vector and raster sheets render alike.

### Demo: `python scripts/demo.py` (HTTP API, local qwen2.5:7b)
Generated DXF with 5 planted errors + docs/requirements_example.md: analysis 5-17 s; 24 clauses,
20 drafted in 221-285 s; 16 unflagged drafts approved (self-tests pass); check with 41 rules in
1-2 s: 15 FAIL, 123 PASS; planted errors found 5/5. A first demo set planted
`comp_unlabelled_room` and `topo_exit_via_bath` on the same bedroom: the unlabelled room has no
type, so C-T1 skipped it (4/5). Not a detection miss; the set now uses separate rooms.

### Self-test fix (rules/review.py)
The metric self-test probed at ±5 % of the limit = the policy's area tolerance band, so the
"too small" probe gave WARNING and no area rule could ever be approved. The probe now sits at 2x
the policy tolerance. The old "wrong rule is refused" unit test passed only through that bug (room
area applied to windows); that case is now refused explicitly. Threshold rules without op/value
are refused with a reason instead of crashing in the engine.

### Windows file replace
`Path.replace` fails while another thread reads the target (job status polling). Both stores
retry briefly; live job records are served from memory.

### Open
Docker files not built here (no engine on this machine). No authentication yet. Untyped rooms
skip type-scoped rules instead of NOT_EVALUATED (engine-policy question).

## M5: learned pass for real CAD drawings (26-27 Oct 2026), [report](docs/progress/M5_vector_learned.md)

### Head-to-head, rules vs fuse vs rebuild (reports/v4_*)
FloorPlanCAD test 100, F1 walls (length) / doors / windows: rules 0.283 / 0.657 / 0.203; fuse
0.518 / 0.901 / 0.687; rebuild 0.569 / 0.894 / 0.675. Generated plans, rooms DXF / PDF: rules and
fuse 474/474 both; rebuild 461/463 (one plan crashed) / 472/474, doors 0.88. Planted errors 24/24 in
all three. Fuse is the default (D8, A38).

### Label bug in generated training data (v2 -> v3)
Door swing discs were labelled before wall faces, so the faces beside every door were "door": the
classifier learned to reject short wall pieces between doors and fused rooms merged (rooms 0.83 /
0.88). Walls now win over swing discs; validation wall F1 on generated plans 0.992 -> 0.999.

### PDF lines of one path shared one Prov (A37)
v3 fuse lost 10 PDF rooms, all on polyline-wall plans: annotate_primitives wrote p_wall 1.0 on each
line, but every line of the path held the same evidence dict, so the last line's 0.0001 won.
Diagnosed by predicting the exact feature rows directly (1.0) against the stored evidence (0.0001).
Fixed in pdf_backend.add(); synthetic cache rebuilt; v4 retrained (val wall F1 0.8375 / 0.9992).

### Room outlines rounded per vertex could self-intersect
Plan 5043 (rebuild mode) stored a self-intersecting room after rounding to 1e-4. Now snapped with
shapely.set_precision (largest polygon kept). Contract test on that plan.

### Training on a laptop that switches off
Two restarts during training. Checkpoints every 100 rounds, resumed with init_model; early stopping
state carried in checkpoint.json. The first checkpoint after a power cut was all zeros (rename
reached the disk before the data): checkpoints and cache chunks are now fsynced before replace.
Uncontended, 4,000 rounds on 8.9 M rows took 28 min (2 h beside other jobs).

## Evidence round: rooms on real CAD, escape routes, the brief, drafting on real regulations (27 Oct 2026)

### Rooms on real CAD - `scripts/eval_rooms_real_cad.py` (reports/rooms_real_cad*/)
No public CAD set labels rooms. Reference: rooms our pipeline builds from the dataset's true
wall/door/window lines (build_model annotator hook, rebuild mode). Measures how line errors damage rooms.

| | rules | default (v4) | default (v5, + ArchCAD) |
|---|---|---|---|
| FloorPlanCAD, 40 drawings, 81 ref rooms: room F1 | 0.454 | 0.696 | 0.663 |
| ArchCAD, 200 slices, 160 ref rooms: room F1 | 0.349 | 0.366 | 0.594 |
| ArchCAD precision (pred / tp) | 0.24 (413/100) | 0.27 (332/90) | 0.59 (160/95) |
| matched rooms with area within 5%: FPCAD / ArchCAD | 43% / 40% | 35% / 47% | 30% / 46% |

False rooms on ArchCAD came from structural beam grids and double-outlined furniture or parking
paired as wall faces; ArchCAD training labels them "other". Areas within 5% for under half of the
matched rooms: area rules on real CAD are not reliable yet.

### Travel distance from the farthest point (C-T5) and door swing (C-T6, draft)
Walked inside each room around its corners (core/geometry.Walkable), door to door. Independent check
on clean plan 21: grid search over the walkable floor (2 cm cells, 16-neighbour) agrees within 0.6 m
on all 5 rooms (rule 16.29 m, grid 15.93 m for the far bedroom). The generator's "clean" flats broke the
example 15 m limit in 40/40 seeds (worst 16.93 m), hidden by the old centroid measure. Entrance moved
into the hall and bounds trimmed: worst case at every bound's maximum 14.89 m, minimum 13.06 m, no
FAIL/WARNING on either; planted metric_travel_far still fails. Findings eval: 24/24, 0 disagreements.

### Brief (programme) - rules/programme.py, rule K-P1
CSV/XLSX/DOCX/PDF/MD, FR/EN headers, room names typed by the label lexicon. Tested on a generated plan
with briefs written from truth (all four formats read identically), planted missing room and small
room (2 FAIL), unlabelled room (NOT_EVALUATED, not FAIL). `rp check plan --brief brief.xlsx` end to end.
A brief written exactly at the drawn area sits in the tolerance band (WARNING): test briefs keep 0.25 m2.

### Drafting on real regulations - `scripts/eval_drafting_code_accord.py` (CODE-ACCORD, CC BY 4.0)
171 sentences (England, Finland) with exactly one annotated comparison; qwen2.5:7b, 36 min.
Direction right: lower bounds 72/92, upper 45/48, "equal" 0/31 (read as minimums or no number).
Number right 78/105 (digits). Unsafe (wrong direction, no flag): 13/171, 2/68 drawing-checkable.
Deterministic wording flags added (ranges, two limits, permissions "may be more than"): unsafe 11/171,
1/68; 9 correct drafts gain a flag. Remaining unsafe: "shall be / used as" values, mostly calculations.

### Vision model as a second reader for scanned labels (qwen2.5vl:7b) - not adopted
`scripts/eval_ocr_labels.py --n 20 --vlm` (20 CubiCasa test scans, 181 spaces): labels correct 50.8%
without and with it. Of 120 OCR words re-read: 18 same, 81 inventions ("10'x20' Office Space Available
for Lease", a list of six room names for "UH"), 21 accepted, 2 new correct labels; correct readings
corrupted (HUONE -> HOME). On a blank crop the model answers "10'x20' Living Room". Kept: the agreement
gate (a second reading must resemble the OCR reading: letters >= 0.6 similar, length within x0.5-x2),
generation cap (num_predict 24, repeat_penalty 1.15: unbounded answers aborted with "token repeat limit
reached"), failure-safe fallback, VLM-typed rooms never FAIL. Module off by default (annotate/label_vlm.py).

### Object outlines are never wall faces (walls.py _object_outlines)
Measured case: random plan 5033 PDF with the ArchCAD model: a bathtub outline became 3 walls, a 1 m2
false room, bathroom 10.12 -> 8.51 m2. Rule: small closed outline whose largest inscribed circle is wider
than T_MAX_M (0.6 m) is an object (bathtub, lift car, counter): its lines neither pair nor become learned
faces. First version used the minimum rotated rectangle: it called L/T-shaped wall bodies objects and
broke 4 generality tests; inscribed circle fixed it. Plan 5033 correct with both models. No change on
FloorPlanCAD room areas (35% within 5%, 52% too small): objects there are not single closed outlines.

## M6: measurement fixes and fusion fixes (28 Oct 2026), [report](docs/progress/M6_evidence_and_measurement.md)

### v6 first attempt (A45)
Training stopped: `cached()` held a stale feature chunk open (np.load without close) while its recompute
replaced it; Windows refuses (WinError 5, reproduced). The chain went on and the ArchCAD eval, pointed at
the missing model, wrote all zeros (true=0: every drawing crashed). Fixed: file closed before replace;
`--method learned` without a model stops; an all-crash run raises; reports count crashed drawings.

### References that were wrong (A44, A46)
- FloorPlanCAD rooms: the "rule result kept" fallback fired on the true labels where they mark no walls
  (0029-0526, a car park): 15 of 81 reference rooms were bay lines and car outlines. Now 66 reference rooms.
- ArchCAD windows: glass grouped by touching split each window symbol into its panes: 376 -> 111 true
  windows on the 100 test slices (1a30af18: 20 -> 5). Window F1 with the corrected truth: v4 0.49,
  v5 0.43, v6 0.44 (v6 finds 42 of 111, v4 47).

### Fusion bugs found through v6's losses (A47, A48)
- 0054-0004: hatched strips kept as walls by a tie (one face 0.7, the other 0.13: share 0.5). Mean
  probability against the tuned threshold: 8 -> 6 rooms (truth 2).
- 0460-0018: learned faces (assumed 0.25 m body) made true walls "glued too thick": 23 true wall faces
  lost, room lost. Learned faces out of the glued test, classifier belief first: 14 lost, room found.
- After both: FloorPlanCAD rooms (40 drawings, 65 reference rooms) v4 0.747, v6 0.747 (morning: 0.73 / 0.70).

### Room areas on real CAD (scratch analysis, v6, 40 FloorPlanCAD drawings)
Median predicted/reference area 0.962; 43% within 5%. Of matched reference area: 4.3% missing as a thin
band along walls, 3.8% missing as chunks, 1.2% / 3.3% extra. The bands follow rule walls pairing a true
face with a line inside the room: lift car + wall 6.7 m2, unlabelled + wall 3.5, two true faces 0.9.
Candidate fix (sandbox, rebuilt walls from believed lines replace such a mixed wall): areas within 5%
v6 43% -> 57%, v4 45% -> 53%; FloorPlanCAD room F1 v6 0.747 -> 0.736, v4 0.747 -> 0.723; ArchCAD rooms
v6 0.632 (area 50%); generated rooms 1.000 DXF and PDF, planted 24/24 for both models.
