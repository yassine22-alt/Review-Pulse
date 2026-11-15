# Rule tests

| rule | clean plan | failing fixtures | status |
|---|---|---|---|
| C-C1 | PASS | topo_no_exit: FAIL (want FAIL) | ok |
| C-D1 | PASS | metric_door_narrow: FAIL/PASS (want FAIL) | ok |
| C-D2 | PASS | metric_corridor_pinch: FAIL (want FAIL) | ok |
| C-D3 | PASS | metric_kitchen_small: FAIL/PASS (want FAIL); metric_room_small: FAIL/PASS (want FAIL) | ok |
| C-D3W | PASS | metric_bedroom_narrow: FAIL/PASS (want FAIL); metric_kitchen_small: FAIL/PASS (want FAIL) | ok |
| C-D3L | PASS | metric_bedroom_narrow: FAIL (want FAIL); metric_living_small: FAIL (want FAIL) | ok |
| C-D5 | PASS | metric_kitchen_small: FAIL (want FAIL) | ok |
| C-T1 | PASS | topo_bedroom_via_bedroom: FAIL/PASS (want FAIL); topo_exit_via_bath: FAIL/PASS (want FAIL); topo_no_exit: FAIL (want FAIL) | ok |
| C-T2 | PASS | topo_bedroom_via_bedroom: FAIL/PASS (want FAIL); topo_no_exit: FAIL (want FAIL) | ok |
| C-T3 | PASS | topo_garage_bedroom: FAIL (want FAIL) | ok |
| C-T4 | PASS | topo_dead_end_no_window: FAIL/PASS (want FAIL) | ok |
| C-T5 | PASS | metric_travel_far: FAIL/PASS (want FAIL) | ok |
| C-V1 | PASS | metric_escape_window: FAIL/PASS (want FAIL); metric_travel_far: FAIL/PASS/WARNING (want FAIL); metric_window_small: FAIL/PASS (want FAIL); topo_dead_end_no_window: FAIL/PASS (want FAIL) | ok |
| C-V2 | PASS | metric_escape_window: FAIL/PASS (want FAIL); metric_window_small: FAIL/PASS (want FAIL) | ok |
| K-A1 | PASS | cons_chain_off: FAIL/PASS (want FAIL); cons_written_vs_drawn: FAIL/PASS (want FAIL) | ok |
| K-A2 | PASS | cons_written_vs_drawn: FAIL/PASS (want FAIL) | ok |
| K-A3 | PASS | cons_area_text: FAIL/PASS (want FAIL) | ok |
| K-X1 | PASS | cons_schedule_width: FAIL/PASS (want FAIL) | ok |
| P-1 | PASS | comp_unlabelled_room: FAIL/PASS (want FAIL) | ok |
| P-2 | PASS | comp_no_dimensions: FAIL (want FAIL) | ok |
| P-3 | PASS | comp_tag_missing: FAIL (want FAIL) | ok |
| P-4 | PASS | comp_title_incomplete: FAIL (want FAIL) | ok |
| P-5 | PASS | comp_door_untagged: FAIL/PASS (want FAIL) | ok |
| P-6 | PASS | topo_isolated_room: FAIL/PASS (want FAIL) | ok |
| Q-1 | PASS | coord_swing_overlap: WARNING (want WARNING) | ok |
