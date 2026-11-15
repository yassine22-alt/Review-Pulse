"""Stress test of room finding when walls are missed, on a public dataset with true rooms (ResPlan, CC BY 4.0).

    python scripts/room_stress.py [--n 150] [--gaps 0,2,4,8] [--seed 3]

Real drawings lose walls: a wall drawn as two thin lines is missed, a glazed partition is not recognised. This test imitates that
on plans whose true rooms are known. For each plan, the true walls are the barrier; then `g` random discs (radius 0.6 to 1.0 m)
are cut out of the walls, leaving gaps. A room name is written at the centre of every true room, as a drawing would. Rooms are
found with and without the label-seeded split (perception/seeded.py) and scored against the true spaces (an open plan living
room and kitchen with no wall between them is one true space): precision, recall and F1 at IoU 0.5.

Doors are kept, so the test isolates one failure: walls that are not there. Nothing is tuned on this data.
"""

from __future__ import annotations

import argparse
import random
from collections import defaultdict
from pathlib import Path

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from reviewpulse.eval.adapters.resplan import ROOM_KEYS, _parts, load, plan_scale
from reviewpulse.eval.matching import match_polygons
from reviewpulse.perception.rooms import detect_rooms
from reviewpulse.schema import Element, Prov, Sheet, TextItem


def truth_spaces(plan: dict, barrier, mpu: float) -> list[Polygon]:
    truth = []
    for key in ROOM_KEYS:
        if key == "balcony":
            continue
        for poly in _parts(plan.get(key)):
            if poly.area * mpu * mpu >= 1.0:
                truth.append(poly)
    eps = 0.05 / mpu
    bar_eps = barrier.buffer(eps)
    parent = list(range(len(truth)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(truth)):
        for j in range(i + 1, len(truth)):
            shared = truth[i].buffer(eps).intersection(truth[j].buffer(eps))
            if not shared.is_empty and shared.difference(bar_eps).area > (0.3 / mpu) * eps:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(truth)):
        groups[find(i)].append(i)
    return [unary_union([truth[i] for i in g]).buffer(0) for g in groups.values()]


def labels_for(plan: dict, mpu: float) -> list[TextItem]:
    out = []
    for key, rtype in ROOM_KEYS.items():
        if key == "balcony":
            continue
        for k, poly in enumerate(_parts(plan.get(key))):
            if poly.area * mpu * mpu < 1.0:
                continue
            p = poly.representative_point()
            h = 0.25 / mpu
            out.append(TextItem(id=f"{key}{k}", text=rtype.upper(), bbox=(p.x - 2 * h, p.y - h / 2, p.x + 2 * h, p.y + h / 2),
                                height=h, kind="room_label", norm=rtype, prov=Prov(source="user", stage="stress")))
    return out


def run(plan: dict, gaps: int, rng: random.Random, seeded: bool) -> tuple[int, int, int]:
    """(true positives, predicted rooms, true spaces)."""
    walls = unary_union(_parts(plan.get("wall")))
    doors, windows, front = _parts(plan.get("door")), _parts(plan.get("window")), _parts(plan.get("front_door"))
    mpu = plan_scale(plan, doors + front)
    full = unary_union([walls] + doors + windows + front)
    cut = walls
    if gaps and not walls.is_empty:
        pts = []
        for g in getattr(walls, "geoms", [walls]):
            pts += [Point(c) for c in list(g.exterior.coords)[:: max(1, len(g.exterior.coords) // 40)]]
        for p in rng.sample(pts, min(gaps, len(pts))):
            cut = cut.difference(p.buffer(rng.uniform(0.6, 1.0) / mpu))
    barrier = unary_union([cut] + doors + windows + front)

    def el(i, poly, cls):
        return Element(id=f"{cls}{i}", cls=cls, geom=[tuple(c) for c in poly.exterior.coords[:-1]],
                       prov=Prov(source="user", stage="stress"))

    openings = [el(i, d, "door") for i, d in enumerate(doors + front)] + [el(i, w, "window") for i, w in enumerate(windows)]
    sheet = Sheet(id=f"s{plan['id']}", source_file="x", mode="vector", coord_unit="drawing_unit", width=1, height=1,
                  texts=labels_for(plan, mpu))
    rooms, _e, _w = detect_rooms(sheet, [], [], openings, mpu, True, barrier=barrier, seeded=seeded)
    spaces = truth_spaces(plan, full, mpu)
    mr = match_polygons([Polygon(r.polygon, r.holes) for r in rooms], spaces, 0.5)
    tp = len(mr.pred_to_true())
    return tp, len(rooms), len(spaces)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--gaps", default="0,2,4,8")
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()

    plans = load(Path("data"))
    rng0 = random.Random(args.seed)
    sample = rng0.sample(plans, min(args.n, len(plans)))
    print(f"{len(sample)} ResPlan plans, a room name at every true room, walls cut by g random gaps\n")
    print(f"{'gaps':>4} | {'plain':^26} | {'with label seeds':^26}")
    print(f"{'':>4} | {'P':>6}{'R':>7}{'F1':>7}{'rooms':>6} | {'P':>6}{'R':>7}{'F1':>7}{'rooms':>6}")
    for g in [int(x) for x in args.gaps.split(",")]:
        row = []
        for seeded in (False, True):
            rng = random.Random(args.seed * 1000 + g)          # the same gaps for both arms
            tp = pred = true = 0
            for plan in sample:
                try:
                    a, b, c = run(plan, g, rng, seeded)
                except Exception:  # noqa: BLE001 - a malformed plan is skipped in both arms alike
                    continue
                tp, pred, true = tp + a, pred + b, true + c
            p, r = tp / max(pred, 1), tp / max(true, 1)
            row.append((p, r, 2 * p * r / max(p + r, 1e-9), pred))
        print(f"{g:>4} | " + " | ".join(f"{p:6.3f}{r:7.3f}{f:7.3f}{n:6d}" for p, r, f, n in row), flush=True)


if __name__ == "__main__":
    main()
