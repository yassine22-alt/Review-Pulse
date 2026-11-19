from reviewpulse.perception.polygonized import polygonized_regions


def test_closed_faces_are_noded_but_not_given_trusted_area_or_class():
    rooms, trace = polygonized_regions([[(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]], "sheet")
    assert len(rooms) == 1 and trace["faces"] == 1
    assert rooms[0].type is None and rooms[0].area_m2 is None


def test_unexplained_gap_is_not_silently_closed():
    rooms, trace = polygonized_regions([[(0, 0), (2, 0), (2, 2), (0, 2)]], "sheet")
    assert not rooms and trace["dangles"] > 0 and not trace["automatic_gap_closing"]


def test_explicit_closing_line_can_establish_a_face():
    rooms, _ = polygonized_regions([[(0, 0), (2, 0), (2, 2), (0, 2)], [(0, 2), (0, 0)]], "sheet")
    assert len(rooms) == 1
