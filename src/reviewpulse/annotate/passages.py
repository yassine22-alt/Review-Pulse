"""The written notes of a drawing set as passages: one numbered note, one legend entry, one callout each.

A requirement about something a plan view does not draw to measure is usually answered in words somewhere in the set ("door to
garage: 20 minute rated", "handrail 34 to 38 in above the nosings"). To find those words for any requirement, the text of every
sheet is first cut into passages a person would read as one statement. Nothing here knows what a passage is about; that is the
job of retrieval (interpreter/drawing_evidence.py).

How a passage is made, from text runs with positions (the same for DXF, PDF and OCR text):
  - runs on one visual line are joined, left to right, as long as no column gap separates them: a drawing sheet has notes,
    schedules and the title block side by side, and text at the same height in two columns is two lines, not one;
  - a line continues the passage whose last line is just above it when it starts at the same left edge (or indented under a
    numbered note) and does not itself start a new numbered note. One passage per column stays open at a time, so columns that
    interleave from top to bottom do not cut each other's notes;
  - text that is a dimension, a schedule tag or a room name is not a note and is left out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NOT_NOTES = {"dimension", "tag", "room_label", "area"}
NUMBERED = re.compile(r"^\s*(?:\d{1,3}|[A-Za-z])[.)]\s+\S")
MIN_LETTERS = 12                      # shorter than this is a label or a tag, not a statement


LONG = 320                            # a passage longer than this holds several statements and is cut into its sentences
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+(?=[A-ZÀ-Ý0-9])")


@dataclass(frozen=True)
class Passage:
    sheet: str
    text: str
    box: tuple[float, float, float, float] | None = field(default=None, compare=False)   # sheet space: where the words are


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


def _union(boxes) -> tuple[float, float, float, float]:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


GUTTER = 2.5                          # a horizontal gap wider than this many text heights separates two columns


def _lines(texts, skip=NOT_NOTES) -> list[tuple[float, float, float, str, tuple]]:
    """Visual lines as (middle y, left x, height, text, box), top first. Sheet coordinates have y pointing up, so a larger y is
    higher on the sheet. Runs at one height are one line only while no column gap separates them."""
    items = []
    for t in texts:
        text = " ".join((t.text or "").split())
        if not text or getattr(t, "kind", "unknown") in skip:
            continue
        x0, y0, x1, y1 = t.bbox
        height = t.height or abs(y1 - y0) or 1.0
        items.append(((y0 + y1) / 2, height, text, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))))
    items.sort(key=lambda it: (-it[0], it[3][0]))
    rows: list[list] = []                                       # runs at one height, whatever their column
    for item in items:
        if rows and abs(item[0] - rows[-1][0][0]) <= 0.5 * max(item[1], rows[-1][0][1]):
            rows[-1].append(item)
        else:
            rows.append([item])
    lines = []
    for row in rows:
        row.sort(key=lambda it: it[3][0])
        part = [row[0]]
        for item in [*row[1:], None]:
            if item is not None and item[3][0] - max(i[3][2] for i in part) <= GUTTER * max(item[1], part[-1][1]):
                part.append(item)
                continue
            box = _union([i[3] for i in part])
            lines.append((part[0][0], box[0], max(i[1] for i in part), " ".join(i[2] for i in part), box))
            if item is not None:
                part = [item]
    return lines


def _passages_of(sheet_id: str, block: list[tuple[str, tuple]], min_letters: int = MIN_LETTERS) -> list[Passage]:
    joined = " ".join(t for t, _b in block)
    spans, at = [], 0                                           # where each line stands in the joined block, with its box
    for t, box in block:
        spans.append((at, at + len(t), box))
        at += len(t) + 1
    out, cursor = [], 0
    for text in statements(joined):
        start = max(joined.find(text, cursor), cursor)
        cursor = start + len(text)
        if sum(ch.isalpha() for ch in text) >= min_letters:
            touched = [box for a, b, box in spans if a < cursor and b > start]
            out.append(Passage(sheet_id, text, _union(touched) if touched else None))
    return out


def sheet_passages(sheet_id: str, texts, skip=NOT_NOTES, min_letters: int = MIN_LETTERS) -> list[Passage]:
    blocks: list[dict] = []                      # in the order they begin; each: lines, and where its last and first lines start
    open_blocks: list[dict] = []
    for mid, left, height, text, box in _lines(texts, skip):
        open_blocks = [k for k in open_blocks if k["y"] - mid <= 2.2 * max(height, k["h"])]      # too far above: closed
        best = None
        if not NUMBERED.match(text):
            for k in open_blocks:
                below = 0 < k["y"] - mid
                aligned = abs(left - k["left"]) <= 1.5 * height or 0 <= left - k["first"] <= 6 * height
                if below and aligned and (best is None or abs(left - k["left"]) < abs(left - best["left"])):
                    best = k
        if best is None:
            # a new passage at this left edge ends the one above it in the same column
            open_blocks = [k for k in open_blocks if abs(left - k["first"]) > 6 * height or k["y"] - mid <= 0]
            best = {"lines": [], "first": left}
            blocks.append(best)
            open_blocks.append(best)
        best["lines"].append((text, box))
        best.update(y=mid, left=left, h=height)
    return [p for k in blocks for p in _passages_of(sheet_id, k["lines"], min_letters)]


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
