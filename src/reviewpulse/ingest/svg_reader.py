"""SVG extraction (vector exports, FloorPlanCAD-style datasets).

Paths (M/L/H/V/A/C/S/Q/T/Z, absolute and relative), lines, polylines, polygons, rects, circles and
ellipses become primitives in drawing units, y flipped to point up. Group/element ``transform``
attributes are composed. Dataset annotations found on elements (FloorPlanCAD ``semanticId`` /
``instanceId``) are kept in ``prov.evidence['gt']`` for evaluation only - the pipeline never reads them.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

from ..core.ids import IdFactory
from ..schema import Primitive, Prov, Sheet, TextItem
from .pdf_backend import _bezier, bezier_to_arc

_NUM = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
_TOKEN = re.compile(rf"[MmLlHhVvAaCcSsQqTtZz]|{_NUM}")


def _parse_transform(s: str | None) -> np.ndarray:
    m = np.eye(3)
    if not s:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s):
        v = [float(x) for x in re.findall(_NUM, args)]
        t = np.eye(3)
        if name == "matrix" and len(v) == 6:
            t = np.array([[v[0], v[2], v[4]], [v[1], v[3], v[5]], [0, 0, 1]])
        elif name == "translate":
            t[0, 2], t[1, 2] = v[0], (v[1] if len(v) > 1 else 0.0)
        elif name == "scale":
            t[0, 0], t[1, 1] = v[0], (v[1] if len(v) > 1 else v[0])
        elif name == "rotate":
            a = math.radians(v[0])
            r = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
            if len(v) == 3:
                c1, c2 = np.eye(3), np.eye(3)
                c1[:2, 2], c2[:2, 2] = (v[1], v[2]), (-v[1], -v[2])
                r = c1 @ r @ c2
            t = r
        m = m @ t
    return m


def _arc_center(p0, p1, rx, ry, phi, large, sweep):
    """SVG endpoint arc -> (center, rx, ry, theta0, dtheta) in the same (y-down) frame (SVG spec F.6.5)."""
    if rx == 0 or ry == 0:
        return None
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cp * dx + sp * dy, -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    co = math.sqrt(max(num / den, 0.0)) if den else 0.0
    if large == sweep:
        co = -co
    cx1, cy1 = co * rx * y1 / ry, -co * ry * x1 / rx
    cx = cp * cx1 - sp * cy1 + (p0[0] + p1[0]) / 2
    cy = sp * cx1 + cp * cy1 + (p0[1] + p1[1]) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t0 = ang(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = ang((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    return (cx, cy), rx, ry, t0, dt


class _Builder:
    def __init__(self, sheet_id: str, height: float):
        self.ids = IdFactory(sheet_id)
        self.H = height
        self.prims: list[Primitive] = []

    def P(self, m: np.ndarray, x: float, y: float) -> tuple[float, float]:
        q = m @ np.array([x, y, 1.0])
        return (round(float(q[0]), 6), round(float(self.H - q[1]), 6))

    def add(self, kind, ev, pts=(), **kw):
        geom = list(pts) or [kw.get("center"), kw.get("radius")]
        ev = dict(ev)
        color = ev.pop("_stroke", None)
        self.prims.append(Primitive(id=self.ids(kind, geom), kind=kind, pts=list(pts), color=color,
                                    prov=Prov(source="vector", stage="svg_extract", evidence=ev), **kw))


def _emit_arc(b: _Builder, m, ev, layer, p0, p1, rx, ry, phi, large, sweep):
    res = _arc_center(p0, p1, rx, ry, math.radians(phi), large, sweep)
    if res is None:
        b.add("line", ev, [b.P(m, *p0), b.P(m, *p1)], layer=layer)
        return
    (cx, cy), rx2, ry2, t0, dt = res
    n = max(4, int(abs(math.degrees(dt)) / 7.5))
    pts = []
    for i in range(n + 1):
        t = t0 + dt * i / n
        x = cx + rx2 * math.cos(math.radians(phi)) * math.cos(t) - ry2 * math.sin(math.radians(phi)) * math.sin(t)
        y = cy + rx2 * math.sin(math.radians(phi)) * math.cos(t) + ry2 * math.cos(math.radians(phi)) * math.sin(t)
        pts.append(b.P(m, x, y))
    # a circular arc (equal radii, uniform transform) is stored as an ARC, else as a polyline
    c = b.P(m, cx, cy)
    r = math.dist(c, pts[0])
    if abs(rx2 - ry2) <= 1e-6 * max(rx2, 1) and all(abs(math.dist(c, q) - r) <= 1e-3 * max(r, 1e-9) for q in pts):
        a_s = math.degrees(math.atan2(pts[0][1] - c[1], pts[0][0] - c[0])) % 360
        a_e = math.degrees(math.atan2(pts[-1][1] - c[1], pts[-1][0] - c[0])) % 360
        mid = pts[len(pts) // 2]
        a_m = math.degrees(math.atan2(mid[1] - c[1], mid[0] - c[0])) % 360
        a0, a1 = (a_s, a_e) if (a_m - a_s) % 360 <= (a_e - a_s) % 360 else (a_e, a_s)
        b.add("arc", ev, center=c, radius=round(r, 6), a0=round(a0, 4), a1=round(a1, 4), layer=layer)
    else:
        b.add("polyline", ev, pts, layer=layer)


def _path(b: _Builder, d: str, m, ev, layer):
    toks = _TOKEN.findall(d or "")
    i, cmd = 0, None
    cur = start = (0.0, 0.0)
    last_ctrl = None
    poly: list[tuple] = []

    def flush(closed=False):
        nonlocal poly
        if len(poly) >= 2:
            pts = [b.P(m, *q) for q in poly]
            if closed and len(pts) >= 3:
                b.add("polygon", ev, pts, layer=layer)
            else:
                for a, c in zip(pts, pts[1:]):
                    if a != c:
                        b.add("line", ev, [a, c], layer=layer)
        poly = []

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if poly and poly[-1] != start:
                    poly.append(start)
                flush(closed=True)
                cur = start
                continue
        rel = cmd.islower()
        C = cmd.upper()
        ox, oy = cur if rel else (0.0, 0.0)
        if C == "M":
            flush()
            cur = (num() + ox, num() + oy)
            start = cur
            poly = [cur]
            cmd = "l" if rel else "L"
        elif C == "L":
            cur = (num() + ox, num() + oy)
            poly.append(cur)
        elif C == "H":
            cur = (num() + ox, cur[1])
            poly.append(cur)
        elif C == "V":
            cur = (cur[0], num() + (cur[1] if rel else 0.0))
            poly.append(cur)
        elif C == "A":
            rx, ry, phi, large, sweep = num(), num(), num(), int(num()), int(num())
            end = (num() + ox, num() + oy)
            flush()
            _emit_arc(b, m, ev, layer, cur, end, rx, ry, phi, large, sweep)
            cur = end
            poly = [cur]
        elif C in "CSQT":
            if C == "C":
                c1 = (num() + ox, num() + oy)
                c2 = (num() + ox, num() + oy)
            elif C == "S":
                c1 = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_ctrl else cur
                c2 = (num() + ox, num() + oy)
            elif C == "Q":
                q = (num() + ox, num() + oy)
                c1, c2 = q, q
            else:
                q = (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1]) if last_ctrl else cur
                c1, c2 = q, q
            end = (num() + ox, num() + oy)
            ctrl = [b.P(m, *cur), b.P(m, *c1), b.P(m, *c2), b.P(m, *end)]
            flush()
            arc = bezier_to_arc(ctrl)
            if arc:
                c, r, a0, a1 = arc
                b.add("arc", ev, center=(round(c[0], 6), round(c[1], 6)), radius=round(r, 6),
                      a0=round(a0, 4), a1=round(a1, 4), layer=layer)
            else:
                b.add("polyline", ev, [tuple(round(v, 6) for v in _bezier(*ctrl, k / 8)) for k in range(9)],
                      layer=layer)
            last_ctrl = c2
            cur = end
            poly = [cur]
            continue
        else:
            i += 1
        last_ctrl = None
    flush()


def _stroke_of(el) -> str | None:
    """Stroke colour as #rrggbb (attribute or style); colour is the layer proxy of many exports."""
    v = el.get("stroke")
    if v is None:
        m = re.search(r"stroke\s*:\s*([^;]+)", el.get("style") or "")
        v = m.group(1).strip() if m else None
    if not v or v == "none":
        return None
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", v)
    if m:
        return "#" + "".join(f"{int(x):02x}" for x in m.groups())
    return v.lower()


