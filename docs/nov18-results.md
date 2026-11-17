# 18 November verification results

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

**Measured:** controlled execution with manually authored interpretations,
existing predicates and frozen plan facts. The two extra automatic results
were correct and did not add false passes on these cases.
**Unmeasured:** automated parsing of the decree, drawing extraction accuracy,
independent expert agreement, and coverage on another document or real project.
The ground truth was written separately from the checker by the benchmark author,
with no independent professional review. Do not claim statutory approval,
general accuracy improvement or automatic checking of the whole decree.
