"""J7 - Self-contained HTML report: rendered page (base64 PNG), inline SVG overlay,
one card per finding, filter by verdict, highlight on click. No external files."""

from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

from ..schema import BuildingModel, Finding
from .anchor import anchor_point

DPI = 100
COL = {"FAIL": "#d32f2f", "WARNING": "#f29900", "PASS": "#2e7d32", "NOT_EVALUATED": "#757575"}


def _backdrop(model: BuildingModel):
    """(png bytes, width px, height px, sheet->px function)."""
    sheet = model.sheet
    src = Path(sheet.source_file)
    if src.suffix.lower() == ".pdf" and src.exists():
        import pymupdf

        page = pymupdf.open(src)[sheet.page]
        pix = page.get_pixmap(dpi=DPI)
        H = sheet.height
        k = DPI / 25.4

        def to_px(p):
            return (p[0] * k, (H - p[1]) * k)

        return pix.tobytes("png"), pix.width, pix.height, to_px
    from .debug_png import _bounds, _Canvas

    pts = [q for p in sheet.primitives if not p.hidden for q in p.pts] or [(0, 0), (1, 1)]
    from .debug_png import sheet_png  # noqa: F401 - same drawing code

    c = _Canvas(_bounds(pts), max_px=1600)
    from ..core.geometry import arc_points

    for p in sheet.primitives:
        if p.hidden:
            continue
        if p.kind in ("line", "polyline"):
            c.d.line([c.p(q) for q in p.pts], fill=(90, 90, 90), width=1)
        elif p.kind == "polygon" and len(p.pts) >= 3:
            c.d.polygon([c.p(q) for q in p.pts], outline=(90, 90, 90), fill=(170, 170, 170) if p.filled else None)
        elif p.kind in ("arc", "circle") and p.center:
            a0, a1 = (p.a0, p.a1) if p.kind == "arc" else (0, 360)
            c.d.line([c.p(q) for q in arc_points(p.center, p.radius, a0, a1, 24)], fill=(90, 90, 90), width=1)
    for t in sheet.texts:
        c.d.text(c.p((t.bbox[0], t.bbox[3])), t.text, fill=(60, 60, 140))
    buf = io.BytesIO()
    c.img.save(buf, format="PNG")
    return buf.getvalue(), c.img.width, c.img.height, c.p


def _svg_group(f: Finding, i: int, to_px, anchor) -> str:
    col = COL.get(f.verdict, "#555")
    parts = []
    for poly in f.evidence.get("polygons", []):
        if len(poly) >= 3:
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (to_px(p) for p in poly))
            parts.append(f'<polygon points="{pts}" fill="{col}" fill-opacity="0.18" stroke="{col}" stroke-width="1.5"/>')
    for pl in f.evidence.get("polylines", []):
        if len(pl) >= 2:
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (to_px(p) for p in pl))
            parts.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5" stroke-dasharray="6 3"/>')
    for p in f.evidence.get("points", []):
        if p:
            x, y = to_px(p)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="none" stroke="{col}" stroke-width="2"/>')
    if anchor is not None:
        x, y = to_px(anchor)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="white" stroke="{col}" stroke-width="2"/>'
                     f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="11" text-anchor="middle" fill="{col}" '
                     f'font-weight="700">{i}</text>')
    return f'<g class="f v-{f.verdict}" data-i="{i}">{"".join(parts)}</g>'


