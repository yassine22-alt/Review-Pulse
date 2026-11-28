"""A block of general notes for a generated plan, the way permit drawings carry them beside the plan or on a notes sheet.

The generated plans had no words about safety provisions, so nothing could be measured about them. This writes a numbered
"GENERAL NOTES" block to the right of the drawing. The wording is ours (generic, in the style of permit drawings), never copied
from a real set. `leave_out` drops notes so that a planted omission can be tested ("the set never mentions smoke alarms").
"""

from __future__ import annotations

from pathlib import Path

NOTES: dict[str, str] = {
    "smoke_alarm_notes": "PROVIDE A SMOKE ALARM IN EACH BEDROOM AND IN THE HALLWAY SERVING THE BEDROOMS.",
    "co_alarm_notes": "PROVIDE A CARBON MONOXIDE ALARM OUTSIDE EACH SLEEPING AREA.",
    "fire_rating_notes": "DOOR BETWEEN GARAGE AND DWELLING: 20 MINUTE FIRE RATED, SELF CLOSING.",
    "safety_glazing_notes": "GLAZING WITHIN 24 IN OF A DOOR SHALL BE TEMPERED.",
    "handrail_notes": "STAIRS WITH FOUR OR MORE RISERS SHALL HAVE A HANDRAIL 34 TO 38 IN ABOVE THE NOSINGS.",
    "guard_notes": "GUARDRAILS 36 IN HIGH AT FLOOR SURFACES MORE THAN 30 IN ABOVE GRADE.",
    "egress_notes": "EVERY BEDROOM SHALL HAVE AN EMERGENCY ESCAPE AND RESCUE OPENING.",
}


def add_general_notes(dxf_path: str | Path, leave_out: tuple[str, ...] = ()) -> list[str]:
    """Append the notes block to a DXF plan (in place); returns the kinds of note written."""
    import ezdxf
    from ezdxf import bbox

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    ext = bbox.extents(msp)
    x0, y = ext.extmax.x + 3.0, ext.extmax.y
    if "A-ANNO-NOTE" not in doc.layers:
        doc.layers.add("A-ANNO-NOTE", color=7)
    written = [k for k in NOTES if k not in leave_out]
    rows = ["GENERAL NOTES"] + [f"{i}. {NOTES[k]}" for i, k in enumerate(written, 1)]
    for row in rows:
        t = msp.add_text(row, height=0.15, dxfattribs={"layer": "A-ANNO-NOTE"})
        t.set_placement((x0, y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_LEFT)
        y -= 0.40
    doc.saveas(dxf_path)
    return written
