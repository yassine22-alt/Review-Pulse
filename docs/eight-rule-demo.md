# Eight-rule assisted run — 19 November 2026

The frozen source/scenario is `reports/eight-rule-assisted-profile.json`, committed
as `ed02b2ed` before generation. Original indexed publisher text is from the
2021 IRC, Chapter 3, first printing. Direct publisher fetch returned HTTP 403;
indexed publisher sections supplied the passages. The UK PL101 H drawing is an
illustration: there is no claim that this code governs that property.

## Reproduce locally

```powershell
.venv/Scripts/python.exe scripts/demo_semantic_drafts.py reports/eight-rule-assisted-profile.json reports/eight-rule-semantic-drafts.json
.venv/Scripts/python.exe scripts/plan_answerable_slice.py data/real_plans/label-study/uk-proposed.pdf runs/native-label-study/uk-proposed/building.json runs/eight-rule-assisted --profile reports/eight-rule-assisted-profile.json --drafts reports/eight-rule-semantic-drafts.json
```

The first command resumes cached text-only GPT-OSS-120B requests. It may retry
previously rejected requests and therefore will not reproduce the exact archived
attempt count; use the saved drafts for the frozen run. Drawings never leave the
machine. The second command uses the trained pipeline's saved building model,
not vector-only synthetic plan facts. Open `runs/eight-rule-assisted/report.html`
and expand each evidence/trace section.

## Actual run

Eight attempted obligations: **7/8 complete neutral semantic readings**, **1/8
HTTP 400 schema/request rejection**. The latter is transport/request failure,
not a semantic grade. The pre-run estimate was 3,466–6,938 input plus a
6,144-token output cap, against the supplied 200,000 tokens/day and 8,000
tokens/minute allowance; requests were paced and cached. Completed calls consumed **3,548 input + 3,634 output =
7,182 tokens**; usage for the rejected call is unavailable.

All **7/7 completed drafts required a full reviewer-authored executable rewrite**.
This is an assisted reading plus formalization workflow, not a completed typed
LLM compiler. These are assistant actions, not independently observed human
edit effort. See the before/after frames in `eight-rule-assisted-findings.json`.

| Target | Final stage | Outcome |
| --- | --- | --- |
| R304.1 eligible area, kitchen exception | validation / entity binding | needs review |
| R304.2 horizontal dimension, kitchen exception | validation / entity binding | needs review |
| R311.1 continuous route, garage exclusion, public discharge | request rejected | unavailable |
| R311.2 minimum egress-door count | checked | satisfied in reviewer scenario |
| R311.2 side-hinged operation | checked | satisfied in reviewer scenario |
| R311.2 face-to-stop width at 90 degrees | validation / entity binding | needs review |
| R311.2 threshold-to-stop clear height | validation / entity binding | needs review |
| R311.6 hallway width | validation / entity binding | needs review |

The five validation failures include missing entity-owned fact declarations and
rounded imperial/metric equivalents; the width also includes uncovered angle
protocol quantities. Exact diagnostics remain in the report. No validators were
bypassed to obtain decisions. **0/8 automatic decisions; 2/8 after scenario
attestation; 5/8 validation needs review; 1/8 API request unavailable.**

Automatic facts come from `from_building` on the saved trained extraction output.
The model's detected inventory is never certified complete. The assistant
visually read the bottom entrance swing and native room labels, and explicitly
designated that door for the hypothetical scenario. Only that designated set is
complete. No clear dimensions, usable area, all-level traversal or public-way
connection were supplied. Nominal dimensions are never treated as clear opening.
The drawing itself says dimensions are approximate and subject to site survey.

Two scenario-labelled passes match 2/2 scenario expectations; this is **not**
regulatory accuracy. There are **0 gold violations**, so false passes **0/0**
and violation precision **0/0** are undefined. R311.2 is decomposed into atomic
obligations; passing count/hinge does not pass that section or establish egress
compliance. All references lack independent review.

The old authored five-rule profile still reproduces **0/5 automatic, 3/5 assisted**.
The new run is deliberately reported separately.
