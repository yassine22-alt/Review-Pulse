# Milestone 6: the results behind the decision

These are the result files behind the table in `docs/progress/M6_evidence_and_measurement.md`
and decision A51 in `docs/DECISIONS.md`. Each folder is one full evaluation on 100 real drawings
per dataset (FloorPlanCAD and ArchCAD), the generated plans, and the planted errors.

| Folder | Code | Model |
|---|---|---|
| `before_v4`, `before_v4_rooms` | before A49 and A50 | v4 (the previous default) |
| `before_v6`, `before_v6_rooms` | before A49 and A50 | v6 |
| `new_code_v4`, `new_code_v4_rooms` | with A49 and A50 | v4 |
| `new_code_v6`, `new_code_v6_rooms` | with A49 and A50 | **v6 (the default now)** |

The `.md` and `.csv` files give walls, doors and windows; `*_rooms/*.json` give rooms on real CAD,
with one line per drawing under `per_drawing`.
