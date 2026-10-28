"""R12 - Tags and schedules.

Schedules are read from the text grid (works the same for DXF and PDF, ruled or
not): a header row with at least two vocabulary cells, then rows aligned under
the header columns. Tags are assigned to doors/windows with Hungarian matching
so an element never gets two tags.
"""

from __future__ import annotations

import re

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Point, Polygon

from ..schema import Element, Sheet, TextItem
from .text_classify import normalise, tag_key

HEADER_VOCAB = {
    "tag": r"^(repere|rep|mark|tag|id|no|n°)\.?$",
    "width": r"^(largeur|larg|l|width|w)\.?(\s*\((m|cm|mm)\))?$",
    "height": r"^(hauteur|haut|h|height)\.?(\s*\((m|cm|mm)\))?$",
    "type": r"^(type|nature|materiau|designation)$",
    "qty": r"^(nb|nbre|qte|quantite|qty)\.?$",
    "sill": r"^(allege|sill)(\s*\((m|cm|mm)\))?$",
}
TAG_ASSOC_M = 1.5
TAG_PREFIX_CLS = {"P": "door", "D": "door", "F": "window", "W": "window", "V": "window"}


def _centre(t: TextItem):
    return ((t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2)


def _header_field(text: str) -> str | None:
    t = normalise(text)
    for f, pat in HEADER_VOCAB.items():
        if re.match(pat, t):
            return f
    return None


def _num(s: str) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", s)
    return float(m.group(0).replace(",", ".")) if m else None


def _unit_from_header(text: str) -> str | None:
    m = re.search(r"\((m|cm|mm)\)", normalise(text))
    return m.group(1) if m else None


def _to_m(v: float, unit: str | None, col_max: float) -> float:
    if unit == "cm":
        return v / 100
    if unit == "mm":
        return v / 1000
    if unit == "m":
        return v
    if col_max <= 3.5:
        return v
    if col_max <= 350:
        return v / 100
    return v / 1000


def find_schedules(sheet: Sheet) -> tuple[list[dict], list[tuple]]:
    """Return (schedules, table boxes)."""
    texts = [t for t in sheet.texts if t.text.strip()]
    heads = [(t, _header_field(t.text)) for t in texts]
    heads = [(t, f) for t, f in heads if f]
    schedules, boxes = [], []
    used = set()
    for t0, _f in heads:
        if t0.id in used:
            continue
        h = t0.height or (t0.bbox[3] - t0.bbox[1]) or 1.0
        y0 = _centre(t0)[1]
        hdr = [(t, f) for t, f in heads if abs(_centre(t)[1] - y0) <= 0.6 * h]
        fields = {f for _, f in hdr}
        if "tag" not in fields or len(fields) < 2:
            continue
        for t, _ in hdr:
            used.add(t.id)
        cols = sorted(((_centre(t)[0], f, t) for t, f in hdr), key=lambda c: c[0])
        xs = [c[0] for c in cols]
        spacing = min(np.diff(xs)) if len(xs) > 1 else 10 * h
        below = [t for t in texts if _centre(t)[1] < y0 - 0.6 * h and t.id not in used
                 and xs[0] - spacing / 2 <= _centre(t)[0] <= xs[-1] + spacing / 2]
        below.sort(key=lambda t: -_centre(t)[1])
        rows_txt: list[list[TextItem]] = []
        last_y, pitch = y0, None
        for t in below:
            y = _centre(t)[1]
            if rows_txt and abs(y - _centre(rows_txt[-1][0])[1]) <= 0.6 * h:
                rows_txt[-1].append(t)
                continue
            gap = last_y - y
            if pitch is not None and gap > 3 * pitch:
                break
            if pitch is None and gap > 6 * h:
                break
            pitch = gap if pitch is None else pitch
            rows_txt.append([t])
            last_y = y
        raw_rows = []
        for r in rows_txt:
            cells: dict[str, str] = {}
            for t in r:
                i = int(np.argmin([abs(_centre(t)[0] - x) for x in xs]))
                cells[cols[i][1]] = (cells.get(cols[i][1], "") + " " + t.text).strip()
            tag = cells.get("tag")
            if not tag or not re.match(r"^[A-Za-z]{1,2}[ -]?\d{1,3}$", tag.strip()):
                if raw_rows:
                    break
                continue
            raw_rows.append(cells)
            for t in r:
                used.add(t.id)
                t.prov.evidence["in_table"] = True
        if not raw_rows:
            continue
        units = {c[1]: _unit_from_header(c[2].text) for c in cols}
        out_rows = []
        for f in ("width", "height", "sill"):
            vals = [_num(r.get(f, "")) for r in raw_rows if r.get(f)]
            units[f + "_max"] = max([v for v in vals if v is not None], default=0)
        for r in raw_rows:
            row = {"tag": tag_key(r["tag"])}
            for f in ("width", "height", "sill"):
                if r.get(f) and _num(r[f]) is not None:
                    row[f + "_m"] = round(_to_m(_num(r[f]), units.get(f), units[f + "_max"]), 4)
            if r.get("type"):
                row["type"] = r["type"]
            if r.get("qty") and _num(r["qty"]) is not None:
                row["qty"] = int(_num(r["qty"]))
            out_rows.append(row)
        for t, _ in hdr:
            t.prov.evidence["in_table"] = True
        all_t = [t for t, _ in hdr] + [t for r in rows_txt for t in r]
        bx = (min(t.bbox[0] for t in all_t), min(t.bbox[1] for t in all_t),
              max(t.bbox[2] for t in all_t), max(t.bbox[3] for t in all_t))
        pad = h
        bx = (bx[0] - pad, bx[1] - pad, bx[2] + pad, bx[3] + 3 * pad)
        name = "doors" if all(r["tag"].startswith(("P", "D")) for r in out_rows) else \
            "windows" if all(r["tag"].startswith(("F", "W", "V")) for r in out_rows) else "openings"
        schedules.append({"name": name, "rows": out_rows, "bbox": bx})
        boxes.append(bx)
    # texts inside a table box belong to the table
    for t in sheet.texts:
        c = _centre(t)
        if any(b[0] <= c[0] <= b[2] and b[1] <= c[1] <= b[3] for b in boxes):
            t.prov.evidence["in_table"] = True
    return schedules, boxes


def associate_tags(sheet: Sheet, elements: list[Element], mpu: float, scale_known: bool = True) -> list[str]:
    """Hungarian assignment of tag texts to door/window elements. Returns warnings."""
    tags = [t for t in sheet.texts if t.kind == "tag" and not t.prov.evidence.get("in_table")]
    els = [e for e in elements if e.cls in ("door", "window", "opening")]
    if not tags or not els:
        return []
    max_d = TAG_ASSOC_M / mpu if scale_known else 30.0
    BIG = 1e9
    cost = np.full((len(tags), len(els)), BIG)
    for i, t in enumerate(tags):
        want = TAG_PREFIX_CLS.get((t.norm or "?")[0])
        c = Point(_centre(t))
        for j, e in enumerate(els):
            if want and e.cls != want and not (want == "door" and e.cls == "opening"):
                continue
            d = Polygon(e.geom).distance(c)
            if d <= max_d:
                cost[i, j] = d
    r, c = linear_sum_assignment(cost)
    warnings = []
    matched = set()
    for i, j in zip(r, c):
        if cost[i, j] >= BIG:
            continue
        els[j].tag = tags[i].norm
        els[j].attrs["tag_text_id"] = tags[i].id
        matched.add(i)
    for i, t in enumerate(tags):
        if i not in matched:
            warnings.append(f"tag {t.norm} matched no door or window")
    return warnings