def _nums(v: str | None) -> list[float]:
    return [float(x) for x in re.findall(_NUM, v or "")]


def _text_items(el, m: np.ndarray, b, tids) -> list[TextItem]:
    """One text item per positioned run (the <text> itself or each <tspan> carrying x/y). Position,
    size and reading direction go through the element transform; per-glyph x lists give the width."""
    size = (_nums(el.get("font-size")) or [1.0])[0]
    runs = []
    x0, y0 = (_nums(el.get("x")) or [0.0])[0], (_nums(el.get("y")) or [0.0])[0]
    if el.text and el.text.strip():
        runs.append((el.text.strip(), [x0], y0, size))
    for ts in el:
        if not isinstance(ts.tag, str) or ts.tag.split("}")[-1] != "tspan":
            continue
        t = "".join(ts.itertext()).strip()
        if not t:
            continue
        xs = _nums(ts.get("x")) or [x0]
        y = (_nums(ts.get("y")) or [y0])[0]
        runs.append((t, xs, y, (_nums(ts.get("font-size")) or [size])[0]))
        x0, y0 = xs[0], y
    out = []
    for t, xs, y, h in runs:
        adv = (xs[-1] - xs[0]) / (len(xs) - 1) if len(xs) > 1 else 0.6 * h
        w = (xs[-1] - xs[0]) + adv if len(xs) > 1 else 0.6 * h * len(t)
        # glyphs sit on the baseline and rise by the font size (SVG y down)
        corners = [b.P(m, xs[0], y), b.P(m, xs[0] + w, y), b.P(m, xs[0] + w, y - h), b.P(m, xs[0], y - h)]
        cx, cy = [c[0] for c in corners], [c[1] for c in corners]
        ux, uy = corners[1][0] - corners[0][0], corners[1][1] - corners[0][1]
        rot = math.degrees(math.atan2(uy, ux)) % 360
        height = math.dist(corners[0], corners[3])
        bbox = (min(cx), min(cy), max(cx), max(cy))
        out.append(TextItem(id=tids("text", t, *bbox), text=t, bbox=bbox, rotation_deg=round(rot, 3),
                            height=round(height, 6), prov=Prov(source="vector", stage="svg_extract")))
    return out


