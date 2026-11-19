# Independent grading sample

Send only `reports/teammate-blind-grading.csv` and these instructions to the teammate. Do not send `reports/blind-grading-key.json` or the earlier assistant adjudication: they reveal the arm and assistant grades. Ten source/draft pairs are shuffled, with five from each arm; the arm is not in the CSV.

Leave source and model output unchanged. Fill subject_grade, fact_grade, operator_grade, value_grade, unit_grade, scope_grade and whole_rule_grade with `correct`, `partly_correct`, `wrong`, `not_applicable`, or `cannot_grade`. Whole-rule grades refer to intended source meaning, including applicability, exceptions and ownership. Grammar failure alone does not make the threshold wrong. Missing units/scope are not correct merely because a number matches. If context is insufficient, use cannot_grade and explain. Notes may explain ambiguous source interpretations or differences from the draft.

No assistant grades or automated suggested answers appear in the sheet. Return the edited CSV. The agreement script then reports exact counts, disagreements and nominal Cohen kappa, excluding cannot_grade and cells where both raters mark not_applicable. Blank cells are pending, never agreement. This is a purposeful ten-row sample, not an independent validation of the whole interpreter.

After return: `python scripts/grade_blind_sample.py <returned.csv> reports/blind-grading-key.json reports/independent-grading-agreement.json`.

The CSV now embeds a per-column correct / partly-correct / wrong rubric in
`instructions_and_rubric`. Read it before filling grades. The script accepts
`partly correct` as well as `partly_correct` and reports per-slot agreement
with explicit denominators. No arm or assistant grade is embedded.
