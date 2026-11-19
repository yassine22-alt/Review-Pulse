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
