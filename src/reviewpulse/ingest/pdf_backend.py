"""R2 - PDF vector extraction behind a ``PdfBackend`` interface (D2).

PyMuPDF is AGPL; keeping it behind this interface lets us switch to
pypdfium2 + pdfminer.six later without touching the rest of the pipeline.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol

from ..core.ids import IdFactory
from ..schema import Primitive, Prov, Sheet, TextItem

MM = 25.4 / 72
ARC_FIT_TOL = 0.005          # 4 sampled bezier points on one circle within 0.5% of the radius
DUP_TOL_MM = 0.01


class PdfBackend(Protocol):
    def extract(self, path: Path, page_no: int, sheet_id: str) -> Sheet: ...


def pdf_layers(doc) -> tuple[list[str], set[str]]:
    """(all optional-content group names, names of the hidden ones)."""
    names, hidden = [], set()
    try:
        ocgs = doc.get_ocgs() or {}
    except Exception:  # noqa: BLE001 - older builds
        ocgs = {}
    for _xref, info in ocgs.items():
        name = info.get("name")
        if not name:
            continue
        names.append(name)
        if info.get("on") is False:
            hidden.add(name)
    return sorted(set(names)), hidden


def _circle_3pts(p1, p2, p3):
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def _bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def bezier_to_arc(ctrl):
    """Return (center, radius, a0, a1) if the cubic bezier is a circular arc (sheet space, y up)."""
    p0, p1, p2, p3 = ctrl
    c = _circle_3pts(p0, _bezier(*ctrl, 0.5), p3)
    if c is None:
        return None
    (cx, cy), r = c
    if r <= 0:
        return None
    for t in (0.25, 0.75):
        q = _bezier(*ctrl, t)
        if abs(math.hypot(q[0] - cx, q[1] - cy) - r) > ARC_FIT_TOL * r:
            return None
    a_start = math.degrees(math.atan2(p0[1] - cy, p0[0] - cx)) % 360
    a_mid = math.degrees(math.atan2(_bezier(*ctrl, 0.5)[1] - cy, _bezier(*ctrl, 0.5)[0] - cx)) % 360
    a_end = math.degrees(math.atan2(p3[1] - cy, p3[0] - cx)) % 360
    # make the arc counter-clockwise
    if (a_mid - a_start) % 360 <= (a_end - a_start) % 360:
        return (cx, cy), r, a_start, a_end
    return (cx, cy), r, a_end, a_start


def _merge_arcs(arcs: list[tuple]) -> list[tuple]:
    """Join consecutive arcs on the same circle (a renderer may split one arc)."""
    out: list[list] = []
    for c, r, a0, a1 in arcs:
        if out:
            pc, pr, pa0, pa1 = out[-1]
            same = math.hypot(c[0] - pc[0], c[1] - pc[1]) < 0.01 * r and abs(r - pr) < 0.01 * r
            if same and abs(((a0 - pa1) + 180) % 360 - 180) < 0.5:
                out[-1][3] = a1
                continue
            if same and abs(((pa0 - a1) + 180) % 360 - 180) < 0.5:
                out[-1][2] = a0
                continue
        out.append([c, r, a0, a1])
    return [tuple(a) for a in out]


def _subpaths(items, to_sheet, tol: float = 0.01):
    """Split a path's items into continuous point chains; return [(points, closed)]."""
    rings: list[list] = []
    for it in items:
        op = it[0]
        if op == "l":
            seg = [to_sheet(it[1]), to_sheet(it[2])]
        elif op == "c":
            ctrl = [to_sheet(p) for p in it[1:5]]
            seg = [tuple(round(v, 3) for v in _bezier(*ctrl, i / 8)) for i in range(9)]
        elif op == "re":
            r = it[1]
            pts = [to_sheet(p) for p in (r.tl, r.tr, r.br, r.bl)]
            rings.append(pts + [pts[0]])
            continue
        elif op == "qu":
            q = it[1]
            pts = [to_sheet(p) for p in (q.ul, q.ur, q.lr, q.ll)]
            rings.append(pts + [pts[0]])
            continue
        else:
            continue
        if rings and math.dist(rings[-1][-1], seg[0]) <= tol and len(rings[-1]) > 1 \
                and math.dist(rings[-1][0], rings[-1][-1]) > tol:
            rings[-1].extend(seg[1:])
        else:
            rings.append(list(seg))
    out = []
    for r in rings:
        closed = len(r) >= 4 and math.dist(r[0], r[-1]) <= tol
        out.append((r[:-1] if closed else r, closed))
    return out


