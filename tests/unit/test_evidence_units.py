"""Each searchable piece of a drawing set says where it sits; drawings and sheets are pieces too."""

from types import SimpleNamespace

from reviewpulse.annotate.evidence_units import PT_PER_MM, evidence_units, sheets_in_order, written_units

HEIGHT = 300.0


def text(words, x, y):
    return SimpleNamespace(text=words, bbox=(x, y, x + 80, y + 3), height=3.0, kind="unknown")


def model(page, texts):
    return SimpleNamespace(sheet=SimpleNamespace(id=f"s{page}", page=page, height=HEIGHT, texts=texts))


def frame(x0, y0, x1, y1):
    """A drawing frame given in sheet millimetres (y up), as the drawing set model states it: page points, y down."""
    return (x0 * PT_PER_MM, (HEIGHT - y1) * PT_PER_MM, x1 * PT_PER_MM, (HEIGHT - y0) * PT_PER_MM)


def view(title, kind, bbox):
    return SimpleNamespace(id=title, title=title, kind=kind, bbox=bbox)


def drawing_set(*sheets):
    return SimpleNamespace(sheets=[SimpleNamespace(index=i, title=t, views=v) for i, t, v in sheets])


def test_a_note_is_searched_with_its_sheet_and_the_smallest_drawing_it_stands_in():
    note = "All fans are vented to the exterior of the building."
    models = [model(0, [text(note, 20, 200)])]
    ds = drawing_set((0, "HVAC PLAN", [view("WHOLE SHEET AREA", "plan", frame(0, 0, 400, 300)),
                                       view("GENERAL NOTES:", "notes", frame(10, 180, 150, 220))]))
    units = evidence_units(models, ds)
    [piece] = [u for u in units if u.kind == "note"]
    assert piece.search == f"HVAC PLAN / GENERAL NOTES: {note}" and piece.text == note and piece.page == 1
    assert piece.box is not None


def test_drawings_and_sheets_can_be_found_without_any_note_about_them():
    ds = drawing_set((0, "PLUMBING & HVAC PLAN", [view("2ND FLOOR HVAC PLAN", "plan", frame(0, 0, 400, 300))]))
    units = evidence_units([model(0, [])], ds)
    assert {u.kind for u in units} == {"view", "sheet"}
    assert any("plan drawing: 2ND FLOOR HVAC PLAN" in u.search and "PLUMBING" in u.search for u in units)


def test_a_stamp_found_on_every_sheet_is_not_a_drawing_title():
    ds = drawing_set(*[(i, f"SHEET {i}", [view("Sample", "other", frame(0, 0, 400, 300))]) for i in range(5)])
    units = evidence_units([model(i, []) for i in range(5)], ds)
    assert not any(u.kind == "view" for u in units) and not any("Sample" in u.search for u in units)


def test_without_a_drawing_set_only_the_notes_are_searched_as_written():
    note = "Provide one smoke detector in each bedroom."
    [piece] = evidence_units([model(2, [text(note, 20, 200)])])
    assert (piece.page, piece.search) == (3, note)


def test_a_sheet_is_ranked_by_its_best_piece():
    unit = lambda page: SimpleNamespace(page=page)  # noqa: E731
    assert sheets_in_order([unit(14), unit(2), unit(2), unit(2), unit(9), unit(5)]) == [14, 2, 9]


def run(words, x, y, kind="unknown"):
    return SimpleNamespace(text=words, bbox=(x, y, x + 20, y + 3), height=3.0, kind=kind)


def test_short_texts_are_found_with_their_place_once_a_sheet_and_codes_are_not_words():
    note = "Provide one smoke detector in each bedroom."
    texts = [run("WATER HEATER", 50, 200), run("WATER HEATER", 250, 100), run("S6", 90, 90), run("R-50", 130, 60),
             run("EXAMPLE FIRM", 5, 5, "title_block"), run(note, 20, 150)]
    ds = drawing_set((0, "PLUMBING PLAN", [view("GROUND FLOOR", "plan", frame(0, 0, 400, 300))]))
    got = written_units([model(0, texts)], ds)
    labels = [u for u in got if u.kind == "label"]
    assert [(u.text, u.times) for u in labels] == [("WATER HEATER", 2)]
    assert labels[0].search == "PLUMBING PLAN / GROUND FLOOR: WATER HEATER"
    assert labels[0].sheet == "s0" and labels[0].box is not None


def test_measurements_are_counted_for_the_drawing_they_stand_in_and_table_rows_stay_whole():
    texts = [run("12'-0\"", 40, 200, "dimension"), run("3'-6\"", 80, 200, "dimension"),
             run("D1", 200, 100), run("ENTRY DOOR", 260, 100)]
    ds = drawing_set((0, "SCHEDULES", [view("FIRST FLOOR", "plan", frame(0, 150, 150, 250)),
                                       view("DOOR SCHEDULE", "schedule", frame(180, 80, 340, 120))]))
    got = written_units([model(0, texts)], ds)
    [measures] = [u for u in got if u.kind == "dimensions"]
    assert measures.text.startswith("2 written dimensions on the drawing FIRST FLOOR") and measures.box == (40, 200, 100, 203)
    assert [u.text for u in got if u.kind == "row"] == ["D1 | ENTRY DOOR"]
