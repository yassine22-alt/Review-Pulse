"""The I4 scorer: a perfect replay model scores 100%, an over-eager one is penalised."""

import yaml

from reviewpulse.eval.drafting import GOLD, run_drafting_eval
from reviewpulse.rules.draft import ReplayClient

RASE = {"requirement": [], "applicability": [], "selection": [], "exception": []}
FN_TO_PROP = {"width_m": "clear_width", "area_m2": "floor_area", "exists_path": "route_to_exit",
              "forbidden_link": "forbidden_direct_connection", "count_exits": "number_of_exits",
              "shortest_path_m": "travel_distance_to_exit", "ratio": "glazed_area_ratio",
              "present": "rooms_labelled", "sum_parts": "dimension_chain_sum",
              "drawn_vs_stated": "written_vs_drawn_dimension", "join": "tags_match_schedule",
              "swing_conflicts": "door_swing_overlap", "stated_vs_computed_area": "stated_vs_drawn_area"}
OP_TO_COMP = {">=": "at_least", "<=": "at_most", None: "no_number"}


def _frame(g):
    if g["checkable"] != "from_drawings":
        prop = "door_height" if g["checkable"] == "needs_other_data" else "fire_resistance"
        return {"property": prop, "subject": "room", "room_types": [], "avoid_room_types": [], "forbidden_pairs": [],
                "comparison": "no_number", "number": None, "unit_written": "none", "severity": "major",
                "title": g["id"], "rase": RASE}
    e = g["expect"]
    prop = FN_TO_PROP.get(e["fn"])
    if e["fn"] == "min_width_m":
        prop = "corridor_width" if e.get("room_types") == ["corridor"] else "room_minimum_dimension"
    unit = {"m": "m", "m2": "m2"}.get(e.get("unit"), "fraction" if e["fn"] == "ratio" else
                                       "count" if e["fn"] == "count_exits" else "none")
    return {"property": prop, "subject": "door" if e.get("element") == "door" else "room",
            "room_types": e.get("room_types", []), "avoid_room_types": e.get("avoid", []),
            "forbidden_pairs": e.get("pairs", []), "comparison": OP_TO_COMP.get(e.get("op"), "at_least"),
            "number": e.get("value"), "unit_written": unit, "severity": "major", "title": g["id"], "rase": RASE}


def test_perfect_model_scores_full_marks():
    gold = yaml.safe_load(GOLD.read_text(encoding="utf-8"))
    res, rows = run_drafting_eval(ReplayClient({g["id"]: _frame(g) for g in gold}))
    a = res["all"]
    assert a["label_accuracy"] == 1.0, rows
    assert a["non_checkable_refused"] == "5/5"
    for f in ("fn", "op", "value", "unit", "scope"):
        assert a[f"{f}_recall"] == 1.0, (f, [r for r in rows if r[3] != "exact" and "refused" not in r[3]])


def test_over_eager_model_is_penalised():
    gold = yaml.safe_load(GOLD.read_text(encoding="utf-8"))
    answers = {g["id"]: _frame(g) for g in gold}
    first = _frame(gold[0])
    for g in gold:
        if g["checkable"] != "from_drawings":      # drafts a door rule for a fire-rating clause
            answers[g["id"]] = first
    res, _ = run_drafting_eval(ReplayClient(answers))
    assert res["all"]["non_checkable_refused"] == "0/5"
    assert res["all"]["label_accuracy"] < 1.0
