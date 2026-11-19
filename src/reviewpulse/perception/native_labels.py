"""Name existing regions from contained native text; never create room boundaries."""
from __future__ import annotations

from shapely.geometry import Point, Polygon

from ..schema import Room, TextItem


def anchor_native_labels(rooms: list[Room], texts: list[TextItem]) -> list[dict]:
    labels = [text for text in texts if text.kind == "room_label"
              and text.prov.source == "vector" and text.prov.stage == "pdf_extract"]
    trace = []
    for room in rooms:
        polygon = Polygon(room.polygon, room.holes)
        contained = {text.id: text for text in labels if polygon.contains(Point(
            (text.bbox[0] + text.bbox[2]) / 2, (text.bbox[1] + text.bbox[3]) / 2))}
        status = "anchored" if len(contained) == 1 else "conflicting_labels" if contained else "missing_label"
        if status == "anchored":
            text = next(iter(contained.values()))
            room.label, room.type = text.text, text.norm
        else:
            # The available trained model classifies primitives, not room use.
            # It cannot establish a bedroom name when the native anchors disagree.
            room.label, room.type = None, None
        evidence = {"native_anchor_status": status, "native_anchor_ids": sorted(contained),
                    "geometry_changed": False, "classification_confirmed": False}
        if room.prov.evidence.get("boundary") == "inferred_from_labels":
            evidence["boundary_issue"] = "inferred_from_labels; enclosure not established by this naming step"
        room.prov.evidence.update(evidence)
        trace.append({"room": room.id, **evidence})
    return trace
