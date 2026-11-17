# ReviewPulse verification results

## Measured

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

### Third document and execution ceiling

The sole held-out source is Morocco's Decree 2-13-874, thermal annex, printed
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

Whole-document extraction, discovery of table applicability, drawing extraction
accuracy, other model settings, reviewer disagreement,
and coverage on real projects remain unmeasured. The samples are small.
The benchmark author wrote the labels and rated drafts without independent
review. The historical excerpt scan found zero matching excerpts in tracked
prompt, fixture or development files outside the holdout artifacts. It
does not rule out paraphrases or pretraining exposure.

## Do not claim

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
