# Review-Pulse results and current status

Updated 17 November 2026. The 46 fire-safety, accessibility and thermal
obligations are DEVELOPMENT data. They cannot support a held-out claim.

The current priority is measuring drafting rather than adding checking
capabilities. The offline redesign makes triage advisory and compiles typed,
schema-constrained model slots into the existing rule language. Drafts still
need source, type, unit and coverage validation and human approval. No new
plan computation or checking family has been added.

The negative oracle result matters: only **5/46** author-translated gold slot
inputs survive with the existing catalogue. With author-proposed declarations,
**17/46** survive; **27/46** still stop at verification and **2/46** remain
unresolved for context or specialist meaning. This does not measure an LLM.
Removing expression syntax alone does not solve grounding or applicability.

Hosted comparison is pending. The user reports rotating the exposed key and
placing its replacement in Codex Cloud Personal Vault. This local Windows
process cannot read GEMINI_API_KEY. It has made **0/0** replacement-key HTTP
attempts and completed **0/46** hosted semantic evaluations. Availability
failures are excluded from semantic failure counts.

The fourth document is frozen and unrun: RPS 2000 version 2011, official French
Bulletin Officiel 6206, 21 November 2013. Its **17 obligations and 48 synthetic
scenarios** were committed at `41b1ad14b466fb52500b118d69593319da649e23`.
Interpretations and applicability labels remain separate from drafting input.

Next: finish the paired local comparison, make the replacement credential
available to this process, then run original and redesigned hosted drafting on
the same 46 development obligations. Only then run the frozen fourth document
once, without further tuning. Inspect wrong approvable drafts separately from
retention. Do not add checker capabilities to improve these numbers.

Local comparison checkpoint before the requested restart: **20/46** redesigned
obligations have completed, with **0/20** retained. Terminal stages are
generation cap **17/20** and absent source subject **3/20**. Request failures
were **0/60** in the five completed batches (12 calls per batch, 0/12 errors
each). This is an incomplete, negative result, not evidence of accuracy or
improvement. The remaining **26/46** are pending in the saved snapshot.
See [partial local trace](../reports/local-after-slots-partial.json).

## Measured

| Measurement | Result and scope |
| --- | --- |
| Gold-slot compiler, active catalogue | 5/46 exact reference trees and generated behavioral matches; 22/46 binding rejection; 17/46 verifier rejection; 2/46 context/binding unresolved |
| Gold-slot compiler, author-proposed facts | 17/46 exact and behavioral matches; 27/46 verifier rejection; 2/46 context/binding unresolved. Proposed facts do not create plan computations |
| Original local drafting, Qwen2.5 1.5B | 45/46 evaluated, 1/46 transport timeout. 1/45 semantic cases retained; that draft was wrong. Wrong technically approvable / approvable = 1/1 with a synthetic issue-free review, not a real critic |
| Generated behavior | 64 fact worlds per retained oracle input; finite tests, not a proof |
| New credential visibility | Absent from local process, Windows user and machine environment; value never printed |
| Current non-slow suite | 978 passed, 2 skipped, 45 slow tests deselected; 530.44 seconds. Redesign pushed at e2d0acf4516d5e3395869f4f470108b0111e1053 |
| Secrets scan | 597 working text files; 776 reachable Git blobs, 286 trees, 37 commits, including refs/reflogs; no credential-pattern match in scanned repository content. Exclusions and access failures are documented |
| Previous complete slow suite | 45/45 passed at the earlier checkpoint; this is historical validation, not a new interpreter result |
| Previous segmentation regression | 0/262,144 changed class pixels on one prepared synthetic plan; unchanged source/checkpoint, not real-plan accuracy |

Per-obligation oracle diagnostics are in
[slot-oracle-results.json](../reports/slot-oracle-results.json).
[Structured drafting](structured-drafting.md) describes checks and limits.
[Secrets audit](secrets-audit.md) states scan exclusions and the chat exposure.
[Hosted runner](resilient-hosted-runner.md) describes retries, cache, circuit
limits and provider setup. [Fourth-document freeze](fourth-document-freeze.md)
records the official edition and source checksum.

## Not measured

- A completed hosted original-versus-redesigned semantic comparison, or the
  gap between a hosted frontier model and the local models.
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
