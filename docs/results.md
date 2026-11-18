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
are excluded. Next: finish and grade that cohort, inspect the paired hosted
pilot, then diagnose zero thermal retention if both five-case arms complete
without retaining a rule. Do not run the fourth document.

## Measured

| Measurement | Counts and scope |
| --- | --- |
| Gold-slot oracle, active catalogue | Exact and behavioral matches 5/46; binding rejected 22/46, verifier rejected 17/46, context unresolved 2/46 |
| Gold-slot oracle, permissive author additions | Exact and behavioral matches 17/46; verifier rejected 27/46, context unresolved 2/46. This mode also adds missing collections and is not the production policy |
| Gold-slot oracle, validated declarations | Retained 13/46; exact trees 13/13 retained; behavioral matches 13/13 retained. Rejections: verifier 23/46, entity binding 8/46, context 2/46, unit vocabulary 0/46 |
| Oracle behavior test scope | 64 generated complete-value worlds per retained frame; declaration provenance stripped for logical comparison only; matching evaluation errors receive no credit |
| Historical local 24-case baseline | Retained 0/24; generation cap 21/24; absent source subject 3/24 |
| Cap diagnosis | Historical raw responses available 0/21. New instrumented replays completed 21/21: repeated node records/IDs 20/21; repeated prose during repair 1/21. Some diagnostic replays stop loops early |
| Prompt-only wire fix | Superseded partial run, not a 24-case result. Repeated output and a transport timeout remained; no accuracy improvement established |
| Hosted pilot, frozen pre-declaration pipelines | Semantic completion 1/12 pilot cases per arm, 1/5 thermal per arm. Retention 0/1 per arm; matches/partly matches/wrong each 0/0 retained candidates, undefined |
| Hosted pilot approvability | Wrong approvable / approvable = 0/0 in each arm, undefined; no final program existed to grade |
| Hosted pilot transport | HTTP failures 10/18 attempts overall, 5/9 per arm; all 10 were HTTP 503. Per-batch denominators are retained in the pilot snapshot; no API-unavailable row is counted as a semantic failure |
| Declaration and compatibility checks | Earlier declaration/runtime/interpreter checks 80/80 passed; focused current drafting/declaration/fallback tests 40/40 passed; isolated cap-only schema tests 12/12 passed |
| Broad suite, first run | 1,012 passed, 2 skipped, 1 failed, 45 slow tests excluded. Fallback compatibility failure corrected; focused 40/40 passed afterwards. Fresh broad rerun pending |
| Worker checks | 23/23 targeted transport, quota, continuation and phase-order tests passed at the pilot checkpoint |
| Fourth document freeze | RPS 2000 version 2011; official French Bulletin Officiel 6206, 21 November 2013; 17 obligations and 48 synthetic scenarios committed at `41b1ad14b466fb52500b118d69593319da649e23`; model/checker runs 0/17 |

Per-obligation and per-stage evidence:

- [Hosted pilot snapshot](../reports/hosted-stratified-pilot-snapshot.json): frozen reading, retained candidate or explicit absence, terminal stage, diagnostics and batch request counts for all 12 selected obligations in both arms.
- [Gold-slot declaration oracle](../reports/slot-oracle-declarations.json): all 46 cases across the three catalogue modes.
- [Reviewed replay diagnosis](../reports/local-cap-reviewed-diagnosis.json): all 21 cap cases and local raw trace paths. Raw responses remain local.
- [Cap-only protocol](../reports/local-cap-protocol.json): unchanged model settings, isolated source fingerprint and reproducible patch. Live local results are `reports/local-schema-after-24.json`.
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
