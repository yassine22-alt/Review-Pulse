"""Render ResPlan truth (left) next to R10 output on true walls (right), for error analysis.

    python scripts/render_resplan.py 10585 5581 --out runs/resplan_dbg
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.ops import unary_union

from reviewpulse.eval.adapters.resplan import ROOM_KEYS, _parts, load, plan_scale
from reviewpulse.perception.rooms import detect_rooms
from reviewpulse.schema import Element, Prov, Sheet

COLS = {"living": (255, 220, 170), "bedroom": (200, 230, 200), "bathroom": (180, 210, 250),
        "kitchen": (250, 200, 220), "balcony": (225, 225, 225), "storage": (220, 200, 250), "stair": (240, 240, 180)}


def render(plan: dict, out: Path, k: float = 4.0) -> None:
    walls = unary_union(_parts(plan.get("wall")))
    doors, wins, fr = _parts(plan.get("door")), _parts(plan.get("window")), _parts(plan.get("front_door"))
    x0, y0, x1, y1 = unary_union([walls] + doors + wins + fr).bounds
    w, h = int((x1 - x0) * k), int((y1 - y0) * k)
    img = Image.new("RGB", (2 * w + 60, h + 40), "white")
    d = ImageDraw.Draw(img)

    def P(x, y, off=0):
        return ((x - x0) * k + 20 + off, (y1 - y) * k + 20)

    for key in ROOM_KEYS:
        for poly in _parts(plan.get(key)):
            d.polygon([P(*c) for c in poly.exterior.coords], fill=COLS.get(key, (240, 240, 200)), outline="grey")
    for poly in _parts(walls):
        d.polygon([P(*q) for q in poly.exterior.coords], fill="black")
    for poly, col in [(p, "green") for p in doors] + [(p, "red") for p in fr] + [(p, "blue") for p in wins]:
        d.polygon([P(*q) for q in poly.exterior.coords], fill=col)
    openings = [Element(id=f"d{i}", cls="door", geom=list(p.exterior.coords)[:-1],
                        prov=Prov(source="user", stage="t")) for i, p in enumerate(doors + fr)]
    sheet = Sheet(id="x", source_file="x", mode="vector", coord_unit="drawing_unit", width=1, height=1)
    rooms, _e, _w = detect_rooms(sheet, [], [], openings, plan_scale(plan, doors + fr), True,
                                 barrier=unary_union([walls] + doors + wins + fr))
    rnd = random.Random(1)
    for r in rooms:
        d.polygon([P(*q, off=w + 20) for q in r.polygon], fill=tuple(rnd.randint(140, 250) for _ in range(3)),
                  outline="black")
    d.text((22, 2), f"ResPlan {plan['id']}: truth", fill="black")
    d.text((w + 42, 2), f"R10 on true walls: {len(rooms)} rooms", fill="black")
    img.save(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+", type=int)
    ap.add_argument("--out", default="runs/resplan_dbg")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    by_id = {p["id"]: p for p in load(Path("data"))}
    for i in a.ids:
        render(by_id[i], out / f"resplan_{i}.png")
        print(out / f"resplan_{i}.png")


if __name__ == "__main__":
    main()
