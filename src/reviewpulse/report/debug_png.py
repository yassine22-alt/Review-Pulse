"""Debug images: the extracted sheet and the detected rooms/elements (any sheet unit)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ..core.geometry import arc_points
from ..schema import BuildingModel, Sheet

ROOM_COLOURS = [(255, 224, 178), (200, 230, 201), (187, 222, 251), (248, 187, 208), (225, 190, 231),
                (255, 249, 196), (178, 235, 242), (215, 204, 200), (220, 237, 200), (255, 205, 210)]


class _Canvas:
    def __init__(self, bounds, max_px=1600, margin=20):
        x0, y0, x1, y1 = bounds
        w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        self.k = (max_px - 2 * margin) / max(w, h)
        self.x0, self.y1, self.m = x0, y1, margin
        self.img = Image.new("RGB", (int(w * self.k) + 2 * margin, int(h * self.k) + 2 * margin), "white")
        self.d = ImageDraw.Draw(self.img)

    def p(self, pt):
        return (self.m + (pt[0] - self.x0) * self.k, self.m + (self.y1 - pt[1]) * self.k)


def _bounds(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1, 1)


def sheet_png(sheet: Sheet, out: Path) -> Path:
    pts = [q for p in sheet.primitives if not p.hidden for q in p.pts] + \
          [p.center for p in sheet.primitives if p.center and not p.hidden]
    c = _Canvas(_bounds(pts))
    for p in sheet.primitives:
        if p.hidden:
            continue
        if p.kind in ("line", "polyline"):
            c.d.line([c.p(q) for q in p.pts], fill="black", width=1)
        elif p.kind == "polygon" and len(p.pts) >= 3:
            c.d.polygon([c.p(q) for q in p.pts], outline="black", fill=(160, 160, 160) if p.filled else None)
        elif p.kind == "arc":
            c.d.line([c.p(q) for q in arc_points(p.center, p.radius, p.a0, p.a1)], fill="black", width=1)
        elif p.kind == "circle":
            c.d.line([c.p(q) for q in arc_points(p.center, p.radius, 0, 360, 32)], fill="black", width=1)
    for t in sheet.texts:
        c.d.text(c.p((t.bbox[0], t.bbox[3])), t.text, fill=(0, 0, 160))
    c.img.save(out)
    return out


def rooms_png(model: BuildingModel, out: Path) -> Path:
    pts = [q for r in model.rooms for q in r.polygon] + [q for e in model.elements for q in e.geom]
    c = _Canvas(_bounds(pts))
    for i, r in enumerate(model.rooms):
        c.d.polygon([c.p(q) for q in r.polygon], fill=ROOM_COLOURS[i % len(ROOM_COLOURS)], outline="grey")
    for e in model.elements:
        if e.cls == "wall":
            w = max(2, int((e.thickness or 0) * c.k))
            c.d.line([c.p(q) for q in e.geom], fill=(40, 40, 40), width=w)
        elif e.cls == "other":
            c.d.line([c.p(q) for q in e.geom], fill=(200, 120, 0), width=1)
        elif e.cls == "column":
            c.d.polygon([c.p(q) for q in e.geom], fill=(40, 40, 40))
        elif e.cls in ("door", "window", "opening"):
            col = {"door": (0, 140, 0), "window": (0, 90, 220), "opening": (220, 0, 0)}[e.cls]
            c.d.polygon([c.p(q) for q in e.geom], outline=col, fill=col)
            if e.attrs.get("swing_polygon"):
                c.d.polygon([c.p(q) for q in e.attrs["swing_polygon"]], outline=col)
            if e.tag:
                c.d.text(c.p(e.geom[0]), e.tag, fill=col)
    for r in model.rooms:
        from shapely.geometry import Polygon

        cc = Polygon(r.polygon).representative_point()
        txt = f"{r.label or '?'}\n{r.area_m2:.2f} m2" if r.area_m2 else (r.label or "?")
        c.d.text(c.p((cc.x, cc.y)), txt, fill="black")
    c.img.save(out)
    return out
