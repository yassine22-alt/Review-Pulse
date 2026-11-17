# Per-obligation measured results

M01–M16 and A01–A15 are development data. No candidate program survived in any run. A missing draft is not a correct interpretation. The 7B M15 candidate was discarded by the semantic verifier and never approvable. Eight timeouts make this 7B run inconclusive as a semantic capacity ceiling.

| ID | 1.5B original stage | 1.5B revised stage | 7B original stage | Retained / matches / partial / wrong retained |
|---|---|---|---|---|
| M01 | triage | source-span grounding | timeout | 0 / 0 / 0 / 0 |
| M02 | triage | source-span grounding | timeout | 0 / 0 / 0 / 0 |
| M03 | expression parse | expression parse | timeout | 0 / 0 / 0 / 0 |
| M04 | generation cap | generation cap | timeout | 0 / 0 / 0 / 0 |
| M05 | source-span grounding | source-span grounding | timeout | 0 / 0 / 0 / 0 |
| M06 | expression parse | expression parse | timeout | 0 / 0 / 0 / 0 |
| M07 | fact ownership | fact ownership | timeout | 0 / 0 / 0 / 0 |
| M08 | triage | triage | timeout | 0 / 0 / 0 / 0 |
| M09 | triage | triage | triage | 0 / 0 / 0 / 0 |
| M10 | triage | triage | triage | 0 / 0 / 0 / 0 |
| M11 | triage | triage | triage | 0 / 0 / 0 / 0 |
| M12 | triage | triage | triage | 0 / 0 / 0 / 0 |
| M13 | triage | triage | triage | 0 / 0 / 0 / 0 |
| M14 | triage | triage | triage | 0 / 0 / 0 / 0 |
| M15 | triage | triage | verifier | 0 / 0 / 0 / 0 |
| M16 | triage | triage | triage | 0 / 0 / 0 / 0 |
| A01 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A02 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A03 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A04 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A05 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A06 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A07 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A08 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A09 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A10 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A11 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A12 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A13 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A14 | triage | triage | not run | 0 / 0 / 0 / 0 |
| A15 | triage | triage | not run | 0 / 0 / 0 / 0 |

Wrong approvable / approvable is 0/0, undefined, for all three runs. The revised 1.5B pipeline retains 0/31 development obligations. The unchanged 7B pipeline retains 0/16 fire obligations. There is no measured draft improvement.

## Sole held-out document

Labels were committed before running. Production code and the harness stayed unchanged after the first thermal model call. Selection comprises 15 adjacent numeric cells across three residential table rows. All cells apply to their pre-scoped synthetic building. The author transcribed the source manually. Whole-document parsing and row selection are outside this experiment. The declared thermal catalogue is new data. No production function or prompt gained a thermal special case.

All drafted rules are unresolved with an interpretation blocker. False passes are 0/8 actual violated cases. Confirmed-violation precision is undefined, 0/0. The manual-rule ceiling has 15/15 executable obligations, 6/15 initial decisions and 13/15 with reviewer evidence.

| ID | Frozen scoped interpretation | Ground truth | Draft stage | Correct draft | Automatic / reviewed draft | Ceiling initial / reviewed | Ceiling blocker after review |
|---|---|---|---|---|---|---|---|
| T01 | roof_u le 0.65 W/m2/K | SATISFIED | expression parse | No | UNRESOLVED / UNRESOLVED | SATISFIED / SATISFIED | none |
| T02 | wall_u le 0.7 W/m2/K | VIOLATED | expression parse | No | UNRESOLVED / UNRESOLVED | VIOLATED / VIOLATED | none |
| T03 | window_u le 2.6 W/m2/K | SATISFIED | expression parse | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / SATISFIED | none |
| T04 | slab_r ge 0.75 m2*K/W | VIOLATED | source-span grounding | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / VIOLATED | none |
| T05 | solar le 0.5 1 | SATISFIED | source-span grounding | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / SATISFIED | none |
| T06 | roof_u le 0.55 W/m2/K | VIOLATED | source-span grounding | No | UNRESOLVED / UNRESOLVED | VIOLATED / VIOLATED | none |
| T07 | wall_u le 0.6 W/m2/K | SATISFIED | expression parse | No | UNRESOLVED / UNRESOLVED | SATISFIED / SATISFIED | none |
| T08 | window_u le 2.6 W/m2/K | VIOLATED | source-span grounding | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / VIOLATED | none |
| T09 | slab_r ge 1.25 m2*K/W | SATISFIED | source-span grounding | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / SATISFIED | none |
| T10 | solar le 0.6 1 | VIOLATED | source-span grounding | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / UNRESOLVED | missing evidence |
| T11 | roof_u le 0.55 W/m2/K | SATISFIED | expression parse | No | UNRESOLVED / UNRESOLVED | SATISFIED / SATISFIED | none |
| T12 | wall_u le 0.6 W/m2/K | VIOLATED | expression parse | No | UNRESOLVED / UNRESOLVED | VIOLATED / VIOLATED | none |
| T13 | window_u le 2.6 W/m2/K | SATISFIED | source-span grounding | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / SATISFIED | none |
| T14 | slab_r ge 1.0 m2*K/W | VIOLATED | source-span grounding | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / UNRESOLVED | missing evidence (conflict) |
| T15 | solar le 0.4 1 | VIOLATED | expression parse | No | UNRESOLVED / UNRESOLVED | UNRESOLVED / VIOLATED | none |

The additional seven manual-rule decisions use synthetic named attestations. They do not count as automatic interpretations or measured independent reviewer performance. In the automated run all 15/15 primary blockers are interpretation. Missing computation, missing evidence, incomplete inventory and specialist judgment each have 0/15 primary blockers at that stage. In the manual ceiling, missing evidence accounts for the remaining 2/15. Attesting a value requires its meaning and scope to be declared first.

Artifacts include [raw 7B traces](../reports/morocco-ceiling-7b-drafts.jsonl), [stage classifications](../reports/drafting-stage-diagnosis.json), [raw thermal traces](../reports/thermal-interpreter-drafts.jsonl) and [execution comparisons](../reports/thermal-interpreter-results.json).
