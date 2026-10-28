"""Render one FloorPlanCAD tile coloured by wall outcome (for error analysis).

    python scripts/render_eval_tile.py data/raw/floorplancad/FloorPlanCAD/test/0101-0020.svg out.png

grey = other primitives, green = true wall found, red = false wall, blue = missed wall.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

from reviewpulse.annotate.text_classify import classify_items
from reviewpulse.core.geometry import arc_points
from reviewpulse.ingest.svg_reader import extract_svg
from reviewpulse.pipeline import build_model
from reviewpulse.schema import Scale


def main(svg: str, out: str, size: int = 1400) -> None:
    s = extract_svg(Path(svg), "x")
    classify_items(s.texts)
    s.scale = Scale(metres_per_unit=0.1, method="user", confidence=1.0)
    m = build_model(s)
    walls = {i for e in m.elements if e.cls == "wall" for i in e.member_ids}
    k = size / max(s.width, s.height)
    img = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(img)

    def P(q):
        return (q[0] * k, (s.height - q[1]) * k)

    for p in m.sheet.primitives:
        if p.hidden:
            continue
        gt = p.prov.evidence.get("gt", {}).get("semantic")
        pred = p.id in walls
        col = (0, 170, 0) if gt == 33 and pred else (220, 0, 0) if pred else (0, 90, 255) if gt == 33 else (190, 190, 190)
        w = 3 if col != (190, 190, 190) else 1
        if p.kind in ("line", "polyline") and len(p.pts) >= 2:
            d.line([P(q) for q in p.pts], fill=col, width=w)
        elif p.kind == "polygon" and len(p.pts) >= 3:
            d.line([P(q) for q in p.pts + p.pts[:1]], fill=col, width=w)
        elif p.kind in ("arc", "circle") and p.center:
            a0, a1 = (p.a0, p.a1) if p.kind == "arc" else (0, 360)
            d.line([P(q) for q in arc_points(p.center, p.radius, a0, a1, 16)], fill=col, width=w)
    img.save(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
