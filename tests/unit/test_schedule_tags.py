"""A tag the schedule lists with two different sizes does not say which is the element's: no size is taken from it."""

from types import SimpleNamespace

from reviewpulse.factgraph.from_building import schedule_rows


def model(*tables):
    return SimpleNamespace(schedules=[{"rows": list(rows)} for rows in tables])


def test_two_sizes_for_one_tag_give_no_size():
    got = schedule_rows(model([{"tag": "D1", "height_m": 2.1, "type": "door"}], [{"tag": "D1", "height_m": 2.4, "type": "door"}]))
    assert "height_m" not in got["D1"] and got["D1"]["type"] == "door"


def test_the_same_row_in_two_tables_is_still_one_row():
    row = {"tag": "W2", "height_m": 1.25, "sill_m": 0.9}
    got = schedule_rows(model([row], [dict(row, type="fixed")]))
    assert (got["W2"]["height_m"], got["W2"]["sill_m"]) == (1.25, 0.9)