def extract_svg(path: Path, sheet_id: str) -> Sheet:
    from lxml import etree

    root = etree.parse(str(path)).getroot()
    vb = [float(v) for v in re.findall(_NUM, root.get("viewBox") or "")]
    W = vb[2] if len(vb) == 4 else float(re.findall(_NUM, root.get("width") or "0")[0] or 0)
    H = vb[3] if len(vb) == 4 else float(re.findall(_NUM, root.get("height") or "0")[0] or 0)
    b = _Builder(sheet_id, H)
    texts: list[TextItem] = []
    tids = IdFactory(sheet_id + ":t")

    def walk(el, m, stroke=None):
        tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
        m = m @ _parse_transform(el.get("transform"))
        stroke = _stroke_of(el) or stroke
        ev = {"_stroke": stroke} if stroke else {}
        if el.get("semanticId") is not None:
            ev["gt"] = {"semantic": int(el.get("semanticId")), "instance": int(el.get("instanceId", -1))}
        layer = el.get("layer") or el.get("{http://www.inkscape.org/namespaces/inkscape}label")
        if tag == "path":
            _path(b, el.get("d"), m, ev, layer)
        elif tag == "line":
            f = [float(el.get(k, 0)) for k in ("x1", "y1", "x2", "y2")]
            b.add("line", ev, [b.P(m, f[0], f[1]), b.P(m, f[2], f[3])], layer=layer)
        elif tag in ("polyline", "polygon"):
            v = [float(x) for x in re.findall(_NUM, el.get("points") or "")]
            pts = [b.P(m, v[k], v[k + 1]) for k in range(0, len(v) - 1, 2)]
            if tag == "polygon" and len(pts) >= 3:
                b.add("polygon", ev, pts, layer=layer)
            else:
                for a, c in zip(pts, pts[1:]):
                    b.add("line", ev, [a, c], layer=layer)
        elif tag == "rect":
            x, y, w, h = (float(el.get(k, 0)) for k in ("x", "y", "width", "height"))
            b.add("polygon", ev, [b.P(m, x, y), b.P(m, x + w, y), b.P(m, x + w, y + h), b.P(m, x, y + h)], layer=layer)
        elif tag in ("circle", "ellipse"):
            cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
            rx = float(el.get("r", el.get("rx", 0)) or 0)
            ry = float(el.get("r", el.get("ry", rx)) or rx)
            pts = [b.P(m, cx + rx * math.cos(t), cy + ry * math.sin(t))
                   for t in np.linspace(0, 2 * math.pi, 33)[:-1]]
            c = b.P(m, cx, cy)
            if abs(rx - ry) < 1e-9:
                b.add("circle", ev, center=c, radius=round(math.dist(c, pts[0]), 6), layer=layer)
            else:
                b.add("polygon", ev, pts, layer=layer)
        elif tag == "text":
            texts.extend(_text_items(el, m, b, tids))
            return                      # its tspans are part of the text, not drawing
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch, m, stroke)

    walk(root, np.eye(3))
    return Sheet(id=sheet_id, source_file=str(path), mode="vector", coord_unit="drawing_unit", width=W, height=H,
                 primitives=b.prims, texts=texts, warnings=["SVG has no units: scale must be recovered"])
