from reviewpulse.perception.native_labels import anchor_native_labels
from reviewpulse.schema import Prov, Room, TextItem


def region():
    return Room(id="region", polygon=[(0, 0), (10, 0), (10, 10), (0, 10)], label="old",
                type="old_type", area_m2=1, prov=Prov(source="derived", stage="rooms_v1"))


def label(name, bounds=(1, 1, 2, 2), source="vector"):
    return TextItem(id=name, text=name, bbox=bounds, kind="room_label", norm="category_a",
                    prov=Prov(source=source, stage="pdf_extract"))


def test_unique_native_label_names_existing_region_without_changing_geometry():
    room = region()
    before = room.polygon[:]
    trace = anchor_native_labels([room], [label("Space A")])
    assert room.label == "Space A" and room.type == "category_a"
    assert room.polygon == before and trace[0]["geometry_changed"] is False
    assert room.prov.evidence["classification_confirmed"] is False


def test_two_labels_inside_merged_region_do_not_silently_choose_a_name():
    room = region()
    anchor_native_labels([room], [label("Space A"), label("Space B", (5, 5, 6, 6))])
    assert room.type is None and room.label is None
    assert room.prov.evidence["native_anchor_status"] == "conflicting_labels"


def test_outside_and_ocr_labels_cannot_establish_native_name_or_inferred_enclosure():
    room = region()
    room.prov.evidence["boundary"] = "inferred_from_labels"
    trace = anchor_native_labels([room], [label("Outside", (20, 20, 21, 21)), label("OCR", source="ocr")])
    assert room.type is None
    assert "boundary_issue" in trace[0]
