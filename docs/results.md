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
