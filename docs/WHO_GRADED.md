# Who graded the answer keys

**Every answer key and every "useful or not" mark in this repository that was graded by reading or by eye was made by an AI
assistant that I used while building ReviewPulse.** No person made them, and no person, plan reviewer or not, has checked them.
Several pages said "one person", "my labels" or "I judged". That was wrong. I corrected it on 28 November 2026.

| Key or marks | Used in |
| --- | --- |
| `benchmarks/checklist_labels.json` | the checklist benchmark, [M12](progress/M12_checklist_benchmark.md) to [M15](progress/M15_evidence_in_the_drawings.md) |
| `benchmarks/stpete_evidence_needs.json`, `benchmarks/austin_stpete_sheets.json` | [M31](progress/M31_what_each_item_needs.md) |
| `benchmarks/austin_stpete_parts_judgements.json` and `..._m36.json` | [M32](progress/M32_part_by_part_and_vision.md), [M36](progress/M36_model_reads_more_plan.md) |
| `benchmarks/vision_presence.json`, `benchmarks/vision_held_out.json` | [M32](progress/M32_part_by_part_and_vision.md), [M33](progress/M33_vision_held_out.md), [M35](progress/M35_visual_search_plan.md) |
| Looks at pages, rules and table cells with no key file | [M10](progress/M10_real_world_findings.md), [M11](progress/M11_second_pass.md), [M18](progress/M18_sheet_tables.md), [M29](progress/M29_review_desk_on_a_real_set.md) |

## What this changes

* A score against one of these keys says how often the tool agrees with an AI grader. It is not accuracy that people confirmed.
* The grader also helped build what it graded, so it is not independent of it.
* Keys that were committed before a run still show that the order was respected. They do not show that the keys are right.
* When 40 already marked pieces were marked again with the old marks hidden, 39 marks were the same
  ([M36](progress/M36_model_reads_more_plan.md)). It is the same kind of grader both times, so this shows that the marks repeat,
  not that they are correct.

## What is not affected

Scores on generated and planted plans (the truth is built into the file), scores on public datasets such as FloorPlanCAD (the
truth comes from the dataset's authors), the label free audits and the automated tests.

## What would fix it

A plan reviewer grading a sample of each key without seeing the marks. Until then, results from these keys are leads, not proof.
