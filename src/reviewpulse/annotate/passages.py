"""The written notes of a drawing set as passages: one numbered note, one legend entry, one callout each.

A requirement about something a plan view does not draw to measure is usually answered in words somewhere in the set ("door to
garage: 20 minute rated", "handrail 34 to 38 in above the nosings"). To find those words for any requirement, the text of every
sheet is first cut into passages a person would read as one statement. Nothing here knows what a passage is about; that is the
job of retrieval (interpreter/drawing_evidence.py).

How a passage is made, from text runs with positions (the same for DXF, PDF and OCR text):
  - runs on one visual line are joined, left to right;
  - a line continues the passage above it when it starts at the same left edge (or indented under a numbered note), follows it
    closely, and does not itself start a new numbered note;
  - text that is a dimension, a schedule tag or a room name is not a note and is left out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NOT_NOTES = {"dimension", "tag", "room_label", "area"}
NUMBERED = re.compile(r"^\s*(?:\d{1,3}|[A-Za-z])[.)]\s+\S")
MIN_LETTERS = 12                      # shorter than this is a label or a tag, not a statement


LONG = 320                            # a passage longer than this holds several statements and is cut into its sentences
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+(?=[A-ZÀ-Ý0-9])")


@dataclass(frozen=True)
class Passage:
    sheet: str
    text: str


def statements(text: str) -> list[str]:
    """A long block (a paragraph of electrical notes, a specification) as the statements it is made of. A requirement is answered by
    one sentence, and inside a long block that sentence is outweighed by everything around it. A short passage is left whole."""
    if len(text) <= LONG:
        return [text]
    out, cur = [], ""
    for part in SENTENCE_END.split(text):
        if cur and len(cur) + len(part) > LONG:
            out.append(cur)
            cur = part
        else:
            cur = f"{cur} {part}".strip()
    return [*out, cur] if cur else out


def _lines(texts) -> list[tuple[float, float, float, str]]:
    """Visual lines as (top y, left x, height, text). Sheet coordinates have y pointing up, so a larger y is higher on the sheet."""
    items = []
    for t in texts:
        text = " ".join((t.text or "").split())
        if not text or getattr(t, "kind", "unknown") in NOT_NOTES:
            continue
        x0, y0, x1, y1 = t.bbox
        height = t.height or abs(y1 - y0) or 1.0
        items.append(((y0 + y1) / 2, min(x0, x1), height, text))
    items.sort(key=lambda it: (-it[0], it[1]))
    lines: list[list] = []
    for mid, left, height, text in items:
        if lines and abs(mid - lines[-1][0]) <= 0.5 * max(height, lines[-1][2]):
            lines[-1][3].append((left, text))
            lines[-1][1] = min(lines[-1][1], left)
        else:
            lines.append([mid, left, height, [(left, text)]])
    return [(mid, left, height, " ".join(t for _x, t in sorted(parts))) for mid, left, height, parts in lines]


def sheet_passages(sheet_id: str, texts) -> list[Passage]:
    out: list[Passage] = []
    block: list[str] = []
    prev = None                                   # (y, left, height) of the last line of the open passage
    first_left = 0.0

    def close():
        for text in statements(" ".join(block)):
            if sum(ch.isalpha() for ch in text) >= MIN_LETTERS:
                out.append(Passage(sheet_id, text))
        block.clear()

    for mid, left, height, text in _lines(texts):
        joins = False
        if prev is not None and block and not NUMBERED.match(text):
            close_below = 0 < prev[0] - mid <= 2.2 * max(height, prev[2])
            aligned = abs(left - prev[1]) <= 1.5 * height or (0 <= left - first_left <= 6 * height)
            joins = close_below and aligned
        if not joins:
            close()
            first_left = left
        block.append(text)
        prev = (mid, left, height)
    close()
    return out


def set_passages(models) -> list[Passage]:
    """Every passage of every sheet of a submission, in sheet order. Identical passages (a note repeated on each sheet) are kept once."""
    seen, out = set(), []
    for m in models:
        for p in sheet_passages(m.sheet.id, m.sheet.texts):
            key = p.text.lower()
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out
