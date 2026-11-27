"""A narrow question to a vision model about one area of a drawing: is this thing shown, and where?

The place is asked as cells of a grid drawn on the picture, not as pixel coordinates: models disagree on how they write
coordinates and rescale pictures before reading them, while a labelled cell means the same thing to every model. A larger
area can be asked tile by tile, which gives each part more pixels and a place that does not rest on what the model says.

Nothing here knows what is being looked for. An answer is never a finding: whether it may even be shown to a reviewer is
decided by how it measures (scripts/vision_eval.py), above all by how often it says yes to what is not there."""

from __future__ import annotations

import io

COLUMNS, ROWS = 4, 4
CELLS = [f"{chr(65 + c)}{r + 1}" for r in range(ROWS) for c in range(COLUMNS)]
ANSWERS = ("yes", "no", "unsure")
LONG_SIDE = 1344                    # pixels of the longer side of a picture sent to the model
MARGIN = 28

SYSTEM = """You are shown one area of a construction or architectural drawing. A grid is laid over it: columns A to D from left
to right (named in the top margin), rows 1 to 4 from top to bottom (named in the left margin). A cell is named by its column
and row, for example B3.

You are asked whether this area shows one thing. It is shown if it is drawn (by its shape or its usual drawing symbol) or if
words written on the drawing name it. Answer "yes" only if you can see it and name the cells it is in. Answer "no" if this
area does not show it. Answer "unsure" if you cannot tell. Most things you are asked about may well be absent: do not assume a
thing is there because drawings like this one often have it.
Reply with JSON only: {"answer": "yes" | "no" | "unsure", "cells": [cell names, empty unless yes]}."""

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string", "enum": list(ANSWERS)},
                                           "cells": {"type": "array", "items": {"type": "string", "enum": CELLS}}},
          "required": ["answer", "cells"]}


def render_area(pdf_path, page_number: int, box, long_side: int = LONG_SIDE):
    """The picture of one area of a page. ``box``: fractions of the page (x0, y0, x1, y1), y down; ``page_number`` from 1."""
    import pymupdf
    from PIL import Image

    with pymupdf.open(pdf_path) as doc:
        page = doc[page_number - 1]
        r = page.rect
        clip = pymupdf.Rect(r.width * box[0], r.height * box[1], r.width * box[2], r.height * box[3])
        zoom = long_side / max(clip.width, clip.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def with_grid(picture) -> bytes:
    """The picture as PNG with the labelled grid: faint lines over it, names in a white margin so they cover nothing."""
    from PIL import Image, ImageDraw

    w, h = picture.size
    canvas = Image.new("RGB", (w + MARGIN, h + MARGIN), "white")
    canvas.paste(picture, (MARGIN, MARGIN))
    draw = ImageDraw.Draw(canvas)
    for c in range(COLUMNS + 1):
        x = MARGIN + min(w - 1, round(w * c / COLUMNS))
        draw.line([(x, 0), (x, h + MARGIN)], fill=(150, 190, 255), width=1)
        if c < COLUMNS:
            draw.text((MARGIN + w * (c + 0.5) / COLUMNS - 4, 8), chr(65 + c), fill=(0, 60, 200))
    for r in range(ROWS + 1):
        y = MARGIN + min(h - 1, round(h * r / ROWS))
        draw.line([(0, y), (w + MARGIN, y)], fill=(150, 190, 255), width=1)
        if r < ROWS:
            draw.text((10, MARGIN + h * (r + 0.5) / ROWS - 6), str(r + 1), fill=(0, 60, 200))
    out = io.BytesIO()
    canvas.save(out, "PNG")
    return out.getvalue()


def cell_box(cell: str, within=(0.0, 0.0, 1.0, 1.0)) -> tuple[float, float, float, float]:
    """A cell as fractions of the area. ``within``: the tile the grid was drawn on, itself in fractions of the area."""
    col, row = ord(cell[0]) - 65, int(cell[1:]) - 1
    w, h = within[2] - within[0], within[3] - within[1]
    return (within[0] + w * col / COLUMNS, within[1] + h * row / ROWS,
            within[0] + w * (col + 1) / COLUMNS, within[1] + h * (row + 1) / ROWS)


def tiles(n: int = 2, overlap: float = 0.1) -> list[tuple[float, float, float, float]]:
    """``n`` by ``n`` tiles of an area (fractions), each grown by ``overlap`` of a tile so a thing on a seam is whole in one."""
    step, grow = 1.0 / n, overlap / n / 2
    return [(max(0.0, c * step - grow), max(0.0, r * step - grow), min(1.0, (c + 1) * step + grow),
             min(1.0, (r + 1) * step + grow)) for r in range(n) for c in range(n)]


def tile_page_box(area, tile) -> tuple[float, float, float, float]:
    """A tile of an area as fractions of the page."""
    w, h = area[2] - area[0], area[3] - area[1]
    return (area[0] + w * tile[0], area[1] + h * tile[1], area[0] + w * tile[2], area[1] + h * tile[3])


def ask(client, png: bytes, what: str) -> dict:
    """{"answer": yes | no | unsure | error, "cells": [...]}. A yes that names no cell is only "unsure": it points nowhere."""
    try:
        out = client.complete(SYSTEM, f"Does this area of the drawing show {what}?", SCHEMA, images=(png,))
    except Exception as exc:  # noqa: BLE001 - no answer is no evidence
        return {"answer": "error", "cells": [], "why": str(exc)[:200]}
    answer = out.get("answer") if isinstance(out, dict) else None
    if answer not in ANSWERS:
        return {"answer": "error", "cells": [], "why": "no usable answer"}
    cells = [c for c in dict.fromkeys(out.get("cells") or []) if c in CELLS] if answer == "yes" else []
    if answer == "yes" and not cells:
        return {"answer": "unsure", "cells": [], "why": "yes without a place"}
    return {"answer": answer, "cells": cells}


def combine(parts: list[tuple[tuple, dict]]) -> dict:
    """Tile answers into one: yes if any tile says yes (with those places), else unsure if any is unsure, else no."""
    places = [cell_box(c, tile) for tile, got in parts if got["answer"] == "yes" for c in got["cells"]]
    kinds = {got["answer"] for _, got in parts}
    answer = "yes" if places else "error" if kinds == {"error"} else "unsure" if kinds & {"unsure", "error"} else "no"
    return {"answer": answer, "places": places}


def overlaps(a, b) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])
