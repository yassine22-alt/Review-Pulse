"""Variant demo plans: each scenario shows a different part of ReviewPulse, with the planted truth known.

Shared by `scripts/make_demo_plans.py` (the gallery for demos) and the scenario tests, so what is demonstrated is exactly
what is tested.
"""

from __future__ import annotations

# name, kind, options, what it shows
SCENARIOS = [
    ("01_clean", "make", dict(seed=11), "A plan with no planted error: every rule is satisfied once you confirm the plan "
     "inventory; before that the answer is a warning, never a silent pass."),
    ("02_door_too_narrow", "make", dict(seed=12, errors=("metric_door_narrow",)),
     "One door is 0.70 m wide against a 0.80 m limit: one violation drawn on that door, with the measured value."),
    ("03_rooms_too_small", "make", dict(seed=13, errors=("metric_room_small", "metric_living_small")),
     "A 7.5 m2 bedroom and a small living room: the bedroom rule has two conditions (area and width) and reports each."),
    ("04_bedroom_through_bathroom", "make", dict(seed=14, errors=("topo_exit_via_bath",)),
     "A bedroom can only leave through the bathroom: a route rule that avoids bathrooms."),
    ("05_garage_next_to_bedroom", "make", dict(seed=15, errors=("topo_garage_bedroom",)),
     "A door joins a garage directly to a bedroom: a rule about a direct link between two kinds of room."),
    ("06_dead_end_room", "make", dict(seed=16, errors=("topo_dead_end_no_window",)),
     "A room with a single door and no window: a rule on door counts."),
    ("07_exit_too_far", "make", dict(seed=17, errors=("metric_travel_far",)),
     "A 17 m wide dwelling: travel distance to the exit over 15 m, walked around corners."),
    ("08_no_exit_at_all", "make", dict(seed=18, errors=("topo_no_exit",)),
     "No door to the outside: every habitable room fails the route rule and the exit count fails."),
    ("09_isolated_room", "make", dict(seed=19, errors=("topo_isolated_room",)),
     "A room with no door or opening at all."),
    ("10_rotated_other_scale", "make", dict(seed=20, rotate=90, denominator=50, errors=("metric_door_narrow",)),
     "Same kind of error as scenario 02 on a page rotated 90 degrees at 1:50: the finding must not change."),
    ("11_everything_wrong", "make", dict(seed=21, errors=("metric_door_narrow", "metric_room_small", "topo_exit_via_bath",
                                                         "cons_chain_off", "comp_unlabelled_room")),
     "Several kinds of error at once: measurements, a route, a dimension chain and a missing label."),
    ("12_other_drawing_style", "rand", dict(seed=803, scheme="fr", wall_style="polylines", door_style="bulge", angle=-33.0,
                                           units="mm", clutter=False),
     "A different generator: random layout, French layers, doors drawn as bulge polylines, rotated 33 degrees, in "
     "millimetres. Nothing planted: it shows the reader copes with another drawing style."),
    ("13_l_shaped_clutter", "rand", dict(seed=805, scheme="aia", wall_style="hatched", door_style="arc_leaf", angle=17.0,
                                        units="m", clutter=True, L_shape=True),
     "An L-shaped dwelling with furniture drawn in, hatched walls and CAD layer names: harder to read, same result expected."),
]
