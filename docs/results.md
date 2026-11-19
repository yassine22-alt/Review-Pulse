# ReviewPulse — assisted product status

19 November 2026. **The product is an assisted numeric drafter and expert
formalization workspace, not a general interpreter.** The app now routes the
Requirements review through the narrow scope gate and closed fact-name menu.
A reviewer can edit numeric fields or formalize a queued clause, validate, then
approve separately. Timed sessions retain diffs, pauses and failed attempts.
Real teammate effort is not yet measured: collect 10–15 completed sessions,
split between drafts and the rewrite queue, then report edits and seconds.

## Measured

| Same numeric development obligations | Before | After |
| --- | --- | --- |
| Fully correct, zero edits | 12/36 | 12/36 |
| One edit | 0/36 | 0/36 |
| More local edits | 0/36 | 0/36 |
| Rewrite/formalization | 21/36 | 21/36 |
| Missing context | 3/36 | 3/36 |

**No executable-coverage improvement.** Thermal rows remain 12/15 correct;
15/15 preserve typed scope and numeric values. Prose parsing passes synthetic
French/English comparator tests, but the real clauses need unsupported
composition or absent catalogue facts. The existing four real fact-name choices
are reused; no new hosted calls. Source-wrong approvable table rules: **0/12**,
assistant review only. These use a fixture catalogue, not thermal facts perceived
from the demo drawing. Full [development results](assisted-product-evaluation.md).

Scope routing: **28/28** labelled out-of-scope clauses queued, **0/28** wrongly
drafted; **12/18** labelled in-scope reached a draft and **6/18** queued.
Diagnostic family names match author labels on **27/46**; this is conservative
routing, not general semantic understanding.

Fourth document: RPS 2000 version 2011, BO 6206 (21 November 2013).
Criteria committed `de33375f`; code frozen `53ea799a`; scope annotation `d1469b61`.
One run: **0/1** in-scope reached <=1 edit (failed); source-wrong approvable
**0/0** (unmeasured, sample requirement not met); **16/16** out-of-scope queued
(met on author labels). **17/17 queued, 0 drafts, 0 model calls.** The simple
joint-width clause is blocked by parent scope/catalogue grounding. Model accuracy
was not exercised. The fourth document is now opened/run once; no tuning or
second inference run. [Full result](assisted-product-fourth-results.md).

## Not measured

Real reviewer edits/time, independent correctness/agreement, a successful
in-scope held-out drafting comparison, real CAD transfer, whole-building inventory
completeness and general perception regression. The blinded CSV includes column
rubrics; **0/10** teammate grades returned. The old eight-target attempt remains
partial and is not a successful automatic regulation-to-plan demonstration.

## Do not claim

A general interpreter, improved held-out accuracy, correctness from zero
candidates, or safety from abstention. All labels lack independent review;
historical ledger attestations are synthetic. Samples are small, capabilities
finite and the 25% scale bound provisional. The expert queue is not a finished
nontechnical rule builder. [Product](assisted-product.md),
[review protocol](assisted-review-workflow.md), [five-minute script](assisted-demo-5min.md).

Validation: **1,177 passed, 2 skipped; 45 slow excluded** before the final upload
integration fix; **17 targeted app/grading tests passed afterward**. Changed Python files
pass Ruff; app JavaScript passes syntax checking. API tests exercise timed edits,
stale drafts and approval; no teammate session or full browser test is claimed.
