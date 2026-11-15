# Saved scan policy replay

Same saved BuildingModel and starter rule pack. Perception was not rerun.
The original findings remain intact. These counts are policy changes, not accuracy measurements.

| Legacy label | Before | After |
|---|---:|---:|
| PASS | 19 | 3 |
| WARNING | 14 | 30 |
| FAIL | 0 | 0 |
| NOT_EVALUATED | 15 | 15 |

Structured outcomes: {"UNRESOLVED": 45, "SATISFIED": 3}

Before warning reasons: estimated scale 7, unconfirmed connections 2, possible OCR omission 5.

After evidence issues (a finding can have multiple issues):

| Issue | Findings |
|---|---:|
| MISSING_CONNECTION | 18 |
| MISSING_INPUT | 6 |
| POSSIBLE_TEXT_OMISSION | 4 |
| UNCERTAIN_SCALE | 13 |
| UNKNOWN_CLASS | 9 |
| UNVERIFIED_GEOMETRY | 11 |

## All 19 original passes

| Rule | Subjects | Original measurement | New outcome | Issues |
|---|---|---|---|---|
| C-C1 | door_da8bfd4fa0, door_4e1a89dd66, door_08cfa8ab8c, door_4d0e9b4baa, door_0dbf172957, door_2f86518ab2, door_e54624bf07 | 7 | now-UNRESOLVED | MISSING_CONNECTION |
| C-D1 | door_da8bfd4fa0 | 1.23 m | still-SATISFIED | UNCERTAIN_SCALE |
| C-D1 | door_4e1a89dd66 | 1.40 m | now-UNRESOLVED | UNCERTAIN_SCALE, UNVERIFIED_GEOMETRY |
| C-D1 | door_4d0e9b4baa | 1.25 m | still-SATISFIED | UNCERTAIN_SCALE |
| C-D3 | room_fe77501d70 | 182.80 m² | now-UNRESOLVED | UNCERTAIN_SCALE, UNVERIFIED_GEOMETRY |
| C-D3L | room_e3fa2ce70c | 14.86 m² | now-UNRESOLVED | UNCERTAIN_SCALE, UNVERIFIED_GEOMETRY |
| C-T1 | room_fe77501d70 | reachable | now-UNRESOLVED | MISSING_CONNECTION |
| C-T2 | room_fe77501d70 | reachable | now-UNRESOLVED | MISSING_CONNECTION |
| C-T3 |  | none | still-SATISFIED |  |
| C-T4 | room_fe77501d70 | 3 door(s), window: True | now-UNRESOLVED | MISSING_CONNECTION |
| C-T5 | room_e3fa2ce70c | 8.25 m | now-UNRESOLVED | UNCERTAIN_SCALE, UNVERIFIED_GEOMETRY |
| P-1 | room_8af0c979d8 | Shower | now-UNRESOLVED | MISSING_CONNECTION |
| P-1 | room_e3fa2ce70c | Dining Room | now-UNRESOLVED | MISSING_CONNECTION |
| P-1 | room_fe77501d70 | Bedroom # 1 | now-UNRESOLVED | MISSING_CONNECTION |
| P-1 | room_ec2e254f26 | Bathroom # 2 | now-UNRESOLVED | MISSING_CONNECTION |
| P-6 | room_6ba8067c30 | 1 door(s) or opening(s) | now-UNRESOLVED | MISSING_CONNECTION |
| P-6 | room_e3fa2ce70c | 1 door(s) or opening(s) | now-UNRESOLVED | MISSING_CONNECTION |
| P-6 | room_fe77501d70 | 3 door(s) or opening(s) | now-UNRESOLVED | MISSING_CONNECTION |
| P-6 | room_ec2e254f26 | 4 door(s) or opening(s) | now-UNRESOLVED | MISSING_CONNECTION |
