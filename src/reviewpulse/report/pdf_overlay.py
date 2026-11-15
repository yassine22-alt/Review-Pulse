"""J7 - Annotated PDF.

PDF source: draw on the original page. Sheet space -> visible page points
(inverse of the R2 transform) -> unrotated page via ``derotation_matrix``,
because drawing calls expect the unrotated page.
DXF source: draw the sheet's primitives on a new page, then the findings.
FAIL red, WARNING amber, PASS not drawn; numbered markers; summary page.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..core.geometry import arc_points
from ..schema import BuildingModel, Finding
from .anchor import anchor_point

MM = 25.4 / 72
COLOURS = {"FAIL": (0.85, 0.1, 0.1), "WARNING": (0.95, 0.6, 0.0), "NOT_EVALUATED": (0.5, 0.5, 0.5)}


def _page_for(doc_out, model: BuildingModel):
    """Return (page, to_page) where to_page maps sheet space to unrotated page points."""
    import pymupdf

    sheet = model.sheet
    src = Path(sheet.source_file)
    if src.suffix.lower() == ".pdf" and src.exists():
        srcdoc = pymupdf.open(src)
        doc_out.insert_pdf(srcdoc, from_page=sheet.page, to_page=sheet.page)
        page = doc_out[-1]
        H = page.rect.height
        der = page.derotation_matrix

        def to_page(pt):
            return pymupdf.Point(pt[0] / MM, H - pt[1] / MM) * der

        return page, to_page
    # vector backdrop for DXF / other sources
    pts = [q for p in sheet.primitives if not p.hidden for q in p.pts] or [(0, 0), (1, 1)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    W, Hh = 1190.0, 842.0                             # A3 landscape in points
    m = 40.0
    k = min((W - 2 * m) / max(x1 - x0, 1e-9), (Hh - 2 * m - 60) / max(y1 - y0, 1e-9))
    page = doc_out.new_page(width=W, height=Hh)

    def to_page(pt):
        return pymupdf.Point(m + (pt[0] - x0) * k, Hh - m - (pt[1] - y0) * k)

    shape = page.new_shape()
    for p in sheet.primitives:
        if p.hidden:
            continue
        if p.kind in ("line", "polyline") and len(p.pts) >= 2:
            shape.draw_polyline([to_page(q) for q in p.pts])
        elif p.kind == "polygon" and len(p.pts) >= 3:
            shape.draw_polyline([to_page(q) for q in p.pts + p.pts[:1]])
        elif p.kind in ("arc", "circle") and p.center:
            a0, a1 = (p.a0, p.a1) if p.kind == "arc" else (0, 360)
            shape.draw_polyline([to_page(q) for q in arc_points(p.center, p.radius, a0, a1, 24)])
    shape.finish(color=(0.25, 0.25, 0.25), width=0.4)
    for t in sheet.texts:
        try:
            page.insert_text(to_page((t.bbox[0], t.bbox[1])), t.text, fontsize=max(4, (t.height or 0) * k * 0.9),
                             color=(0.2, 0.2, 0.5))
        except Exception:  # noqa: BLE001 - a bad glyph must not stop the report
            pass
    page.insert_text((m, 25), f"{src.name} (rendered from {sheet.coord_unit}, scale {sheet.scale.method})",
                     fontsize=10)
    return page, to_page


def _draw_evidence(page, to_page: Callable, f: Finding, n: int, anchor) -> None:
    col = COLOURS.get(f.verdict, (0.4, 0.4, 0.4))
    ev = f.evidence
    shape = page.new_shape()
    for poly in ev.get("polygons", []):
        if len(poly) >= 3:
            shape.draw_polyline([to_page(p) for p in list(poly) + [poly[0]]])
    shape.finish(color=col, fill=col, fill_opacity=0.18, width=1.2)
    shape.commit()
    shape = page.new_shape()
    for pl in ev.get("polylines", []):
        if len(pl) >= 2:
            shape.draw_polyline([to_page(p) for p in pl])
    shape.finish(color=col, width=1.8, dashes="[4 2] 0")
    shape.commit()
    for p in ev.get("points", []):
        if p:
            page.draw_circle(to_page(p), 4, color=col, width=1.5)
    if anchor is not None:
        c = to_page(anchor)
        page.draw_circle(c, 7, color=col, fill=(1, 1, 1), width=1.5)
        page.insert_text((c.x - 3.5 if n < 10 else c.x - 6, c.y + 3), str(n), fontsize=8, color=col)


def write_annotated_pdf(models: list[BuildingModel], findings: list[Finding], out: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    numbered = []
    for model in models:
        page, to_page = _page_for(doc, model)
        mine = [f for f in findings if f.evidence.get("sheet") in (None, model.sheet.id)]
        for f in mine:
            if f.verdict not in ("FAIL", "WARNING") or f.evidence.get("dismissed"):
                continue
            numbered.append(f)
            _draw_evidence(page, to_page, f, len(numbered), anchor_point(f, model))
    # summary pages
    lines = [f"ReviewPulse findings - {len(findings)} total"]
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.verdict] = counts.get(f.verdict, 0) + 1
    lines.append(", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    lines.append("")
    for i, f in enumerate(numbered, start=1):
        src = f.source.get("clause") or f.source.get("doc", "")
        lines.append(f"{i:>3}. [{f.verdict}] {f.rule_id} ({f.severity}, {f.tier}) {f.message}")
        if f.detected or f.required:
            lines.append(f"       detected {f.detected or '-'} / required {f.required or '-'}   source: {src}")
    ne = [f for f in findings if f.verdict == "NOT_EVALUATED"]
    if ne:
        lines += ["", "Not evaluated:"] + [f"   {f.rule_id}: {f.message}" for f in ne]
    dismissed = [f for f in findings if f.evidence.get("dismissed")]
    if dismissed:
        lines += ["", "Dismissed by the reviewer:"] + [f"   {f.rule_id}: {f.evidence['dismissed']}" for f in dismissed]
    per_page = 60
    for start in range(0, len(lines), per_page):
        page = doc.new_page(width=595, height=842)
        page.insert_textbox(pymupdf.Rect(36, 36, 559, 806), "\n".join(lines[start:start + per_page]),
                            fontsize=8, fontname="helv")
    doc.save(out)
    return out
