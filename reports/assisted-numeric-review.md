# Deterministic table extraction and actual header-only linking

Development data. Assistant/author review only; no independent grading. Numeric membership frozen at `278b70d7`.

| Group | Fully correct / zero edits | One edit | More edits / context | Full rule composition |
| --- | --- | --- | --- | --- |
| Thermal | 12/15 | 0/15 | 3/15 | 0/15 |
| Other numeric | 0/21 | 0/21 | 0/21 | 21/21 |
| All numeric | 12/36 | 0/36 | 3/36 | 21/36 |

Every thermal row retains five typed scope conditions (zone, class, approach and both glazing bounds), its numeric value and comparator. Twelve carry an explicit header unit. Three solar rows have an unresolved cell qualifier and no explicit unit: the numeric value is retained but the whole rule stays review-only.

Four real GPT-OSS-120B strict-schema requests selected the four distinct compatible fact meanings; source rows reuse these choices. Actual usage: 1,376 input + 654 output = **2,030 tokens**, or four calls for twelve rules. All four requests succeeded; 0/4 non-200 responses. Wrong/incomplete source-approvable rules: **0/12**, assistant reviewed. This is not false-pass accuracy: no labelled plan was run in this interpretation evaluation.

The initial larger choice-or-declaration schema was a separate pilot: one dual selection rejected by validation, one HTTP 400 json_validate_failed. That was not a daily quota error and was corrected in the transport report. The minimal fact-only run is a changed development contract, not a controlled model-capacity comparison.

Narrative clauses keep quantity scans and original spans but are not given guessed semantics. Manual composition counts as rewrite for operational edit burden. Three missing-context cases are not assigned a fictitious exact edit count. The preregistered >=50% numeric criterion is **not met: 12/36 <=1 edit**. No final pipeline is selected.

All cell decisions, typed applicability and unit sources are logged with source offsets in [full results](assisted-numeric-minimal-results.json). [Review counts](assisted-numeric-review.json).