def write_html(models: list[BuildingModel], findings: list[Finding], out: Path) -> Path:
    sections = []
    cards = []
    n = 0
    for model in models:
        png, w, h, to_px = _backdrop(model)
        b64 = base64.b64encode(png).decode()
        groups = []
        for f in findings:
            if f.evidence.get("sheet") not in (None, model.sheet.id):
                continue
            n += 1
            groups.append(_svg_group(f, n, to_px, anchor_point(f, model) if f.verdict in ("FAIL", "WARNING") else None))
            src = f.source or {}
            clause = " ".join(str(x) for x in (src.get("doc"), src.get("clause")) if x)
            cards.append(
                f'<article class="card v-{f.verdict}" data-i="{n}">'
                f'<header><span class="badge" style="background:{COL.get(f.verdict)}">{f.verdict}</span>'
                f'<span class="badge tier">{f.tier}</span><b>{n}. {html.escape(f.rule_id)}</b>'
                f'<span class="sev">{f.severity}</span></header>'
                f'<p>{html.escape(f.message)}</p>'
                + (f'<p class="vals">detected <b>{html.escape(f.detected or "-")}</b> &middot; required '
                   f'<b>{html.escape(f.required or "-")}</b></p>' if (f.detected or f.required) else "")
                + (f'<p class="src">{html.escape(clause)}</p>' if clause else "")
                + (f'<p class="src">dismissed: {html.escape(str(f.evidence["dismissed"]))}</p>' if f.evidence.get("dismissed") else "")
                + "</article>")
        sections.append(
            f'<section class="sheet"><h2>{html.escape(model.sheet.id)} &middot; {model.sheet.sheet_type} &middot; '
            f'tier {model.tier} &middot; scale {model.sheet.scale.method}</h2>'
            f'<div class="plan"><svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
            f'<image href="data:image/png;base64,{b64}" width="{w}" height="{h}"/>{"".join(groups)}</svg></div></section>')
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.verdict] = counts.get(f.verdict, 0) + 1
    buttons = "".join(f'<button data-v="{v}">{v} ({counts.get(v, 0)})</button>'
                      for v in ("FAIL", "WARNING", "NOT_EVALUATED", "PASS"))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ReviewPulse Report</title>
<style>
:root{{--bg:#fafafa;--fg:#1d1d1f;--card:#fff;--line:#e2e2e2}}
@media (prefers-color-scheme: dark){{:root{{--bg:#151515;--fg:#eee;--card:#202020;--line:#333}}}}
body{{margin:0;font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg)}}
main{{display:grid;grid-template-columns:minmax(0,3fr) minmax(280px,1.2fr);gap:16px;padding:16px}}
@media (max-width:900px){{main{{grid-template-columns:1fr}}}}
.plan svg{{width:100%;height:auto;background:#fff;border:1px solid var(--line)}}
.card{{background:var(--card);border:1px solid var(--line);border-left:5px solid #888;padding:8px 10px;margin:0 0 8px;cursor:pointer}}
.card.v-FAIL{{border-left-color:{COL['FAIL']}}}.card.v-WARNING{{border-left-color:{COL['WARNING']}}}
.card.v-PASS{{border-left-color:{COL['PASS']}}}.card.sel{{outline:2px solid #1976d2}}
.badge{{color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-right:6px}}.tier{{background:#455a64}}
.sev{{float:right;opacity:.7}}.vals,.src{{margin:4px 0;font-size:12px;opacity:.85}}
nav{{padding:12px 16px;border-bottom:1px solid var(--line)}}nav button{{margin-right:6px}}
nav button.off{{opacity:.4}}g.f.hide,.card.hide{{display:none}}g.f.hl *{{stroke-width:4}}
h2{{font-size:15px}}#list{{max-height:90vh;overflow:auto}}
</style></head><body>
<nav><b>ReviewPulse</b> &nbsp; {len(findings)} findings &nbsp; {buttons}</nav>
<main><div>{''.join(sections)}</div><div id="list">{''.join(cards)}</div></main>
<script>
const off=new Set(["PASS"]);
function apply(){{document.querySelectorAll('.card,g.f').forEach(e=>{{const v=[...e.classList].find(c=>c.startsWith('v-')).slice(2);e.classList.toggle('hide',off.has(v));}});
document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('off',off.has(b.dataset.v)));}}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{{off.has(b.dataset.v)?off.delete(b.dataset.v):off.add(b.dataset.v);apply();}});
document.querySelectorAll('.card').forEach(c=>c.onclick=()=>{{document.querySelectorAll('.sel,.hl').forEach(e=>e.classList.remove('sel','hl'));
c.classList.add('sel');const g=document.querySelector('g.f[data-i="'+c.dataset.i+'"]');if(g){{g.classList.add('hl');g.scrollIntoView({{block:'center',behavior:'smooth'}});}}}});
apply();
</script></body></html>"""
    out.write_text(page, encoding="utf-8")
    _ = json
    return out