class PyMuPdfBackend:
    def extract(self, path: Path, page_no: int, sheet_id: str) -> Sheet:
        import pymupdf

        doc = pymupdf.open(path)
        page = doc[page_no]
        layers, hidden_layers = pdf_layers(doc)
        rot = page.rotation_matrix
        H = page.rect.height

        def to_sheet(pt):
            q = pymupdf.Point(pt) * rot
            return (round(q.x * MM, 3), round(H * MM - q.y * MM, 3))

        ids = IdFactory(sheet_id)
        prims: list[Primitive] = []
        seen: dict[tuple, Primitive] = {}

        def add(kind, pts=(), **kw):
            key = None
            if kind == "line":
                a, b = sorted(pts)
                key = ("l", round(a[0] / DUP_TOL_MM), round(a[1] / DUP_TOL_MM),
                       round(b[0] / DUP_TOL_MM), round(b[1] / DUP_TOL_MM))
                if key in seen:
                    seen[key].prov.evidence["dup_count"] = seen[key].prov.evidence.get("dup_count", 1) + 1
                    return
            geom = list(pts) or [kw.get("center"), kw.get("radius")]
            # one path gives many primitives: each needs its own provenance, or evidence written on one
            # (a rule tag, a classifier call) is silently written on all its siblings
            kw["prov"] = kw["prov"].model_copy(deep=True)
            p = Primitive(id=ids(kind, geom), kind=kind, pts=list(pts), **kw)
            prims.append(p)
            if key:
                seen[key] = p

        warnings: list[str] = []
        for path_ in page.get_drawings():
            layer = path_.get("layer")
            if layer in hidden_layers:     # get_drawings ignores visibility, so filter here
                continue
            width = (path_.get("width") or 0) * MM
            dashes = path_.get("dashes") or "[] 0"
            dashed = not dashes.strip().startswith("[]")
            fill = path_.get("fill")
            color = path_.get("color")
            color_s = "#" + "".join(f"{int(c * 255):02x}" for c in color) if color else None
            ev = {"seqno": path_.get("seqno")}
            if layer:
                ev["layer"] = layer
            common = dict(layer=layer, width=round(width, 3), color=color_s, dashed=dashed,
                          prov=Prov(source="vector", stage="pdf_extract", evidence=ev))
            arcs = []
            poly_pts = []
            if fill is not None:
                # filled paths (solid walls, columns, pilasters): every closed subpath is a filled polygon
                rest = []
                subs = _subpaths(path_["items"], to_sheet)
                for ring, closed in subs:
                    closed = closed or (bool(path_.get("closePath")) and len(subs) == 1)
                    if closed and len(ring) >= 3:
                        add("polygon", ring, filled=True, **common)
                    else:
                        rest.append(ring)
                for ring in rest:
                    for a, b in zip(ring, ring[1:]):
                        if a != b:
                            add("line", (a, b), **common)
                continue
            for it in path_["items"]:
                op = it[0]
                if op == "l":
                    a, b = to_sheet(it[1]), to_sheet(it[2])
                    if a != b:
                        add("line", (a, b), **common)
                elif op == "c":
                    ctrl = [to_sheet(p) for p in it[1:5]]
                    arc = bezier_to_arc(ctrl)
                    if arc:
                        arcs.append(arc)
                    else:
                        pts = [_bezier(*ctrl, i / 8) for i in range(9)]
                        add("polyline", [(round(x, 3), round(y, 3)) for x, y in pts], **common)
                elif op == "re":
                    r = it[1]
                    pts = [to_sheet(p) for p in (r.tl, r.tr, r.br, r.bl)]
                    poly_pts.append(pts)
                elif op == "qu":
                    q = it[1]
                    pts = [to_sheet(p) for p in (q.ul, q.ur, q.lr, q.ll)]
                    poly_pts.append(pts)
            for c, r, a0, a1 in _merge_arcs(arcs):
                add("arc", center=(round(c[0], 3), round(c[1], 3)), radius=round(r, 3),
                    a0=round(a0, 3), a1=round(a1, 3), **common)
            for pts in poly_pts:
                add("polygon", pts, filled=fill is not None, **common)

        texts = self._texts(page, sheet_id, to_sheet, rot)
        if len(texts) < OUTLINE_TEXT_MAX_WORDS and _glyph_like(prims) >= OUTLINE_MIN_GLYPHS:
            warnings.append("text_as_outlines: send the rendered page to OCR (R4/R13)")
        return Sheet(
            id=sheet_id, source_file=str(path), page=page_no, mode="vector", coord_unit="paper_mm",
            width=round(page.rect.width * MM, 3), height=round(page.rect.height * MM, 3),
            rotation=page.rotation, primitives=prims, texts=texts, layers=layers, warnings=warnings,
        )

    @staticmethod
    def _texts(page, sheet_id, to_sheet, rot) -> list[TextItem]:
        import pymupdf

        ids = IdFactory(sheet_id)
        rot0 = pymupdf.Matrix(rot)
        rot0.e = rot0.f = 0
        out = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"]).strip()
                if not text:
                    continue
                d = pymupdf.Point(line["dir"]) * rot0
                angle = round(math.degrees(math.atan2(-d.y, d.x)), 2) % 360
                x0, y0, x1, y1 = line["bbox"]
                corners = [to_sheet((x0, y0)), to_sheet((x1, y1)), to_sheet((x0, y1)), to_sheet((x1, y0))]
                xs = [c[0] for c in corners]
                ys = [c[1] for c in corners]
                bbox = (min(xs), min(ys), max(xs), max(ys))
                size = max(s["size"] for s in line["spans"]) * MM
                out.append(TextItem(id=ids("text", text, bbox), text=text, bbox=bbox, rotation_deg=angle,
                                    height=round(size, 3),
                                    prov=Prov(source="vector", stage="pdf_extract")))
        return out


OUTLINE_TEXT_MAX_WORDS = 20
OUTLINE_MIN_GLYPHS = 50
GLYPH_MM = 6.0


def _glyph_like(prims: list[Primitive]) -> int:
    """Small curved or many-vertex marks, the size of lettering: outlined text leaves hundreds."""
    n = 0
    for p in prims:
        if p.kind not in ("polyline", "polygon") or len(p.pts) < 4:
            continue
        xs, ys = [q[0] for q in p.pts], [q[1] for q in p.pts]
        if max(xs) - min(xs) <= GLYPH_MM and max(ys) - min(ys) <= GLYPH_MM:
            n += 1
    return n


def render_preview(path: Path, page_no: int, out_png: Path, dpi: int = 100) -> Path:
    import pymupdf

    doc = pymupdf.open(path)
    doc[page_no].get_pixmap(dpi=dpi).save(out_png)
    return out_png
