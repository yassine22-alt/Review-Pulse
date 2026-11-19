# ReviewPulse verification results

## Measured

### Current Gemini ceiling access

M01–M16, A01–A15 and T01–T15 are development data in the requested hosted
comparison. The historical thermal holdout below describes the earlier run.
No fourth-document held-out evaluation has been run.

The key authenticated to Google's API. One regulation-only access check
generated a response from Gemini 3.8 Flash. The subsequent ceiling attempt
stopped during repeated HTTP 503 responses. Gemini 3.1 Pro reported free-tier
quota limits of 0 for input tokens, requests per minute and requests per day.
The [access investigation](gemini-ceiling-status.md) records model-specific
responses, the unchanged pipeline commit and the distinction between
transport failure and interpretation failure.

Completed hosted drafting evaluations are **0/46**. Matching or wrong
interpretation rates are unmeasured. Wrong approvable / approvable is
undefined, **0/0**. The M01 artifact's UNRESOLVED status came from failed API
calls and is reported as API_UNAVAILABLE. It is excluded from semantic failure
counts. The requested redesign and its before/after comparison await the
hosted baseline.

The raster investigation identified a failed checksum in the EasyOCR Latin
recognition cache. The installed EasyOCR corruption-recovery branch used an
undefined `corrupt_msg`, causing the earlier NameError. Restoring the official
checksum-verified recognition checkpoint fixed that local cache defect. The
segmentation source and checkpoint stayed identical to the pinned version.
A comparison on one prepared synthetic plan had **0/262,144** changed class
pixels, a maximum probability difference of 0.0, and equal rescale factors.
The [regression artifact](../reports/segmentation-regression-gemini-round.json)
records hashes and the scope of this comparison.

The **complete slow selection passed 45/45**, with **0 failures**, **0 skipped**
and **948 non-slow tests deselected**, in 905.97 seconds. All five previously
crashing raster acceptance cases passed. The
[JUnit report](../reports/gemini-complete-slow.xml) records every selected test.
The cache repair and regression evidence were pushed at
`574a298e2c5f90ea8e349dd26b7b0ad70a310d24`.

| Requested item in this round | Status |
| --- | --- |
| 1, hosted ceiling on 46 obligations | Blocked by provider availability and quota. Access report pushed at `12528a0bfd6420e65b63b90a5e89eadd0ecc7cf0` |
| 2, redesign and paired development comparison | Pending the hosted ceiling diagnosis |
| 3, applicability discovery without supplied scope | Unmeasured |
| 4, fourth-document frozen labels and hosted/local comparison | Pending. No fourth-document model run or label freeze |
| 5, full slow suite and raster cause | Complete, 45/45 passed and prediction comparison identical |
| 6, measured / not measured / do not claim | Updated in this document |

### Archived development baseline

The fire-safety and accessibility obligations are both development data for
this round. Historical artifact filenames are retained for reproducibility.
The same production checker was used on both French source sets. The complete
run used the app's bulk drafting path with real local Qwen2.5 1.5B, without
cached responses. The 7B configuration completed one diagnostic clause, M01,
in 322.8 seconds and retained no rule. It was stopped for runtime. A separate
1.5B single-clause probe also declined M01 and M02. Neither probe enters the
table. [Method and reproduction](interpreter-holdout-method.md) ·
[Per-obligation source references, frozen readings and drafts](interpreter-holdout-clauses.md) ·
[Paired execution results](../reports/morocco-interpreter-results.json) ·
[Raw drafting trace](../reports/morocco-interpreter-drafts.jsonl).

| Drafting outcome | 2-14-499 fire safety | 2-11-246 accessibility |
|---|---:|---:|
| Obligations submitted | 16 | 15 |
| Matches / partly matches / wrong retained drafts | 0 / 0 / 0 | 0 / 0 / 0 |
| Correctly unsupported | 8 | 15 |
| Needs interpretation or context review | 1 | 0 |
| Missed an executable interpretation under the frozen plan scope | 7 | 0 |
| Wrong rules presented / rules presented | 0 / 0 | 0 / 0 |
| Wrong rules approvable / rules approvable | 0 / 0 | 0 / 0 |

The last two denominators are empty. The results say nothing about how
often an offered draft is wrong. The fire-safety triage declined the count
and composition table obligations. Later stages also failed on source
spans, expression parsing, ownership of facts and a generation cap.

| Same 32 fire-safety checks | Manual interpretation | Only matching drafts approved | Drafts approved as written |
|---|---:|---:|---:|
| Initial decisions, pass / violated | 6 / 3 | 0 / 0 | 0 / 0 |
| Initial unresolved | 23 | 32 | 32 |
| Decisions with frozen reviewer evidence, pass / violated | 8 / 8 | 0 / 0 | 0 / 0 |
| Unresolved with reviewer evidence | 16 | 32 | 32 |
| False passes, initial / reviewed | 0 / 0 | 0 / 0 | 0 / 0 |
| Confirmed violation precision, initial / reviewed | 3/3 / 8/8 | undefined / undefined | undefined / undefined |
| Manual decisions lost, initial / reviewed | — | 9 / 16 | 9 / 16 |
| Manual decisions changed to the wrong verdict | — | 0 | 0 |

Both scripted approval policies had zero candidates to approve. The
accessibility transfer run had zero correct drafts, zero automatic decisions,
zero false passes, and 15 unresolved obligations. The blockers were missing
evidence (9), missing computation (5), specialist judgment (1),
interpretation (0), and incomplete inventory (0). These are the benchmark
author's categories. Several model explanations did not name the real gap.
No checker changes were needed to run the second document. Useful adaptation
was not demonstrated.

### Manual execution comparison

