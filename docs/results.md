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
