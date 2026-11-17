# ReviewPulse verification results

## Measured

### Automated interpretation and transfer

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

The holdout uses 16 separately scored obligations from Morocco's Decree 2-14-499
across two independently specified synthetic ground-floor plans. Separately scored
obligations can share a numbered provision. All 32 clause–plan pairs are applicable
under the published fixture assumptions. The [manual labels](../reports/morocco-holdout-labels.json)
were frozen in commit `2a60396` before checker execution. The baseline is
`bc6f7892`, the remote tip before merging the count upgrade. The source is the
[published French Bulletin Officiel annex](https://aute.gov.ma/s/a/library/2023-11-01/0a4d2c47-5b19-4b4f-858f-67f605534364.pdf).
No use of this decree was found in the checked-in development corpus.

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

## Not measured

Whole-document extraction, source-reference discovery, drawing extraction
accuracy, a complete 7B run, other model settings, reviewer disagreement,
and coverage on real projects remain unmeasured. The samples are small.
The benchmark author wrote the labels and rated drafts without independent
review. The explicit leakage scan found zero matching excerpts in tracked
prompt, fixture or development files outside the holdout artifacts. It
does not rule out paraphrases or pretraining exposure.

## Do not claim

Zero false passes with zero decisions is abstention. It does not establish
safety, precision, useful zero-code transfer, or statutory compliance.
The earlier two-decision gain applies only to manually interpreted rules
on the frozen fact fixtures. The provisional scale bound and the finite
checker capability set remain documented limitations.

The largest named gaps tie at three obligations apiece across the two
documents: door glazing and operation evidence (M12, M13, M16), and adapted
equipment and seating schedules (A07–A09). If we next pilot one capability,
choose **reviewed door glazing and operation evidence**. The existing opening
inventory gives a place to attach it. Three is the number of directly
addressed clauses, not a measured coverage gain. Test with independently
labelled glazing, sliders and release hardware, including a missing field,
a conflicting schedule, an ambiguous tag, and an inapplicable door. Run both
frozen documents again with the same drafting configuration. Count a gain
only when a correct draft reaches a correct new decision and false passes
do not increase. No new capability was built for this evaluation.