This development comparison uses 16 separately scored obligations from Morocco's Decree 2-14-499
across two independently specified synthetic ground-floor plans. Separately scored
obligations can share a numbered provision. All 32 clause–plan pairs are applicable
under the published fixture assumptions. The [manual labels](../reports/morocco-holdout-labels.json)
were frozen in commit `2a60396` before checker execution. The baseline is
`bc6f7892`, the remote tip before merging the count upgrade. The source is the
[published French Bulletin Officiel annex](https://aute.gov.ma/s/a/library/2023-11-01/0a4d2c47-5b19-4b4f-858f-67f605534364.pdf).
The historical pre-freeze excerpt scan found no matching checked-in corpus
entries. This decree now belongs to the development set.

| Same 32 applicable checks | Before | After |
|---|---:|---:|
| Decided on initially available facts (pass / violated) | 7 (4 / 3) | 9 (6 / 3) |
| Additional decisions after the same reviewer evidence (pass / violated) | 9 (4 / 5) | 7 (2 / 5) |
| Still unresolved after review | 16 | 16 |
| False passes, initial / after review | 0 / 0 | 0 / 0 |
| Precision of confirmed violations, initial / after review | 3/3 / 8/8 | 3/3 / 8/8 |

Both newly automatic decisions are on plan A. Its two confirmed exits satisfy
the minimum count and establish the applicable travel-distance branch despite an
unresolved third candidate. Plan B's apparent second exit is a fixed panel.
The count and travel decision wait for the reviewed inventory in that plan.
The exact [before](../reports/morocco-holdout-before.json) and
[after](../reports/morocco-holdout-after.json) outputs include every clause,
outcome, source-fact gap and blocker category. After review, the remaining
blockers are missing evidence (12 pairs), missing computation (2) and specialist
judgment (2). Interpretation blockers are outside this execution experiment.

| Named gap after review | Distinct obligations it could unlock | Clause IDs |
|---|---:|---|
| Door glazing and operation evidence | 3 | M12, M13, M16 |
| Circulation finish schedule with classifications | 2 | M14, M15 |
| Isolated level-change detection | 1 | M09 |
| Partition and structure rating evidence | 1 | M10 |
| Smoke-control design verification | 1 | M11 |

These counts show which obligations reach each blocker on the two fixtures.
They are potential unlocks, subject to correct interpretation and verified
input, and do not forecast coverage on another project.

Inventory completeness defaults to false. In the app, a reviewer explicitly
confirms the extracted inventory against the drawing. A T1 scale or high
confidence in an individual door does not establish coverage. For bounded
counts, an upper bound requires completeness and trusted membership. Stairs
always have incomplete inventory in the current producer. A floor without
a connection to the outside in a multi-sheet set need not have a complete
route graph even after inventory review. An erroneous human attestation can
still lead to a wrong result. The checker cannot detect an omitted entity
from the completeness flag alone.

### Current development diagnosis and evidence ledger

The [31-obligation diagnosis](drafting-development-diagnosis.md) assigns a
terminal stage to every archived failure. Triage stopped 26/31, expression
parsing stopped 2/31, and source-span grounding, the generation cap and fact
ownership stopped 1/31 each. Four obligations went through repair before their
terminal failure. The numeric-table change sends rows through normal checked
drafting, where validation can still refuse a rule. There is no new rule family.

| [31 development obligations](../reports/morocco-development-after.jsonl), Qwen2.5 1.5B | Archived | Current |
| --- | ---: | ---: |
| Draft retained | 0/31 | 0/31 |
| Triage | 26/31 | 24/31 |
| Expression parse | 2/31 | 2/31 |
| Generation cap | 1/31 | 1/31 |
| Source-span grounding | 1/31 | 3/31 |
| Fact ownership | 1/31 | 1/31 |
| Other verifier or repair-only | 0/31 | 0/31 |

M01 and M02 advanced from triage to source-span grounding. Both repairs quoted
context outside the target row, so both were still declined. The other 29/31
kept the same terminal stage. There was no gain in retained rules. The rate
of wrong approvable drafts is undefined (0/0 in both runs).

The stronger-model probe used local Qwen2.5 7B on a Core i7-1165G7 CPU with
about 16 GB RAM and no VRAM offload. It ran the original pipeline, with the
same 384-token cap and a 90-second timeout per request. Its terminal counts
were timeouts 8/16, triage 7/16, semantic-verifier rejection 1/16, and retained
drafts 0/16. M15 produced a candidate about exit eligibility instead of
circulation finish ratings. The round-trip verifier refused it. The rate of
wrong approvable rules is undefined (0/0). These time-limited results do not
isolate model capacity from pipeline design. Qwen2.5 7B was the largest
locally installed model. No hosted API was configured. The run was paused
after six completed clauses while the smaller-model runs used the same
server, then resumed without changing completed responses.

In the [ledger demonstration](../reports/evidence-ledger-demo.json), five manually
scoped development rules ran against synthetic fixtures. They started
unresolved in 5/5 cases and generated typed requests with an entity, fact,
unit, reason, clause and suggested source.

| Obligation | Evidence requested | After attestation |
| --- | --- | --- |
| M12 | Transparency and colour of exit door glazing | Violated |
| M13 | Public exit door motion and motorization | Violated |
| M16 | Push release or easy operation of one device per leaf | Violated |
| A13 | Handrail on each side of the relevant passage | Violated |
| A15 | Accessible fixed telephone at each inventoried entrance | Satisfied |

All 5/5 agree with the fixture labels. Tests also check that incompatible
units are rejected and conflicting facts stay unresolved. The checker will not
use a missing, conflicting or untrusted value. Other trusted facts can still
establish an outcome independently. The ledger requires a rule and declared
bindings. Legacy facts can lack an origin. Fixture imports do not verify
reviewer identity or authenticate citations. Conflicts remain open when another
attestation is appended.

### Archived thermal run and execution ceiling

The third source in the earlier held-out run was Morocco's Decree 2-13-874, thermal annex, printed
page 4265 of the French official translation of the *Bulletin Officiel* no.
6306, 6 November 2014. The [gazette reproduction](https://anre.ma/wp-content/uploads/2020/09/Decret_n_2-13-874.pdf)
is hosted by Morocco's National Electricity Regulation Authority. The
[frozen labels](../reports/thermal-holdout-labels.json) were pushed first at
`64630d4e8e5c3f0fccd73f30a88325c41c9f163c`. The production code was pinned
at `4a26b89b01a6e34b10c1e784a6bdb7cfd211691e` before live drafting on the third
document. A unit test caught an eager table lookup on the single-clause path
in the initial pin. The correction runs it only in bulk triage and leaves
the development benchmark's bulk inputs on the same path. The benchmark
harness was pinned separately at `9eb53dd3ac20a91aea8e5ee80314c4f026d131f3`.

The sample is 15 numeric obligations from three adjacent residential table
rows, five per climate zone. The benchmark supplies climate zone, glazing band,
prescriptive path, occupancy and orientation scope. It declares the thermal
fact names and units as data. Models receive the source transcription and fact
descriptions. No measured values, frozen interpretations or truth labels enter
the prompts.

Using the frozen human interpretations, **15/15** were executable with existing
numeric comparisons and the ledger. With initial synthetic observations,
**6/15** were decided (3 satisfied, 3 violated). Attestations added **7/15**
decisions (4 satisfied, 3 violated), for **13/15** total. T10 lacked
solar-factor evidence. T14 had conflicting slab-resistance evidence. False
passes were 0/8 initially and 0/8 after attestation among the eight violated
labels. Violation precision was 3/3 initially and 6/6 after attestation.

The real 1.5B drafting run on this source retained **0/15** rules. Seven of
15 stopped at expression parsing and 8/15 at source-span grounding. The
fully automated run and the run with reviewer evidence each decided **0/15**,
with 15/15 unresolved because of interpretation. False passes were **0/8**
actually violated obligations. Confirmed-violation precision was undefined
(0/0). Approving every retained draft as-is gave the same results because
there were no retained drafts to approve. Relative to the manual ceiling,
the interpreter lost 6/15 initially available decisions and 13/15 decisions
after evidence. Wrongly changed decisive outcomes were 0/15.

The [per-obligation table](drafting-measured-clauses.md) contains all 31
development rows and all 15 thermal rows with scoped frozen interpretations,
terminal stages and execution outcomes. The [thermal raw trace](../reports/thermal-interpreter-drafts.jsonl)
and [execution results](../reports/thermal-interpreter-results.json) retain the
diagnostics. The existing checker can represent every selected numeric
obligation once its interpretation, scope and thermal fact binding are supplied.
The ledger adds a route for evidence. Neither resolves the observed automatic
drafting failures.

The thermal document name and fact identifiers have no matches in production
source, tests or runtime examples. Its source transcription and numeric gold
interpretations are stored as separate benchmark data. The old excerpt audit
below describes the earlier development baseline. Neither check can exclude
pretraining exposure.

### Verification

The final pinned version passed **946** non-slow tests, with **2** skipped and
**45** slow tests deselected. It used normal filesystem access after earlier
Windows cache read permission failures. The new ledger and drafting tests,
plus the three affected single-clause regressions, passed **18/18** in a
targeted run. Ruff and the whitespace checks passed.

The earlier full-suite attempt ran the initial ledger commit and finished
with **982 passed, 2 skipped, 9 failed**. Five raster acceptance cases crashed
with a model-loading `NameError: corrupt_msg`; three were the eager
single-clause table lookup corrected before the thermal model run; one was a
concurrent cache read `PermissionError`. The final complete slow suite has
not been rerun. The baseline raster comparison skipped because the baseline
checkout had no model snapshot, so this investigation did not establish the
cause or pre-existence of those raster crashes. The final non-slow suite
includes the concurrent cache test and it passed.

## Not measured

The new hosted ceiling, the requested drafting redesign's paired results,
automatic applicability discovery and the fourth-document comparison remain
unmeasured. No semantic comparison or wrong-approvable rate can be derived
from the failed API requests. Their completed evaluation denominator is
0/46. The local cache repair and passing raster tests do not resolve this
dependency.

Whole-document extraction, discovery of table applicability, drawing extraction
accuracy, other model settings, reviewer disagreement,
and coverage on real projects remain unmeasured. The samples are small.
The benchmark author wrote the labels and rated drafts without independent
review. The historical excerpt scan found zero matching excerpts in tracked
prompt, fixture or development files outside the holdout artifacts. It
does not rule out paraphrases or pretraining exposure.

## Do not claim

Successful key authentication or one successful access-check response does
not establish usable capacity for the 46-obligation experiment. An HTTP 503
or zero project quota cannot diagnose the interpreter's reasoning or its
pipeline. This round supplies no new automated-interpretation accuracy result.

Zero false passes with zero decisions is abstention. It does not establish
safety, precision, useful zero-code transfer, or statutory compliance.
The earlier two-decision gain applies only to manually interpreted rules
on the frozen fact fixtures. The provisional scale bound and the finite
checker capability set remain documented limitations.

The ledger demonstrates that named evidence can unblock some existing
expressions. Keep that coverage distinct from automated interpretation, plan
extraction, applicability discovery and the ability to calculate a fact that is
missing from the plan. The thermal sample has one table format and repeated
numeric operators. It cannot establish transfer to arbitrary regulation
documents. The benchmark author labelled the sample without independent
review.


## Archived pre-pilot status, 18 November 2026

# Review-Pulse results and current status

Updated 18 November 2026. The 46 fire-safety, accessibility and thermal
obligations are DEVELOPMENT data. They cannot support a held-out claim.

The current priority is measuring drafting rather than adding checking
capabilities. The offline redesign makes triage advisory and compiles typed,
schema-constrained model slots into the existing rule language. Drafts still
need source, type, unit and coverage validation and human approval. No new
plan computation or checking family has been added.

The compiler oracle retains **5/46** gold inputs with the active catalogue,
or **17/46** with author-proposed declarations. This does not measure an LLM.

The key now authenticates, without its value being displayed or stored.
Gemini 3.8 Flash exhausted its daily quota according to the user's dashboard
(22 used / 20 limit). Its transport failures are excluded from semantic counts.
Gemini 4 Hydrogen completed a same-model partial comparison: **2/46** clauses
per pipeline, **0/2** retained in either. Each arm used **8/8** successful
requests, then stopped at its configured allowance. These results do not
establish improved accuracy or separate all model errors from pipeline errors.

The fourth document is frozen and unrun: RPS 2000 version 2011, official French
Bulletin Officiel 6206, 21 November 2013. Its **17 obligations and 48 synthetic
scenarios** were committed at `41b1ad14b466fb52500b118d69593319da649e23`.
Interpretations and applicability labels remain separate from drafting input.

The user chose free quota across multiple days. A
[continuation worker](free-quota-continuation.md) is configured for the
remaining **44/46** hosted obligations per arm, starting after the **08:00 UTC
18 November** reset. It uses fixed checkouts and at most 19 requests per day.
The PC must stay awake; saved progress supports explicit resume after restart.
Do not pool models. Complete the local run too, then review the full comparison
before the fourth document runs once. No checker capabilities were added. The
unit-vocabulary gap remains documented without a claim of unlocked checks.

The resumed local snapshot has **24/46** completed, **0/24** retained: generation
cap **21/24**, absent source subject **3/24**. It remains incomplete, with
**22/46** pending. See the [cache snapshot](../reports/local-after-slots-cache-snapshot.json).
The first 20 recorded 0/60 request errors. Batch HTTP counters are incomplete
for the whole cache, because interrupted batches can leave completed entries.

## Measured

| Measurement | Result and scope |
| --- | --- |
| Gold-slot compiler, active catalogue | 5/46 exact reference trees and generated behavioral matches; 22/46 binding rejection; 17/46 verifier rejection; 2/46 context/binding unresolved |
| Gold-slot compiler, author-proposed facts | 17/46 exact and behavioral matches; 27/46 verifier rejection; 2/46 context/binding unresolved. Proposed facts do not create plan computations |
| Original local drafting, Qwen2.5 1.5B | 45/46 evaluated, 1/46 transport timeout. 1/45 semantic cases retained; that draft was wrong. Wrong technically approvable / approvable = 1/1 with a synthetic issue-free review, not a real critic |
| Generated behavior | 64 fact worlds per retained oracle input; finite tests, not a proof |
| Replacement credential | Visible after Windows restart; model-list authentication succeeded. Value never printed or written |
| Hosted original pipeline, replacement key | First batch: 3/3 errors in each of three cycles; 9/9 overall (7 HTTP 429, 2 timeouts). 4/4 unavailable per cycle; circuit prevented further calls. 0/46 semantic evaluations; all 46 pending |
| Hydrogen paired development sample | 2/46 completed per arm, 0/2 retained per arm. Original terminal stages: verifier 2/2. Structured: context/binding 1/2, schema 1/2. Wrong approvable / approvable undefined, 0/0 per arm |
| Hydrogen request accounting | 0/8 request errors per arm, 0/16 overall. Each arm stopped at its eight-request allowance; the next clause was interrupted by the client budget and 43/46 were not submitted |
| Request allowance and pacing tests | 7/7 passed: existing retry/cache tests plus new failed-request budget, cross-cycle allowance and request-spacing checks |
| Multi-day continuation tests | 13 continuation tests plus the 7 transport/budget tests passed 20/20. The current quota window has zero remaining worker allowance, so setup sends no new generation requests |
| Drafting-redesign non-slow suite | 978 passed, 2 skipped, 45 slow tests deselected; 530.44 seconds at e2d0acf4516d5e3395869f4f470108b0111e1053. The later runner-only allowance changes have the separate 7/7 targeted result above |
| Secrets scan | 597 working text files; 776 reachable Git blobs, 286 trees, 37 commits, including refs/reflogs; no credential-pattern match in scanned repository content. Exclusions and access failures are documented |
| Previous complete slow suite | 45/45 passed at the earlier checkpoint; this is historical validation, not a new interpreter result |
| Previous segmentation regression | 0/262,144 changed class pixels on one prepared synthetic plan; unchanged source/checkpoint, not real-plan accuracy |

Per-obligation oracle diagnostics are in
[slot-oracle-results.json](../reports/slot-oracle-results.json).
The [Hydrogen assessment](../reports/hydrogen-development-assessment.json)
lists all 46 obligations, their frozen readings, completed results or explicit
not-evaluated status. No final rule existed to compare as exact, partial or
wrong. Author notes retain the differences and request limitations.
[Structured drafting](structured-drafting.md) describes checks and limits.
[Secrets audit](secrets-audit.md) states scan exclusions and the chat exposure.
[Hosted runner](resilient-hosted-runner.md) describes retries, cache, circuit
limits and provider setup. [Fourth-document freeze](fourth-document-freeze.md)
records the official edition and source checksum.

## Not measured

- A full 46-obligation hosted comparison. Only 2/46 completed per arm on
  Hydrogen. The hosted-versus-local capacity gap remains unmeasured; the
  earlier wrong retained local width rule was not reached in the hosted run.
- Fourth-document drafting, unsupplied applicability discovery, end-to-end
  verdict accuracy, false passes or violation precision. Its model/checker
  evaluations are **0/17** obligations.
- Production accuracy gains from the redesign. Compiler-oracle matches do not
  establish source interpretation quality or usable application coverage.
- Independent label quality. Labels and gold slots were written by the
  benchmark author without independent review. The samples are small.
- Real reviewer evidence quality: ledger attestations in benchmark scenarios
  are synthetic. They are not independent measurements or professional review.

## Do not claim

- A reliable general regulation interpreter or adaptation to any document.
- That unresolved-only output demonstrates useful accuracy or is "safe".
- That schema validity, a round trip, human approval or finite behavioral tests
  prove legal or semantic correctness.
- That missing scale, membership, inventory or evidence can be assumed true.
  The provisional 25% scale bound is a placeholder, not calibrated accuracy.
- That proposed fact declarations remove the finite checker capability limit.
  Evidence attestation supplies labelled facts; it does not implement missing
  geometry, physics or specialist judgment.
- That earlier thermal runs remain held-out after development used them, or
  that these unreviewed synthetic samples establish performance in practice.

Earlier runs, superseded statuses and their original limitations are preserved
in [results history](results-history.md). Historical provider availability does
not establish connectivity for the replacement credential.


## Archived before applicability priority change, 18 November 2026

# Review-Pulse results and current status

Updated 18 November 2026. All 46 fire-safety, accessibility and thermal
obligations are DEVELOPMENT data. The fourth document remains frozen and
unrun. Labels were written by the benchmark author without independent
review; ledger attestations and plan scenarios are synthetic. These are small
samples, not evidence of general regulatory accuracy.

The hosted worker now prioritizes a 12-obligation stratified pilot on both
arms: five thermal, four executable fire-safety and three accessibility
obligations. The pre-declaration snapshot completed only T01: **1/12 per arm,
0/1 retained per arm**. Original stopped at the verifier; structured stopped
at context/binding after a unit diagnostic. Only **1/5 thermal cases per arm**
has been evaluated. Do not describe this as five thermal failures. HTTP 503
errors were **5/9 attempts per arm**, excluded from semantic failure counts.

The production declaration change has its own frozen hosted cohort. The
worker retains the three completed original evaluations, restarts the changed
structured arm from **0/46**, and preserves all previous request debits. It is
waiting for free quota: **18/19** allowance used in the current window,
**1/19** left, below the minimum start budget. Next reset is **19 November,
08:00 UTC**. No billing was enabled. The PC must stay awake; a restart requires
explicit resume. Previous structured versions are archived, never pooled.

Offline, validated fact declarations compile **13/46** gold frames, versus
**5/46** with the active catalogue and **17/46** with permissive author-added
facts and collections. The 13 retained frames match the 13 frozen trees and
their generated behavior checks. Eight of these 13 need new declared facts;
declarations supply no values. They require named reviewer evidence before
decisive execution. This measures deterministic compilation, not LLM accuracy.

The local cap diagnosis is complete, but the paired model result is not.
All **21/21** instrumented replays exhibit repetition. Prompt-only wire
instructions did not eliminate it. A cap-only bounded-schema variant is
running the same 24 cases with unchanged model settings; declaration changes
are excluded. Its first completed case is source-span rejected (1/24 completed,
0/1 retained). Next: finish and grade that cohort, inspect the paired hosted
pilot, then diagnose zero thermal retention if both five-case arms complete
without retaining a rule. Do not run the fourth document.

## Measured

| Measurement | Counts and scope |
| --- | --- |
| Gold-slot oracle, active catalogue | Exact and behavioral matches 5/46; binding rejected 22/46, verifier rejected 17/46, context unresolved 2/46 |
| Gold-slot oracle, permissive author additions | Exact and behavioral matches 17/46; verifier rejected 27/46, context unresolved 2/46. This mode also adds missing collections and is not the production policy |
| Gold-slot oracle, validated declarations | Retained 13/46; exact trees 13/13 retained; behavioral matches 13/13 retained. Rejections: verifier 23/46, entity binding 8/46, context 2/46, unit vocabulary 0/46 |
| Thermal pilot gold frames | Verifier rejection 5/5: number coverage requires the table's 26–35% scope bounds, but frozen gold expressions assume that scope externally. Scope-contract mismatch, not a model result; no check or label bypassed |
| Oracle behavior test scope | 64 generated complete-value worlds per retained frame; declaration provenance stripped for logical comparison only; matching evaluation errors receive no credit |
| Historical local 24-case baseline | Retained 0/24; generation cap 21/24; absent source subject 3/24 |
| Cap diagnosis | Historical raw responses available 0/21. New instrumented replays completed 21/21: repeated node records/IDs 20/21; repeated prose during repair 1/21. Some diagnostic replays stop loops early |
| Prompt-only wire fix | Superseded partial run, not a 24-case result. Repeated output and a transport timeout remained; no accuracy improvement established |
| Bounded-schema local snapshot | Semantic completion 1/24, source-span rejected 1/1, retained 0/1. Paired M01 stage: generation cap → source span; remaining 23/24 pending. This is not an accuracy gain |
| Hosted pilot, frozen pre-declaration pipelines | Semantic completion 1/12 pilot cases per arm, 1/5 thermal per arm. Retention 0/1 per arm; matches/partly matches/wrong each 0/0 retained candidates, undefined |
| Hosted pilot approvability | Wrong approvable / approvable = 0/0 in each arm, undefined; no final program existed to grade |
| Hosted pilot transport | HTTP failures 10/18 attempts overall, 5/9 per arm; all 10 were HTTP 503. Per-batch denominators are retained in the pilot snapshot; no API-unavailable row is counted as a semantic failure |
| Declaration and compatibility checks | Earlier declaration/runtime/interpreter checks 80/80 passed; focused current drafting/declaration/fallback tests 40/40 passed; isolated cap-only schema tests 12/12 passed |
| Broad suite after correction | 1,014 passed, 2 skipped, 45 slow tests excluded; 900.23 seconds. Initial run found a fallback compatibility regression (1 failure); it was corrected and tested |
| Current worktree secret check | 1,659 source, script, test, document, report and run text files (38,980,509 bytes); current environment key checked exactly plus provider credential patterns; 0/1,659 files matched, 0 unreadable. This is not a new full-history audit |
| Worker checks | 23/23 targeted transport, quota, continuation and phase-order tests passed at the pilot checkpoint |
| Fourth document freeze | RPS 2000 version 2011; official French Bulletin Officiel 6206, 21 November 2013; 17 obligations and 48 synthetic scenarios committed at `41b1ad14b466fb52500b118d69593319da649e23`; model/checker runs 0/17 |

Per-obligation and per-stage evidence:

- [Hosted pilot snapshot](../reports/hosted-stratified-pilot-snapshot.json): frozen reading, retained candidate or explicit absence, terminal stage, diagnostics and batch request counts for all 12 selected obligations in both arms.
- [Gold-slot declaration oracle](../reports/slot-oracle-declarations.json): all 46 cases across the three catalogue modes.
- [Reviewed replay diagnosis](../reports/local-cap-reviewed-diagnosis.json): all 21 cap cases and local raw trace paths. Raw responses remain local.
- [Cap-only protocol](../reports/local-cap-protocol.json): unchanged model settings, isolated source fingerprint and reproducible patch. Live local results are `reports/local-schema-after-24.json`.
- [Local comparison snapshot](../reports/local-cap-comparison-snapshot.json): all 24 paired IDs, completed stages and explicit pending cases. Local continuation counts are `reports/local-cap-continuation/comparison.json`; retained candidates are not automatically graded or approved.
- [Hosted protocol](../reports/free-quota-protocol.json): frozen versions and quota accounting. Live progress is `reports/free-quota-declared-eval/progress.json`.

[Pilot design](development-pilot.md), [cap diagnosis](local-generation-cap.md),
[fact-declaration design](fact-declarations.md) and
[continuation instructions](free-quota-continuation.md) explain the choices.

## Not measured

- A completed paired 12-case hosted pilot or full 46-case model comparison.
  The latest structured cohort has 0/46 completed; earlier versions stay separate.
- A completed same-24 local before/after result or correctness grading of any
  new retained local candidates. A reduced cap-failure count alone would not
  measure correct interpretation.
- Real model-proposed declaration quality. The 13/46 result uses author-supplied
  gold declarations, not model-generated declarations.
- Fourth-document interpretation, unsupplied applicability discovery or
  end-to-end accuracy: 0/17 evaluated. No fourth-document result is used for tuning.
- False-pass rate or confirmed-violation precision for the latest interpreter.
  There are no paired end-to-end results to supply those denominators.
- Independent label validity, real reviewer evidence quality, real-plan
  segmentation accuracy or legal sufficiency.

## Do not claim

- Improved interpreter accuracy, general adaptation to any rule set, or a fair
  model-capacity ceiling. Those questions remain open until paired results exist.
- That zero decisions, schema validity, round trips, finite behavior tests or
  human approval establish correctness or make the system "safe".
- That declarations implement geometry, physics, missing entity inventories or
  specialist judgment. Evidence requests expose those gaps; they do not compute values.
- That missing or conflicting evidence, unknown membership, uncertain scale or
  incomplete inventory may be assumed verified. The provisional 25% scale bound
  remains an uncalibrated placeholder.
- Unlimited expression capacity: the generation wire budget permits 64 nodes
  and bounded diagnostic messages; larger clauses can remain unresolved.
- Any held-out result on the 46 development obligations. The only sealed fourth
  document is unrun. Labels have no independent review; attestations are synthetic.

Earlier results and superseded statuses are preserved in
[results history](results-history.md). Provider model revisions can change
behind a fixed API identifier; that drift has not been measured.


## Archived: status before the 18 November recovery sprint

# Review-Pulse results and current status

Updated 18 November 2026. The 46 fire-safety, accessibility and thermal
obligations are DEVELOPMENT data. The fourth document stays sealed and unrun.
Labels are benchmark-author annotations without independent review; evidence
attestations and plan scenarios are synthetic. These small samples do not
establish general regulatory accuracy.

Applicability now has typed project-metadata conditions separate from the
requirement predicate. Missing, conflicting, unverified or wrongly typed
metadata creates reviewer requests. Scope bounds count toward source coverage
without entering the requirement. The gold-slot oracle retains **28/46**,
versus **13/46** before separation. The remaining rejections are verifier
**8/46**, entity/catalogue binding **8/46**, missing context **2/46**. This is
deterministic compilation, not an LLM accuracy result. Only **15/46** metadata
scopes have supplemental gold annotations; **31/46** remain unannotated.

Raw-field scoring is independent of retention. The stopped 1.5B run completed
**15/24**, retaining **0/15**. Some raw output exists for **16/24**: clause-span
agreement is **13/16**, while the other scored fields have zero exact matches
on their eligible denominators below. The local workers are stopped. A single
field-sized schema path is implemented; one 7B backend-only probe confirms
JSON-schema support, not interpretation quality. There is no further 1.5B tuning.

The hosted work is now a finite **12-obligation, two-arm first-draft pilot**,
with common subject and metadata fields. It has **0/12** completed per arm.
The attempts returned three HTTP 503s and one HTTP 400; a separate diagnostic
returned HTTP 429. These are not semantic failures. Array bounds were moved
out of the hosted decoding schema into compiler checks, but provider
acceptance of that adaptation is untested. No billing or provider was changed,
and the old 46-case worker was stopped. No standing quota protocol was expanded.

The strong-model thermal score is **undefined (0/0 slots; 0/5 outputs)**, so
the requested 70% decision is pending. Next: resume the new pilot version when
quota permits, measure slots and retained-rule correctness separately, and
apply the decision rule. Do not infer model capacity from unavailable responses
or run the fourth document.

## Measured

Today’s demonstrated end-to-end path starts with manually interpreted rules
and supplied synthetic plan facts under the frozen fixture scope. The checker
evaluates them, exposes unresolved evidence and updates findings after reviewer
evidence. Re-running the same **32 applicable clause–plan pairs** on current
code gives **9/32** initial decisions (6 satisfied, 3 violated), **16/32** after
review (8 satisfied, 8 violated), and **16/32** still unresolved. False passes
are **0/15** gold violations; confirmed-violation precision is **3/3** initially
and **8/8** after review. This demonstrates that manual-rule checking path,
not automated regulation interpretation or accurate extraction from uploaded
real drawings. See [current manual execution](../reports/manual-execution-current.json).

| Measurement | Counts and scope |
| --- | --- |
| Gold slots before applicability separation | Retained 13/46; verifier rejection 23/46; entity binding 8/46; context 2/46 |
| Gold slots after separation | Retained 28/46; verifier rejection 8/46; entity binding 8/46; context 2/46; unit vocabulary rejection 0/46 |
| Retained requirement checks | Exact frozen trees 28/28; generated requirement behavior matches 28/28, 64 complete-value worlds each. Metadata/provenance stripped only for predicate comparison; scope is tested separately |
| Supplemental scope labels | Thermal metadata annotated 15/46, other scopes unannotated 31/46; committed before the oracle at `5537191c37a3b864ba7ca719469991d1a92c5db4` |
| Existing 1.5B bounded run, stopped | Evaluated 15/24, retained 0/15; source span 2/15, compile 1/15, subject 11/15, type/unit 1/15. No completed result for 9/24 |
| Local constrained-decoding mechanics | Qwen2.5 7B, Q4_K_M, CPU/16 GB RAM, no GPU; 1/1 schema-only probe passed, 12 output tokens, 30.14 seconds; 0 regulation clauses submitted |
| Historical hosted raw availability | 0 raw responses retained for previously completed hosted cases; historical slot accuracies undefined, not zero |
| New hosted first-draft pilot | Completed 0/12 per arm; retained / evaluated 0/0 per arm; all slot-accuracy denominators 0. First invocation: 3/3 HTTP 503; second: 1/1 HTTP 400; separate diagnostic: 1/1 HTTP 429 |
| Integration limitation | HTTP 400 is request rejection, not model error. Exact cause unknown. Schema complexity is a candidate; hosted schema adaptation acceptance unmeasured |
| Applicability/drafting/ledger tests | 90/90 targeted tests passed before fieldwise addition |
| Fieldwise assembly and associated tests | 35/35 passed; no fieldwise semantic benchmark run |
| Broad verification | Initial run: 1,036 passed, 2 skipped, 45 slow tests excluded (332.16 s). Post-adapter run: 1,042 passed, 2 skipped, 45 slow tests excluded (307.35 s). Subsequent focused adapter/pilot checks: 22/22; final metadata/interpreter/findings/ledger/pilot checks: 82/82 |
| Fourth-document integrity | RPS 2000 version 2011, official French Bulletin Officiel 6206, 21 November 2013; 17 obligations, 48 synthetic scenarios; frozen files unchanged; model/checker evaluation 0/17 |
| Worktree integrity check | 1,764 text artifacts scanned; 0/1,764 matched the current environment key or credential patterns, 0 unreadable. Two frozen fourth-document files match their freeze commit. This is not a new full-history secrets audit |

Final-captured local slot agreement, before validators:

| Slot | Bounded run | Prompt-only partial run | Diagnostic cap replays |
| --- | --- | --- | --- |
| Raw cases available / selected cohort | 16/24 | 2/24 | 21/46 development corpus |
| Subject exact | 0/16 | 0/2 | 0/21 |
| Fact exact | 0/15 | 0/2 | 0/20 |
| Operator exact | 0/14 | 0/2 | 0/19 |
| Value exact | 0/9 | 0/1 | 0/11 |
| Unit exact | 0/9 | 0/1 | 0/11 |
| Metadata applicability exact | undefined, 0/0 | undefined, 0/0 | undefined, 0/0 |
| Clause span exact | 13/16 | 0/2 | 1/21 |

Denominators exclude gold-inapplicable fields and unannotated scope. Completed
fields in truncated raw responses are scored; missing requested fields count
incorrect. Expression interfaces that never requested a subject do not receive
a fabricated subject score. The replays are early-stopped diagnostics, not
recovered historical responses or a comparable before/after run. Their fact
atom recall is **2/34**, despite **0/20** exact fact-set agreement. Retention
does not erase that partial information. These normalized field sets do not
measure associations between fields or whole-rule correctness.

Evidence and design details:

- [Applicability policy and full rejection taxonomy](applicability-policy.md); [46-case oracle](../reports/slot-oracle-applicability.json).
- [Raw-slot scoring](slot-scoring.md), with initial/final per-case scores and missing-record status in linked reports.
- [One local decoding change](local-fieldwise.md); [backend-only probe](../reports/local-field-schema-probe.json).
- [Minimal hosted pilot and resume command](scoped-pilot.md); [request results](../reports/scoped-first-draft-pilot.json).
- [Pending decision and conditional edit-burden evaluation](interpreter-decision.md).
- [Post-adapter non-slow test report](../reports/applicability-final-nonslow.xml).

## Not measured

- Strong-model slot accuracy with separated applicability: **0/5** thermal
  outputs. The 70% rule cannot be applied to an undefined **0/0** score.
- A completed paired hosted pilot: **0/12** evaluated per arm. Provider
  acceptance of the revised schema is also untested.
- Accuracy or latency gains from per-field local prompting. Its probe tested
  constrained output mechanics only; the existing 1.5B result remains negative.
- Full metadata-scope discovery on the other **31/46** development clauses.
  They are not labelled globally applicable merely because scope is unannotated.
- Whole-rule correctness from field-set agreement, the rate of wrong approvable
  new drafts, or new end-to-end interpreter false passes and violation precision.
- Independent label validity, real reviewer evidence quality, or real drawing
  extraction accuracy. Current attestations and plans are synthetic.
- Fourth-document generalization, interpretation or applicability discovery:
  **0/17** evaluated. Its labels have not been used for tuning.

## Do not claim

- A reliable general interpreter, demonstrated adaptation to arbitrary rule
  sets, improved model accuracy or a fair model-capacity ceiling.
- That 28/46 compiler retention means 28/46 model interpretations are correct
  or that 64 generated worlds prove equivalence.
- That high slot agreement establishes correct field associations, scope,
  quantifiers, exceptions or legal meaning. The 70% criterion is a research
  decision rule, not a regulatory acceptance threshold.
- That request errors are semantic failures, or that no decisions demonstrate
  useful accuracy or make the system "safe".
- That declarations create observations, inventories or new computations.
  Project metadata must be declared and verified; missing evidence stays missing.
- Unlimited applicability expressiveness: current metadata conditions are
  conjunctive; alternative or ambiguous scope requires review, with canonical
  string values. Human approval remains necessary.
- That synthetic manual-rule results establish upload-to-verdict accuracy on
  real plans. The 25% scale bound remains provisional and uncalibrated.

Superseded statuses and earlier measurements are in
[results history](results-history.md). No billing changes, new checker family
or fourth-document run were made in this round.


## Archived: recovery-sprint status before the free-hosted comparison

# Review-Pulse results and current status

Updated 18 November 2026. **The deterministic compiler improved; improved
complete automated interpretation has not been demonstrated.** The 46 Morocco
fire, accessibility and thermal obligations are DEVELOPMENT data. The fourth
RPS document remains unchanged, sealed and unrun. Labels have no independent
review. Earlier benchmark plans and ledger attestations remain synthetic.

Gold-input compilation now retains **29/46**, versus the reproduced **28/46**.
The extra case, A08, was wrongly rejected because the French number vocabulary
stopped at ten. Whole numeral phrases now ground as a unit; unsupported larger
phrases cannot license a smaller threshold. A second general fix reads
construction notation such as `2-1/2"` as one quantity. On a real publisher's
drawing, this removes one unjustified rejection: **2/4 -> 3/4** manually
interpreted whole clauses compile. Neither change adds plan computations or
weakens the verdict policy.

The local-model experiment did not establish a winner. Qwen2.5 7B delivered
**0/7** complete monolithic responses within the configured 180-second socket
budget. Attempted compact and decomposed calls also timed out. Partial outputs
contain visible semantic errors as well as excessive output. They never became
approvable rules. The model was CPU-only on 15.7 GiB RAM with roughly 0.6 GiB
available while loaded. One smaller-model download failed for disk space; it
was not evaluated. No hosted calls, billing changes or 1.5B tuning were made.

A reproducible real-drawing trace now shows exact source clauses, manual slots,
approval, plan evidence, findings and missing facts. **0/4 whole clauses are
decided**, before or after the fix. A separately labelled nominal-width
component passes on a reviewer-read schedule value; this is not a full-clause
pass. The useful next experiment is a completed paired semantic comparison on
adequate local resources, before choosing a new default extraction method.
Free storage and memory first; do not tune on the sealed document.

## Measured

| Measurement | Reproduced before | After | Meaning / denominator |
| --- | --- | --- | --- |
| Gold slots, active catalogue | 5/46 retained | 5/46 | Existing fact coverage unchanged |
| Gold slots, validated fact declarations | 13/46 retained | 14/46 | Author-supplied declarations; no observed values created |
| Gold slots, separated applicability | 28/46 retained | 29/46 | Manual gold inputs, not LLM outputs |
| Retained requirement trees / generated behavior | 28/28 | 29/29 | Exact reference trees; 64 synthetic complete-value worlds per case, not a semantic proof |
| Remaining gold-input rejections | 18/46 | 17/46 | Verifier 7/46, entity binding 8/46, context 2/46 |
| Local monolithic complete outputs | 0/7 | No completed replacement cohort | Runtime failures; semantic correctness and wrong-approvable rate undefined (0/0) |
| Real drawing, manually interpreted whole clauses compiled | 2/4 | 3/4 | Same four author interpretations, source and evidence |
| Real drawing, whole-clause decisions | 0/4 | 0/4 | Missing evidence/inventory and one ambiguous requirement remain |
| Real drawing, nominal-width component | 1/1 satisfied | 1/1 satisfied | Single reviewer-selected schedule type, not a complete requirement |
| Existing manual synthetic execution | 9/32 decided initially | 16/32 with reviewer evidence | Same prior fixture: false passes 0/15 gold violations; violation precision 3/3 initially, 8/8 reviewed; not an upgrade gain |

See [before oracle](../reports/recovery-oracle-before.json),
[after oracle](../reports/recovery-oracle-after.json), and the
[46-case diagnosis](../reports/recovery-diagnosis.json), which records source,
expected interpretation, actual rejection, before/after and likely cause.
Baseline/protocol freeze was committed as
`55cb6e018d056340e8a429b20a94444b39e56d59`, before the fixes.
French grounding was committed as `313e018f`.

### Where correctness is lost

- **Document reading:** existing context assembly preserves parents, explicit
  references and definitions; implicit references remain limited. In the real
  drawing, the selected multi-line egress and garage notes cross automatic
  clause boundaries. Reviewer-selected exact spans are therefore explicit in
  the demonstration; this is not automatic segmentation success.
- **Semantic generation:** [monolithic results](../reports/recovery-monolithic.json)
  are 7/7 runtime-limited. The [exploratory alternatives](../reports/recovery-variants.json)
  attempted T01 reading and three formalizations, then M03 expression control.
  All four formalizations timed out; five other cases were unattempted. The
  reading completed in 47.95 seconds but partly misread glazing scope as
  efficiency and introduced uncertain exceptions. The three T01 formalization
  prefixes invent extra thresholds, mix scope into requirements or use invalid
  syntax. These are observed prefix errors, not scored complete interpretations.
  Wrong approvable / approvable is **0/0**, not a measured 0% error rate.
  Repair requests issued: **0/0 eligible complete constrained candidates**.
- **Compiler/verifier:** of 17 remaining development rejections, **8/17** lack
  entity collections (step groups, level changes, sidewalks, curb cuts,
  passages, turns, entrances); **3/17** concern quantity/context coverage;
  **3/17** mistake noun enumeration for logical alternatives; **1/17** treats
  material-class digits as thresholds; **2/17** require external specialist
  context. These are likely causes requiring review, not grounds to bypass
  checks. A05 still rejects after its number is recognized because its
  alternative semantics remain unresolved.
- **Plan evidence:** the real sheet's vector-only baseline found two room
  regions, not a reviewed complete inventory. The drawing visibly labels four
  bedrooms. Zero schedules were recovered. A warning applies a rendering-only
  scale disclaimer to the plan. Teammate segmentation models were not evaluated;
  this is not evidence of their accuracy or regression.

The compact-expression control was added after the baseline timeouts and is
exploratory, not an originally frozen fifth arm. Reading/formalization token
budgets were 384/1152, monolithic/control 1536, potential repair 512; raw traces
include latency and partial output. Some tests ran concurrently, so timings are
not isolated throughput benchmarks. No decomposed strategy is promoted into
the application default without a completed correctness comparison.

### Reproduce the real-source trace

Download the first-party [Chief Architect Modern Bungalow sample](https://cloud.chiefarchitect.com/1/samples/projects/modern-bungalow/modern-bungalow.pdf),
July 2024, sheet A-7 (PDF page 7). This is a published project drawing and its
notes, not an official building regulation or a claim of legal applicability.
The publisher's address is not taken as the project's jurisdiction.

After the normal README environment setup:

```powershell
.venv/Scripts/python.exe scripts/recovery_drawing_demo.py data/real_plans/recovery/modern-bungalow.pdf runs/recovery-demo
```

The input PDF must match the recorded SHA-256. The script makes no LLM calls.
It extracts source text and vector geometry, compiles the supplied manual slots
through the existing validators, records author approval and evaluates against
explicit evidence. It writes sheet/building JSON, findings, a drawing preview and `report.html`
with expandable rule/evidence traces. See
[labels and provenance](../reports/recovery-drawing-labels.json),
[before findings](../reports/recovery-drawing-before.json) and
[after findings](../reports/recovery-drawing-after.json).

The garage/living relationship is preserved as a required fact. No connecting
room, thickness, rating, material or self-closing behavior is inferred from a
schedule tag. The exterior-exit clause remains NEEDS_REVIEW because its U-value
unit is absent; its stated MIN direction is not silently corrected. D06's
`3076` schedule label supplies a reviewer-read nominal width of 36 inches;
it supplies neither 32-inch clear opening nor operability or glazing evidence.
All reviewer observations here are author readings of the real sample drawing,
not independently verified as-built measurements. Whole-clause false-pass and
violation-precision rates are undefined: **0 labelled decisive cases, 0
confirmed violations**. No full-clause accuracy or safety claim follows.

The development oracle can be reproduced with
`python scripts/evaluate_slot_oracle.py <accessibility-source-text> reports/oracle.json`;
source provenance and extraction expectations are in
[development source manifest](../reports/morocco-interpreter-source.json).

### Design choice and research

The production change is restricted to generic quantity grounding with
vocabulary stored as data. It does not silently accept ambiguous alternatives,
create inventories or convert declarations into observed facts. Small
research helpers test source-only reading, constrained formalization and
single-field diagnostic repair against the existing compiler. They remain
experimental. [Grammar-constrained decoding research](https://aclanthology.org/2023.emnlp-main.674/)
and [JSONSchemaBench](https://arxiv.org/abs/2501.10868) motivate testing structural
constraints separately from meaning; they do not establish correctness here.
The single attempted smaller download was the official non-thinking
[Qwen3 4B Instruct 2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507).
It was chosen for lower memory use, but storage prevented installation; no
performance claim can be made for it.

### Verification

Final non-slow suite: **1,069 passed, 2 skipped, 45 slow tests excluded**
in 277.05 seconds. The new quantity counterexamples and research-helper tests
are included. Ruff and diff whitespace checks pass. This is software regression
verification, not semantic or segmentation accuracy. See
[validation record](../reports/recovery-validation.json).

## Not measured

- Improved complete model interpretation, model-capacity ceiling, or a fair
  completed comparison between monolithic, decomposed and repaired drafts.
- Independent label correctness, held-out improvement or automatic
  applicability discovery across unfamiliar rule documents. Only 15/46 current
  scopes have supplemental author annotations. The fourth document is unrun.
- Real automatic upload-to-verdict accuracy, whole-building perception,
  confirmed connection inventories or calibrated measurement uncertainty.
- A reduction in false accepted model rules: there were no complete candidate
  outputs in the new local formalization experiment.
- The slow raster/dataset tests and teammate segmentation accuracy in this sprint.

## Do not claim

- A reliable general regulation interpreter, a winning decomposed architecture,
  improved model accuracy, or adaptation to arbitrary regulations.
- That 29/46 manual gold compilations are 29 correct automatic interpretations,
  or that compilation, syntax validity, source matching or approval proves meaning.
- That 0/4 decisions is useful accuracy or demonstrates safety. A correctly
  unresolved result diagnoses a blocker; it does not fulfill the checking goal.
- That the nominal-width component is a full exterior-door pass, that material
  evidence comes from line geometry, or that a partial inventory is complete.
- A precision gain from a 0/0 denominator. Existing synthetic tests and the
  provisional 25% scale bound do not establish real-world accuracy.

Prior statuses are in [results history](results-history.md). The honest result
is fewer unjustified compiler rejections, with an inspectable assisted real-source
trace; improved automated understanding and useful whole-clause decision coverage
remain unproven.


## 18 November 2026: free-hosted comparison, incomplete

No billing was enabled. Keys were read from the environment. Regulation text, catalogue type vocabulary and output contracts were sent; drawings were processed locally. ElevenLabs and Gemini were not called. The unavailable Mistral/Meta-Llama request was replaced, with user approval, by GPT-OSS-120B and Qwen3.8-27B on Groq. [Mistral current policy](https://docs.mistral.ai/admin/billing-usage/usage-limits) states free mode has no API access. The user supplied Groq console limits: 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD per model. Authenticated model listing and response headers confirmed model IDs and nominal TPM/RPD. The authenticated console itself required login; account limits were user-transcribed, not read from a logged-in session.

Both arms use the same compact expression research contract and final deterministic gate; the staged arm adds source-only neutral reading. This is **not** a measurement of the production node-slot drafter or a fair historical-baseline/model-capacity ceiling. Formal budget 3,072, reading budget 512, temperature 0, seed omitted, requested low reasoning. JSON-object mode; declared fields are compiler-validated. Requests are sequential, retried with bounded exponential jitter and Retry-After, and cached by model/prompt/schema/settings. Native strict schema is prepared for the closed-link arm, which has not been run against hosted models.

GPT-OSS used 191,104 successfully reported tokens before the precommitted 190,000 safety budget stopped the next stage. This is not proof that all 200,000 provider tokens are exhausted. Qwen used 37,802 reported tokens and stopped after three exhausted HTTP-429 cycles (T01 staged, M07 monolithic, M02 monolithic), despite retries and output-aware pacing. Its last sanitized diagnostics showed Limit 1,000 / Requested 2,080; the limiting dimension was not retained. The discrepancy with the nominal 8,000 TPM is unresolved; project-level limits were requested. Do not keep retrying without a changed condition.

[Raw GPT results](../reports/free-gpt-oss.json), [raw Qwen results](../reports/free-qwen.json), and [authoritative revalidation/grades](../reports/free-drafting-scored.json). The last file includes every planned obligation, frozen reading next to the draft, terminal stage, field mismatch proxy, API/budget gaps and paired proposals. No frozen interpretations were placed in model prompts. API failures are excluded from semantic denominators. A temporary UTF-8 cue-file editing error was caught by tests and corrected; every saved output was revalidated through the final gates without regeneration.

### Exact field agreement before validation

These are exact frozen-field agreement counts, not independent semantic accuracy. Subject labels sometimes accept only the full frozen clause, undercrediting correct noun phrases; shorter valid citations can also fail exact annotation agreement. Expression field extraction requires parseable structure. Separate lexical diagnostics below do not require expression parsing but cannot prove ownership, associations or scope.

| Model / arm | Subject | Fact | Operator | Value | Unit | Applicability | Span |
| --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-oss-120b / decomposed | 0/33 | 1/31 | 1/30 | 0/21 | 1/21 | 0/2 | 24/33 |
| openai/gpt-oss-120b / monolithic | 0/34 | 0/32 | 1/31 | 2/22 | 2/22 | 0/3 | 26/34 |
| qwen/qwen3.8-27b / decomposed | 1/4 | 1/4 | 1/4 | 2/4 | 1/4 | 0/1 | 1/4 |
| qwen/qwen3.8-27b / monolithic | 0/4 | 1/4 | 1/4 | 1/4 | 1/4 | 0/1 | 2/4 |

### Raw lexical diagnostics, independently of expression parsing

Counts are exact sets of mentioned fact names, numerical values and comparison symbols on eligible lexable outputs. They are not binding accuracy or whole-rule correctness.

| Model / arm | Fact names | Numeric values | Comparators |
| --- | --- | --- | --- |
| openai/gpt-oss-120b / decomposed | 5/28 | 7/19 | 7/20 |
| openai/gpt-oss-120b / monolithic | 6/26 | 8/19 | 6/20 |
| qwen/qwen3.8-27b / decomposed | 3/4 | 2/4 | 2/4 |
| qwen/qwen3.8-27b / monolithic | 3/4 | 3/4 | 3/4 |

### Interpretation and transport findings

GPT-OSS completed 67 draft JSON objects: 49 rejected at expression parsing, six at source/subject grounding, ten at entity binding, one at schema/compilation, and one retained. M08 is a frozen-fixture predicate match (`two_way == true` versus the reference boolean fact), under its pre-assumed scope. It is not evidence of general quantified door interpretation. No retained nonmatches remain unadjudicated in this run. Wrong approvable / approvable is 0/1 for that staged sample; other arms have undefined 0/0 ratios. This tiny accepted sample does not establish precision.

GPT: 0/100 non-200 HTTP responses, all ten batches of ten had 0/10 errors. Qwen: 19/31 non-200 responses (17 HTTP 429, two HTTP 400); chronological batches had 6/10, 5/10, 7/10 and 1/1 non-200 responses. These include reading calls and retries. The two request rejections and final availability failure are not semantic errors. No claim is made that provider limits, model capacity or full interpretation accuracy have been isolated.

On four common completed obligations per arm, each single-model gate already retained 0/4; the agreement gate also produced 0/4 candidates and 4/4 abstentions per arm, with 42/46 paired obligations still pending per arm. Wrong-candidate rate is undefined 0/0, not a safety result. Agreement adds no measured protection or coverage on this subset. Both proposals remain visible. Actual reviewer edits/time were not observed; per-clause edit-family mismatches are only a proxy.

### Deterministic extraction, trained drawing and assisted slice

[Source-locked extraction](../reports/deterministic-quantities.json) processed 46/46 development clauses and matched 25/44 typed numeric literals in the frozen requirement trees. This denominator includes structural literals and excludes metadata bounds, so it is not whole-rule accuracy. Comparators, unit/header evidence and all unmatched quantities are recorded. Closed-link choices cannot invent numeric values or units; missing binding or complex composition yields review. This bounded arm handles simple numeric conjunctions, not general table applicability, exceptions, route logic or qualitative requirements. Its hosted comparison is unmeasured.

Trained perception used original local weights. [Reference labels](../reports/chief-a7-perception-labels.json) were frozen at `b35a2b56` before inference. The first vector run failed on an 895-MiB allocation for roughly 58 million neighbour pairs. The batch fix preserves all pre-change fixture features exactly at batch sizes 1, 2 and 128; no thresholds or weights changed. The rerun completes. [Vector results](../reports/trained-a7-vector.json): one raw room region, 0/17 reference-label point matches, 0/4 classified bedrooms, no detected doors/windows and 0/2 schedules. [Raster results](../reports/trained-a7-raster.json): U-Net at 150 dpi with automatically extracted native PDF text (no OCR or LLM labels), four raw regions, 3/17 point matches, 0/4 classified bedrooms, 25 door and 19 window candidates, 4/6 annotated-opening box overlaps, 0/2 schedules. Point containment is not polygon-IoU recall; merged/misclassified regions may cover points. The six-opening subset cannot establish global precision/recall. Some schedule graphics became garage regions. A nominal detail-scale factor and a rendering-only scale disclaimer were applied to the plan: end-to-end failure cannot be attributed to model weights alone. Per-view scale/region grounding needs a separate controlled measurement, not threshold tuning. No general segmentation regression conclusion follows.

[The new five-check slice](../reports/plan-answerable-results.json) is explicitly an author-written project brief with manually authored rule meanings, not an official regulation or a held-out test. Native detections are matched to declared labels/tags where possible; none supplies trusted bedroom evidence. The author supplies two room identities, rectangular interpretations of printed internal dimensions and two corridor connections. Only these selected collections are marked complete after author attestation. Whole-building, stair and final-exit inventories remain incomplete. The source, labels, scope, rule meanings and facts are data, not clause-specific engine branches. The author’s geometry assumptions and attestations have no independent review; they must not be presented as independently measured real-plan truth.

Area, filtered path to HALL and conditional area/width checks pass after author evidence: 3/5, versus 0/5 automatically. Net clear door opening and confirmed final-exit count remain unresolved; nominal `3076` is never substituted for clear width, and an upper-floor sheet cannot establish ground-level exits. These are changes in supplied evidence under a new authored profile, not a paired accuracy improvement over the old egress demonstration. No false-pass or violation-precision estimate exists: there are zero labelled violations and zero confirmed violations. Counterfactual tests from the same fixture exercise incomplete scope, unverified area, an unknown room on the only route, nominal versus clear size and missing final-exit coverage. Wrong trusted attestations themselves are not detected by this policy.

### Reproduction and remaining work

```powershell
# GPT: resume on a new quota day, using the same report and cache
.venv/Scripts/python.exe scripts/free_drafting.py <accessibility-source-text> reports/free-gpt-oss.json --model openai/gpt-oss-120b
# Qwen: only after project limits/availability change
.venv/Scripts/python.exe scripts/free_drafting.py <accessibility-source-text> reports/free-qwen.json --model qwen/qwen3.8-27b
# Closed numeric-link arm: only when its shared model budget is available
.venv/Scripts/python.exe scripts/free_drafting.py <accessibility-source-text> reports/free-det-gpt.json --model openai/gpt-oss-120b --arms deterministic --protocol reports/free-deterministic-protocol.json
.venv/Scripts/python.exe scripts/trained_drawing.py data/real_plans/recovery/modern-bungalow.pdf runs/trained-a7-raster --mode raster
.venv/Scripts/python.exe scripts/plan_answerable_slice.py data/real_plans/recovery/modern-bungalow.pdf runs/trained-a7-raster/building.json runs/plan-answerable
```

The source PDF remains local/ignored and comes from the [first-party Chief Architect sample](https://cloud.chiefarchitect.com/1/samples/projects/modern-bungalow/modern-bungalow.pdf), July 2024. No drawings were sent to hosted models. Do not run the fourth document until all requested development comparisons finish and one pipeline is chosen before looking at it. Its source/label blobs remain unchanged against `ad7742ce`; no tests reference or run it. Final non-slow validation: 1,104 passed, two skipped, 45 slow tests excluded, 255.37 seconds. Slow raster/dataset tests were not rerun.


## 19 November 2026: cached GPT continuation

The same model, settings, contract and cached worker resumed; no new capabilities or fourth-document runs were added. GPT completed 89/92 formal drafts: monolithic 45/46, staged 44/46. Only the same M08 staged draft remains retained and matches the frozen predicate: 1/44 staged, 0/45 monolithic. Wrong approvable / approvable remains 0/1 staged, undefined 0/0 monolithic; this is not a precision estimate on a useful accepted sample. Final gates reject 69/89 at expression parsing, 6/89 at subject/source grounding, 10/89 at entity binding, 2/89 at schema/compilation and 1/89 at declaration validation; 1/89 retained. The 22 additional JSON outputs did not add a retained rule.

The next request was rejected for daily tokens: provider-reported limit 200,000, used 198,896, requested 2,840. Reported successful usage in this worker was 63,223 tokens on 19 November and 191,104 on 18 November. These are UTC bookkeeping totals, not the provider rolling-window usage. Changing the calendar date does not guarantee quota recovery. No further exhausted-daily-budget retry was attempted. Cumulative HTTP attempts: 134/135 successful, 1/135 HTTP 429; the first thirteen batches had 0/10 errors, the final partial batch 1/5. Three formal drafts remain (T14 staged and both T15 arms). API unavailability is excluded from semantic grades. Qwen remains paused pending project-limit clarification.

Updated exact slot agreement (counts/eligible outputs):

| GPT arm | Subject | Fact | Operator | Value | Unit | Applicability | Span |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Monolithic | 0/45 | 0/43 | 1/42 | 2/33 | 2/33 | 0/14 | 32/45 |
| Staged | 0/44 | 1/42 | 1/41 | 0/32 | 1/32 | 0/13 | 29/44 |

These fields remain constrained by expression parseability and exact author annotations, not a fair direct slot-generation measurement. Raw lexical agreement, independent of expression parsing: monolithic fact names 14/37, numerical values 12/30, comparators 6/31; staged 16/39, 13/30, 9/31. They do not establish binding, applicability or whole-rule correctness. Qwen, paired agreement, deterministic extraction, perception and assisted-slice results are unchanged. The production typed-slot and closed-link hosted comparisons are still unrun. No accuracy improvement or general reliable interpretation is established.


## 19 November 2026: direct saved-draft audit and parse taxonomy

Hosted compact-expression generation is stopped. [Thirty assistant-adjudicated drafts](../reports/draft-adjudication-30.md), stratified across both arms and all three development families: 3/30 correct intended meanings, 16/30 partly correct, 11/30 wrong. These are NOT independently human-graded and not retained-rule accuracy. The user explicitly accepted assistant-only adjudication for now. On 95 eligible decisive slot judgments, the original exact scorer undercredited 73/95 and overcredited 0/95; revised scoring undercredits 26/95 and overcredits 0/95. Forty-three partial slot judgments and unannotated scope slots are excluded from this comparison. Subject alternatives are explicit review data; comparator reversal/negation and unit alias equivalence are tested. This is development resubstitution, not a held-out scorer evaluation. All saved GPT/Qwen outputs were rescored in [the audit replay](../reports/free-drafting-audited-scored.json); original scores/raw outputs remain unchanged.

Crucially M08 staged is a fixture-predicate match but omits the source applicability restriction. Thus 1/1 source-reviewed approvable drafts is incomplete; the earlier frozen-match-based 0/1 error count did not measure source-correctness. No fully source-correct retained rule was established. A01 frozen firm fact is not explicit in the supplied excerpt; A10 frozen true is an unsupported placeholder. Neither is silently relabelled or used as a correct automated interpretation.

[All 69 parse failures](../reports/expression-parse-audit.md) were directly categorized: naming/operator form 35/69, unsupported constructs 17/69, substantive semantic errors 17/69, outer wrappers/formatting 0/69. These are exclusive primary causes; naming errors can coexist with missing scope/units. Lossless surface replay changed 32/69 outputs, moved 5/69 beyond parsing, and retained 0/69 after full gates (four then fail subject grounding, one verifier). It never invents variables, fact synonyms, metadata, quantities, exceptions or scope. Every change has field before/after/operation logs. Production default gates remain unchanged. Twelve focused tests passed, including negative normalization and comparator/unit cases.


## Archived status before the direct audit (19 November)

# ReviewPulse — current status

19 November 2026. **The requested comparison is unfinished; no accuracy improvement
is established.** Local LLM generation is stopped. With the user’s approval,
Groq GPT-OSS-120B and Qwen3.8-27B replace unavailable Mistral/Meta-Llama arms.
Mistral’s current free mode excludes API access; no billing was enabled.
Keys come only from environment variables. Drawings remain local.

The hosted experiment uses a compact-expression research contract, shared by
both arms; it does not measure the production node-slot drafter. GPT-OSS resumed to 89/92 drafts, then hit the provider daily token limit. Qwen stopped after three exhausted
HTTP-429 cycles; project-level limit clarification is pending. API errors and
budget deferrals are excluded from semantic counts. Caches preserve completed
stages. The fourth document remains sealed and unrun.

## Headline results

| Model / arm | Complete JSON | Retained | Frozen match | Wrong approvable |
| --- | --- | --- | --- | --- |
| GPT-OSS / monolithic | 45/46 | 0/45 | 0/45 | undefined, 0/0 |
| GPT-OSS / staged | 44/46 | 1/44 | 1/44 | 0/1 |
| Qwen / monolithic | 4/46 | 0/4 | 0/4 | undefined, 0/0 |
| Qwen / staged | 4/46 | 0/4 | 0/4 | undefined, 0/0 |

“Frozen match” means normalized fixture IR under its assumed scope, not independent
legal interpretation. Of 89 GPT drafts, 69 fail expression parsing. Retention
requires deterministic checks and still needs human approval. Exact field
agreement, raw lexical diagnostics, per-obligation grades and HTTP-batch counts
are in the [scored report](../reports/free-drafting-scored.json) and
[history](results-history.md#18-november-2026-free-hosted-comparison-incomplete).
Subject/citation agreement can undercredit valid alternative phrases; raw
mentions do not prove correct binding or scope.

- **Deterministic extraction:** 46/46 clauses assessed; 25/44 typed reference
  numeric literals matched. Source quantities/operators are locked before closed
  catalogue choice. Complex composition requires review. Hosted comparison is
  **not run**, so this is not an interpretation-accuracy result.
- **Agreement gate:** 4/46 paired outputs per arm; 0/4 candidates and 4/4
  abstentions per arm. Both single-model validators also retain 0/4 on these
  same cases. Added benefit is unproven; false-candidate rate is undefined 0/0.
- **Trained perception, A-7:** both paths classify **0/4 bedrooms** and recover
  **0/2 schedules**. Raster gives 25 door/19 window candidates and 4/6 annotated-box
  overlaps; this partial annotation cannot establish global opening accuracy.
  Wrong view-scale/layout handling also contributes; this does not isolate model quality.
- **Assisted slice:** **0/5 automatic decisions; 3/5 after author evidence**.
  It uses an explicitly authored project brief and manual rule interpretations.
  Two rectangular room readings and corridor links are author-supplied; clear
  opening and ground-level exit coverage remain unresolved. This is not an
  automated regulation-to-drawing success. [Data](../reports/plan-answerable-results.json).

## Not measured / do not claim

Full 46-case comparisons, closed-link model quality, actual reviewer edits/time,
independent label correctness, held-out adaptation and general segmentation
regression remain unmeasured. Labels have no independent review. Historical
ledger attestations are synthetic; new author attestations are unverified
as-drawn interpretations. Finite capabilities, small samples and the provisional
25% scale bound remain limitations. Zero decisions or zero candidates do not
establish safety. Do not claim improved accuracy or promote an unmeasured arm.

Next: clarify Qwen project limits, resume the three remaining GPT drafts when the rolling allowance recovers, and
complete the same-case closed-link comparison before choosing a pipeline or
unsealing the fourth document. **1,104 tests passed; 2 skipped; 45 slow excluded.**
Reproduction commands and detailed failure analysis are in the history.


## 19 November: strict-slot and drawing continuation

Compact-expression hosting is stopped in the runner. Strict production SlotDraft and numeric closed-link hosting were attempted with the existing approved GPT-OSS model; no drawings were sent. Groq rejected overlapping scalar integer/number alternatives and duplicate string alternatives. Lossless strict-schema canonicalization removes redundant integer branches and merges string enum/pattern unions, preserving field names. There is no fallback to unconstrained output. The two separate diagnostic calls were sanitized before display; raw provider error bodies were not stored. Native strict output then succeeded. A per-report OS lock prevents concurrent resume workers, including after a process crash.

[Token estimate and side-by-side status](../reports/strict-focused-comparison.json): the focused 92-request plan is estimated at 156,649–313,373 input tokens, versus 179,343–358,774 without retrieval; full output caps add 153,088. These are UTF-8 byte heuristics, not model tokenizer measurements, and correspond to roughly two to three 200k-token windows at full caps. Actual first typed request: 3,231 prompt plus 1,295 completion tokens. Two completed closed requests used 1,397 tokens total. The new production arm completed 1/46, retained 0/1, assistant source-correct 0/1; the closed arm completed 2/46, retained 0/2, whole-source-correct 0/2. Its distance/fact choices are partly correct but the review flag is false despite unsupported scope. The deterministic quantity gate rejects both. Source comparison on T01 is possible across both new arms and archived expression arms; no arm ranking follows from one shared case. The next production call hit the rolling daily limit (200,000; used 197,049; requested 4,423). API rejections are not semantic failures. Full comparisons remain unfinished.

[Four-drawing results](../reports/native-label-study.md), using labels frozen at c1c452b3: native name matching 0/17, 4/14, 0/7, 4/5; bedrooms 0/4, 2/3, 0/1, 2/2. Native containment names existing regions and refuses conflicts; it cannot recover missing boundaries. The existing builder already used native labels. No trained room-type classifier exists; the original trained primitive classifier supplies geometry and unknown room types stay unknown. Selected opening box hits are partial annotations, not global detection accuracy. Three additional sources are public planning-CDN copies, not verified official council archives. Review scope selection was supplied by the author; no automatic view discovery or sealed-material tuning was claimed.

[Eight-rule demo scope](eight-rule-demo.md) selects 2021 IRC Chapter 3 and one thin-line metric bungalow style. It is NOT an executed source-to-LLM-to-approval walkthrough. The published-source chapter was indexed but its direct fetch returned 403; paraphrases in the scope file are planning notes, never substituted as original LLM input. No eight-rule edits, decisions or false-pass counts have been measured. This is separate from the older five-rule authored brief.


### Final validation for this round

Full non-slow suite: **1,126 passed, two skipped, 45 slow deselected, 259.54 seconds** using `python -m pytest`. An initial console-entry invocation failed collection because the repository root was missing from its import path; no tests were removed. Changed files pass Ruff and diff whitespace checks. The subsequent CLI-only default-arm correction was checked offline: it plans the protocol's 92 intended requests without a hosted call. No old drafting processes or scheduled jobs were found. Exact environment-secret values were absent from changed tracked files, without printing them. Fourth-document blobs remain unchanged from ad7742ce, with no model runs or test references. [Validation record](../reports/nov19-audit-validation.json). Slow tests and general segmentation regression remain unmeasured.


---

## Archived status before assisted table sprint, 19 November 2026

# ReviewPulse — current status

19 November 2026. **The scorer overstated failure, but reliable automatic
interpretation is still unproven.** Compact-expression hosting is stopped.
Typed-slot and closed-link requests now use strict JSON schema with focused
catalogue retrieval. The first production draft completed, then the daily
allowance blocked continuation. API failures are excluded from semantic counts.
Drawings stay local; keys come only from the environment. No billing was enabled.
The fourth document remains sealed; no final pipeline has been chosen.

## Measured

Thirty saved GPT drafts were directly **assistant-adjudicated**, with user
approval of that limitation: **3/30 correct intended meanings, 16/30 partial,
11/30 wrong**. None of the three correct intentions became retained rules.
The old scorer undercredits **73/95** eligible decisive slot judgments; revised
scoring undercredits **26/95**, with **0/95 overcredits**. Partial judgments and
unannotated scopes are excluded. This is development resubstitution, not a
held-out scorer validation. [Review table](../reports/draft-adjudication-30.md).

| Arm | Complete | Retained | Source correctness reviewed |
| --- | --- | --- | --- |
| Archived GPT expression, monolithic | 45/46 | 0/45 | 1/15 sampled intentions correct |
| Archived GPT expression, staged | 44/46 | 1/44 | 2/15 sampled intentions correct |
| Production typed slots, strict | 1/46 | 0/1 | 0/1 correct |
| Closed numeric linking, strict | 2/46 | 0/2 | 0/2 whole rules correct |

The sole retained expression is **incomplete against its source: 1/1 reviewed
approvable candidates**. Its fixture predicate match did not establish correct
scope. The former fixture-based 0/1 error count must not be used as precision.

All **69/69 parse failures** were categorized: naming/operator form **35/69**,
unsupported constructs **17/69**, semantic errors **17/69**, wrappers **0/69**.
Logged surface normalization moves **5/69** beyond parsing, retains **0/69**
after the remaining gates, and never invents scope or omitted constraints.

| Frozen drawing scope | Named space points | Bedrooms classified |
| --- | --- | --- |
| A-7 | 0/17 | 0/4 |
| Thin-line bungalow | 4/14 | 2/3 |
| Shaded-wall plan | 0/7 | 0/1 |
| Proposed conversion | 4/5 | 2/2 |

Native naming cannot repair missing enclosures. The existing builder already
used native labels; this pass adds conflict checks/provenance. Trained models
classify primitives, not room use. Opening annotations are partial; global
opening precision/recall is unmeasured. A-7 schedules remain **0/2**.

## Not measured

Full paired strict-arm comparison, independent human grading, actual reviewer
edit effort, whole-drawing completeness, general segmentation regression and
held-out adaptation. An [eight-rule single-code demo](eight-rule-demo.md) is
selected but **unrun**; original source text and quota-available drafting remain
blockers. Its edit, decision and false-pass counts are unknown, not zero.

## Do not claim

Improved interpretation accuracy, a winning architecture, reliable general
adaptation or safety from abstention. All labels lack independent review;
historical ledger attestations are synthetic. The older five-rule authored
brief achieved 0/5 automatic and 3/5 author-assisted decisions; it is not an
automated regulation-to-plan demonstration. Finite capabilities, small samples
and the provisional 25% scale bound remain limitations.

Next: finish the strict development comparison and record actual edits before
choosing a pipeline or unsealing the fourth document. Detailed evidence,
transport counts, tests and [archived runs](results-history.md) remain available.

Validation: **1,126 tests passed; two skipped; 45 slow excluded.**


## Assisted sprint validation, 19 November 2026

Non-slow suite: **1,151 passed, 2 skipped, 45 slow deselected**, 586.85 seconds.
Ruff on changed implementation/test files and `git diff --check` passed.
The old authored five-rule profile still returns 0/5 automatic and 3/5 assisted
decisions. The fourth-document files are unchanged against `ad7742ce` and were
not run through any model. Current environment API-key/token values were absent
from changed files; this is not a full-history secret audit.

[Validation record](../reports/assisted-sprint-validation.json).


---

## Archived status before assisted-product convergence

# ReviewPulse — current status

19 November 2026. **A narrow assisted table helper works; a general interpreter
has not been demonstrated.** Numeric values, units and applicability come from
source cells; four hosted closed-menu choices select fact names. On development
data it produces 12 correct thermal rules, but covers only 12/36 numeric
obligations. This fails our pre-registered 18/36 selection threshold. No pipeline
is selected; the fourth document remains sealed and unrun. Next: get independent
grades, then decide whether the narrow table scope is sufficient. Do not broaden
claims or tune the sealed test. Drawings stay local; no billing was enabled.

## Measured

| Development measurement | Result |
| --- | --- |
| Thermal full rules, assistant-source-reviewed | 12/15 correct, zero edits; 3/15 need context/unit |
| Thermal typed scope and quantity/comparator | 15/15 match frozen references |
| All numeric obligations, edit burden | 12/36 zero; 0/36 one; 21/36 rewrite; 3/36 missing context |
| Source-wrong/incomplete approvable table rules | 0/12, assistant review only |
| Four cached fact-choice calls | 4/4 complete; 2,030 total tokens; 0/4 HTTP errors |
| Old 30 drafts, estimated repair burden | 0/30 zero; 0/30 one; 19/30 two-plus; 11/30 rewrite |
| Raw relational declarations | 2/3 type-valid, 0/3 source-correct; 0/4 old wrong bindings automatically repaired |
| Independent teammate grades | 0/10 returned; agreement unmeasured |

Retrospective edit plans estimate executable-rule repairs, not observed human
effort: 3/30 old drafts had correct intent but still needed binding/formalization.
Fact declarations do not create values: all 3 manually corrected relational
measurements remain evidence requests, with 0/3 full clauses decided.
[Table review](../reports/assisted-numeric-review.md),
[edit rubric/results](../reports/assisted-edit-burden.json).

Exact polygonization covers **0/17, 0/14, 0/7 and 1/5** frozen real-PDF room
points; bedrooms **0/4, 0/3, 0/1 and 0/2**. It is not promoted over the existing
builder. Synthetic CAD control: **3/3** rooms, **2/2** bedrooms; no real DXF was
found. These are point hits, not region overlap or global opening recall.

The [eight-target actual assisted attempt](eight-rule-demo.md) completed **7/8**
text-only readings; **1/8** provider request rejection is excluded from semantic
failures. All **7/7** completed readings required full reviewer rewrites:
**0/8 automatic decisions, 2/8 scenario-assisted decisions, 5/8 validation
needs-review, 1/8 unavailable**. Validation exposes rounded unit equivalents,
missing entity-owned facts and angle protocol coverage. The two decisions use
an assistant-designated entrance scenario; they do not establish legal egress
compliance. With **0 gold violations**, false-pass rate **0/0** and violation
precision **0/0** are undefined. This demonstrates assisted execution only.

## Not measured

Independent human correctness/edit time, a completed paired general drafting
comparison, real Moroccan CAD transfer, whole-building inventory completeness,
general perception regression, and held-out adaptation. A blinded 10-draft CSV
is ready; agreement waits for its return. See [selection decision](assisted-pipeline-choice.md).

## Do not claim

General automated regulation interpretation, improved held-out accuracy,
zero false passes from an empty violation sample, or safety from abstention.
Labels lack independent review; historical ledger attestations are synthetic.
Capabilities are finite; test sets are small; the 25% scale bound is provisional.
Detailed budgets, negative results and prior runs are in
[history](results-history.md), [token budget](assisted-token-budget.md), and
[polygonize report](../reports/polygonize-study.md).

Validation: **1,151 passed, 2 skipped; 45 slow excluded**. Changed-file Ruff and
whitespace checks passed. [Details](../reports/assisted-sprint-validation.json).


## Assisted-product convergence validation

Non-slow suite: **1,177 passed, 2 skipped, 45 slow excluded**, 306.12 seconds.
Three additional CSV grade-normalization cases passed afterward; all eight
targeted grading/reviewer tests passed. Changed Python files pass Ruff, app
JavaScript passes syntax checking. No complete browser interaction test or real
teammate effort is claimed. Runtime code remains at the held-out freeze.

[Validation record](../reports/assisted-product-validation.json).


Post-run integration audit found Inputs upload still invoked the archived drafter.
The new assisted upload endpoint stores and splits source without constructing
a client; UI uploads and retry buttons use assisted routes. Seventeen targeted
app/grading tests and JavaScript syntax checks pass afterward. The inference
core and held-out runner remain unchanged; the fourth document was not rerun.
