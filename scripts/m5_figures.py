"""Figures for docs/progress/M5_vector_learned.md (writes docs/progress/img/m5/).

    python scripts/m5_figures.py [walls] [prov]

1. A FloorPlanCAD test drawing coloured by wall outcome, rules only vs the default pass (rules +
   learned classifier, fused): among the first test tiles with at least 3 doors, the one where the
   default gains most.
2. Generated plan 5005 as a PDF (walls drawn as polylines): rooms with the provenance defect
   reproduced (every line of a path reads the last line's classifier call) vs the fixed reader.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "progress" / "img" / "m5"
TEST = ROOT / "data" / "raw" / "floorplancad" / "FloorPlanCAD" / "test"
MIN_DOORS = 3                # the walls figure shows a floor plan (tile with at least this many doors)
GREEN, RED, BLUE, GREY = (0, 160, 0), (220, 0, 0), (0, 90, 255), (195, 195, 195)
ROOM_FILL = [(255, 214, 165), (189, 224, 254), (202, 255, 191), (255, 198, 255), (253, 255, 182),
             (155, 246, 255), (255, 173, 173), (210, 210, 255)]


def _font(size=22):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _caption(img: Image.Image, text: str) -> Image.Image:
    out = Image.new("RGB", (img.width, img.height + 44), "white")
    out.paste(img, (0, 44))
    ImageDraw.Draw(out).text((10, 10), text, fill="black", font=_font())
    return out


def _side(a: Image.Image, b: Image.Image) -> Image.Image:
    out = Image.new("RGB", (a.width + b.width + 20, max(a.height, b.height)), "white")
    out.paste(a, (0, 0))
    out.paste(b, (a.width + 20, 0))
    return out


def _canvas(sheet, size):
    k = size / max(sheet.width, sheet.height)
    img = Image.new("RGB", (round(sheet.width * k), round(sheet.height * k)), "white")
    return img, ImageDraw.Draw(img), (lambda q: (q[0] * k, (sheet.height - q[1]) * k))


def _draw_prim(d, P, p, col, w):
    from reviewpulse.core.geometry import arc_points

    if p.kind in ("line", "polyline") and len(p.pts) >= 2:
        d.line([P(q) for q in p.pts], fill=col, width=w)
    elif p.kind == "polygon" and len(p.pts) >= 3:
        d.line([P(q) for q in p.pts + p.pts[:1]], fill=col, width=w)
    elif p.kind in ("arc", "circle") and p.center:
        a0, a1 = (p.a0, p.a1) if p.kind == "arc" else (0, 360)
        d.line([P(q) for q in arc_points(p.center, p.radius, a0, a1, 16)], fill=col, width=w)


def _fpcad_model(svg: Path, learned: bool):
    from reviewpulse.annotate.text_classify import classify_items
    from reviewpulse.eval.adapters.floorplancad import UNIT_M
    from reviewpulse.ingest.svg_reader import extract_svg
    from reviewpulse.pipeline import build_model
    from reviewpulse.schema import Scale

    s = extract_svg(svg, svg.stem)
    classify_items(s.texts)
    s.scale = Scale(metres_per_unit=UNIT_M, method="user", confidence=1.0)
    return build_model(s, learned=learned)


def _wall_f1(r):
    w = r["wall"]
    return 2 * w["tp_len"] / (2 * w["tp_len"] + w["fp_len"] + w["fn_len"]) if w["tp_len"] else 0.0


def fig_walls(n_tiles: int = 12) -> None:
    from reviewpulse.eval.adapters.floorplancad import GROUPS, score_file

    files = sorted(TEST.glob("*.svg"))
    files = files[:: max(1, len(files) // 100)][:100][:n_tiles]      # the eval's own sample, first tiles
    best = None
    for f in files:
        rules, learned = score_file(f, "oracle", False), score_file(f, "oracle", True)
        gain = _wall_f1(learned) - _wall_f1(rules)
        print(f.name, round(_wall_f1(rules), 3), "->", round(_wall_f1(learned), 3), "doors", rules["door"]["true"],
              flush=True)
        # a floor plan, not a sheet of details: a big gain on a tile with almost no walls shows little
        if rules["door"]["true"] >= MIN_DOORS and (best is None or gain > best[0]):
            best = (gain, f, rules, learned)
    _gain, f, r_rules, r_learned = best
    panels = []
    for learned, r, name in ((False, r_rules, "rules only"), (True, r_learned, "default (rules + classifier, fused)")):
        m = _fpcad_model(f, learned)
        walls = {i for e in m.elements if e.cls == "wall" for i in e.member_ids}
        img, d, P = _canvas(m.sheet, 1100)
        for p in m.sheet.primitives:
            if p.hidden:
                continue
            gt = p.prov.evidence.get("gt", {}).get("semantic") in GROUPS["wall"]
            pred = p.id in walls
            col = GREEN if gt and pred else RED if pred else BLUE if gt else GREY
            _draw_prim(d, P, p, col, 1 if col == GREY else 3)
        dr = r["door"]
        panels.append(_caption(img, f"{name}: wall F1 {_wall_f1(r):.2f}, doors found {dr['found']}/{dr['true']}"))
    _side(*panels).save(OUT / "01_floorplancad_walls.png")
    print("walls figure from", f.name)


def _synth_model(pdf: str, shared: bool):
    """Default pass on a generated PDF; ``shared`` reproduces the defect: every primitive of one PDF
    path (same seqno) ends with the classifier call written last on that path."""
    import reviewpulse.perception.learned.classifier as C
    from reviewpulse.eval.cli import _model_from

    real = C.annotate_primitives

    def annotate_shared(model):
        n = real(model)
        last = {}
        for p in model.sheet.primitives:
            if "learned_wall" in p.prov.evidence and "seqno" in p.prov.evidence:
                last[p.prov.evidence["seqno"]] = p
        for p in model.sheet.primitives:
            src = last.get(p.prov.evidence.get("seqno"))
            if src is not None and "learned_wall" in p.prov.evidence:
                for k in ("p_wall", "p_door", "p_window", "learned_wall", "learned_class"):
                    p.prov.evidence[k] = src.prov.evidence[k]
        return n

    C.annotate_primitives = annotate_shared if shared else real
    try:
        return _model_from(pdf)
    finally:
        C.annotate_primitives = real


def fig_prov(seed: int = 5005) -> None:
    import os
    import tempfile

    from reviewpulse.synth.random_plan import random_plan

    os.environ["REVIEWPULSE_LEARNED"] = "1"
    panels = []
    with tempfile.TemporaryDirectory() as td:
        pdf = random_plan(td, seed=seed)["pdf"]
        for shared, name in ((True, "before: one evidence record per PDF path"),
                             (False, "after: one record per line")):
            m = _synth_model(pdf, shared)
            img, d, P = _canvas(m.sheet, 1000)
            for i, r in enumerate(m.rooms):
                d.polygon([P(q) for q in r.polygon], fill=ROOM_FILL[i % len(ROOM_FILL)])
            for p in m.sheet.primitives:
                if not p.hidden:
                    _draw_prim(d, P, p, GREY, 1)
            for e in m.elements:
                if e.cls == "wall" and len(e.geom) == 2:
                    d.line([P(q) for q in e.geom], fill=(40, 40, 40), width=4)
                elif e.attrs.get("candidate"):
                    d.line([P(q) for q in e.geom], fill=RED, width=6)
            n_rej = sum(1 for e in m.elements if e.attrs.get("candidate"))
            panels.append(_caption(img, f"{name}: {len(m.rooms)} rooms, {n_rej} walls rejected (red)"))
    _side(*panels).save(OUT / "02_pdf_shared_provenance.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    which = set(sys.argv[1:]) or {"walls", "prov"}
    if "prov" in which:
        fig_prov()
    if "walls" in which:
        fig_walls()
