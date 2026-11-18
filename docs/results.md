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

Next: complete the paired local run and the remaining **44/46** hosted
obligations per arm, using daily free-quota resets or a higher-quota project.
Do not pool different models. Only afterward should the frozen fourth document
run once. No checker capabilities were added. The observed unit-vocabulary
generation gap is documented, without a claim that fixing it unlocks checks.

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
