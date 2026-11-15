# What ReviewPulse can and cannot do today

This page states, as plainly as the evidence allows, where ReviewPulse can be relied on, where it works with care, and what it does
not do yet. Every statement points to a measurement. It is updated when the measurements change.

ReviewPulse reads a plan and a requirements document, proposes checkable rules, lets a person approve them, runs them on the plan,
and reports each finding on the drawing. It is a reviewer's assistant: it never replaces the approval of a person, and a finding it
cannot support is reported as "cannot be determined".

## Works well

| Capability | Evidence |
| --- | --- |
| **Reading clean vector plans** (PDF, DXF) made by CAD: scale, walls, doors, windows, rooms, routes | Thirteen generated plan variants (different styles, units, rotations, languages) all pass; every planted error is found (3 of 3 on the self-check through the code, the PDF path and the web app). A real clean house plan gives 7 rooms and 11 doors. |
| **Scale on metric and imperial drawings** | Feet and inches, written scales in several languages (1:100, Maßstab, 1/4" = 1'), and scales derived from printed room areas. Scattered evidence gives no scale rather than a wrong one. |
| **Text drawn as outlines** | Read by OCR. On a German apartment plan 62 words were read in about 30 seconds on a laptop CPU, enough to name every room and read its printed area. |
| **Reading long requirement documents** | Nine real documents (a 280 page US standard, a UK fire safety volume, three French accessibility texts, four plan-review checklists) and eight generated styles are split into clauses, tables and definitions. The 280 page standard is read in about two minutes on first use. Checked without labels against an independent reading of the text (clauses starting mid sentence 94 to 20), and by writing the same checklist out in other formats and reading it back (32 variants, recall 0.96, precision 0.98). Details: `docs/progress/M13_reading_any_document.md`. |
| **Requirement documents in other file types** | PDF, scanned PDF or photo of a page (OCR), Word, Excel, csv, web page, Markdown and text. Scans are the weakest: 0.57 to 0.84 of the clauses recovered on synthetic scans, and the English OCR model drops accents. |
| **Not accepting a wrong rule** | The rule is compared with its sentence by programs (numbers, direction, what is measured) and by two multiple choice checks: which quantity the sentence limits (accepts a true rule 92% of the time, rejects a swapped one 100%) and which kind of requirement it states (accepts a true one 90%, rejects a wrong kind 97%). |
| **Requirements about how spaces connect** (a forbidden or required link, a route with spaces to avoid, a door for every room) | On 16 sentences in English, French, German and Spanish, 11 rules were written correctly, 5 were declined to the general arm, none was wrong; 6 sentences that are not relations were all declined. On ten generated plans (eight with a planted connection or distance error), the checks reported a violation in 9 of the 13 cases where the reference engine finds one, and raised no false alarm on the clean plans; of the 4 misses, 3 are clauses the tool declined to turn into a rule and 1 is a rule that states its sentence more faithfully than the reference rule does. |

## Works with caveats

| Capability | What to keep in mind |
| --- | --- |
| **Complex real drawings** | Seven real sheets from three countries were read and all came out "readable with caveats", none unusable and none fully clean. Typical caveats: the scale is written on the sheet and not confirmed by measured dimensions, some room boundaries are inferred from room names, and the drawing prints no areas to cross-check. On the most complex sheet (a US permit set), 12 rooms were found with a printed area, and 11 of them agree with it within 50%. |
| **Plans with missing walls** | When walls are missed, dividing a space by its room names recovers most rooms. In a controlled test on 150 public plans with 8 random wall gaps each, recall rises from 0.32 to 0.80 and F1 from 0.47 to 0.83. On plans with no gap it costs precision (F1 0.99 to 0.94), because an open plan with a named living room and kitchen is divided in two. These boundaries are marked inferred, and an inferred room size or connection can raise a warning but never a failure. |
| **Rules written by the local model** | A 7 billion parameter model on a laptop writes correct rules for limits on one measured quantity and for connection requirements. It does not write rules for conditions, exceptions or several limits in one sentence; those are reported as not checkable, with the reason. A hosted model option exists and has not been measured. |
| **Proxies** | Some requirements are approximated by the closest plan fact (a clear space in front of kitchen fixtures becomes the kitchen's minimum width). The rule is shown in plain words so the reviewer can reject a proxy; it is never applied without approval. |

## Does not do yet

- **Scans and hand sketches.** Only vector drawings are read by the path described here.
- **Drawing sets with several levels.** Each floor plan is read separately; routes between levels are not followed, so "no route to the exit" is not claimed on a level that has no door to the outside.
- **Most of a real regulation.** On random samples of real accessibility texts, almost no clause is about something a plan shows (door handle positions, threshold heights, signage, parking distances). ReviewPulse says so for each clause. It checks the part a plan can decide: room and door sizes, circulation widths, stair dimensions where found, connections, routes and travel distances.
- **Conditional and compound requirements.** "A room with a single door has a window" and sentences with two limits are left to the reviewer.
- **Compliance conclusions without a reviewer.** Every rule needs a person's approval before it runs.

## Verify it yourself

```text
python -m reviewpulse.selfcheck              checks the installation and finds planted errors in a generated plan
python scripts/review_pack.py                runs real drawings and writes a report a reviewer can open in a browser
python scripts/room_stress.py                the missing wall test on a public dataset (see docs/RUNBOOK.md)
python scripts/relations_eval.py             the connection requirement test on a local model
```

The measurements and the decisions taken on them are in [docs/progress/](progress/), in particular
[M10_real_world_findings.md](progress/M10_real_world_findings.md) and [M11_second_pass.md](progress/M11_second_pass.md).
