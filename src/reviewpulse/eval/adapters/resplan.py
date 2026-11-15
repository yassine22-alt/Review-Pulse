"""E2 - ResPlan adapter: R10 (rooms + room graph) scored on true walls, doors and windows.

ResPlan (CC BY 4.0) stores, per plan, Shapely geometries for walls, doors, windows, the front
door and room types. Following the plan's oracle rule, the barrier given to R10 is built from the
TRUE walls and openings, so this scores the room logic alone: free-space components, the closing
step, opening probes and the exit edge.

Truth door edges are computed here from the geometry (a door touching two rooms joins them; the
front door joins its room to EXIT) - the dataset's own helper script is not executed.
The pickle is read with an allow-list unpickler (Shapely, NumPy and builtin types only), because a
pickle from the internet can otherwise execute code.
"""

from __future__ import annotations

import io
import json
import math
import pickle
from collections import defaultdict
from pathlib import Path

from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

ROOM_KEYS = {"living": "living", "bedroom": "bedroom", "bathroom": "bathroom", "kitchen": "kitchen",
             "storage": "storage", "stair": "stairs", "balcony": "terrace"}


class _SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        top = module.split(".")[0]
        if top in ("shapely", "numpy", "builtins", "collections", "copyreg", "_codecs"):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"blocked {module}.{name} while loading ResPlan")


_CACHE: dict = {}


def load(data_dir: Path) -> list[dict]:
    p = data_dir / "raw" / "resplan" / "ResPlan.pkl"
    if not p.exists():
        raise NotImplementedError("ResPlan not found: python scripts/fetch_datasets.py resplan")
    if str(p) not in _CACHE:
        _CACHE[str(p)] = _SafeUnpickler(io.BytesIO(p.read_bytes())).load()
    return _CACHE[str(p)]


def _parts(g) -> list[Polygon]:
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [x for x in getattr(g, "geoms", []) if isinstance(x, Polygon)]


DOOR_PRIOR_M = 0.85


def plan_scale(plan: dict, doors: list[Polygon]) -> float:
    """Metres per unit. Plans are drawn at varying scales and the area metadata is wrong on a
    minority of them (0.009 or 0.75 m/unit against a typical 0.045), so doors are the ruler:
    0.85 m over the median door width; the area metadata only when a plan has no doors."""
    widths = []
    for d in doors:
        c = list(d.minimum_rotated_rectangle.exterior.coords)
        widths.append(max(math.dist(c[0], c[1]), math.dist(c[1], c[2])))
    if widths:
        widths.sort()
        return DOOR_PRIOR_M / widths[len(widths) // 2]
    inner = unary_union(_parts(plan.get("inner")))
    return math.sqrt(float(plan["net_area"]) / inner.area) if inner.area and plan.get("net_area") else 0.045


def score_plan(plan: dict) -> dict:
    from ...perception.rooms import detect_rooms
    from ...schema import Element, Prov, Sheet
    from ..matching import match_polygons

    walls = unary_union(_parts(plan.get("wall")))
    doors = _parts(plan.get("door"))
    windows = _parts(plan.get("window"))
    front = _parts(plan.get("front_door"))
    mpu = plan_scale(plan, doors + front)
    barrier = unary_union([walls] + doors + windows + front)

    def el(i, poly, cls, tag):
        return Element(id=f"{tag}{i}", cls=cls, geom=[tuple(c) for c in poly.exterior.coords[:-1]],
                       prov=Prov(source="user", stage="resplan_truth"))

    openings = [el(i, d, "door", "d") for i, d in enumerate(doors)] + \
               [el(i, d, "door", "fd") for i, d in enumerate(front)] + \
               [el(i, w, "window", "w") for i, w in enumerate(windows)]
    sheet = Sheet(id=f"resplan_{plan['id']}", source_file="ResPlan.pkl", mode="vector", coord_unit="drawing_unit",
                  width=1, height=1)
    rooms, edges, _warn = detect_rooms(sheet, [], [], openings, mpu, True, barrier=barrier)

    # truth spaces: rooms joined without any wall between them (open-plan living + kitchen) are one
    # physical space; balconies are outdoor (no enclosing walls) and scored apart
    truth = []
    outdoor = 0
    for key, rtype in ROOM_KEYS.items():
        for poly in _parts(plan.get(key)):
            if poly.area * mpu * mpu < 1.0:
                continue
            if key == "balcony":
                outdoor += 1
                continue
            truth.append([poly, {rtype}])
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
            shared = truth[i][0].buffer(eps).intersection(truth[j][0].buffer(eps))
            if not shared.is_empty and shared.difference(bar_eps).area > (0.3 / mpu) * eps:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(truth)):
        groups[find(i)].append(i)
    spaces = [(f"s{k}", unary_union([truth[i][0] for i in g]).buffer(0)) for k, g in enumerate(groups.values())]
    mr = match_polygons([Polygon(r.polygon, r.holes) for r in rooms], [sp[1] for sp in spaces], 0.5)
    p2t = {rooms[i].id: spaces[j][0] for i, j in mr.pred_to_true().items()}

    # truth door edges from geometry: inner doors join two spaces; the front door is the EXIT;
    # a door with one space and the outdoors behind it (balcony) goes OUTSIDE, which is not an exit
    # a door connects whatever lies on its two sides: probe just beyond both long faces
    te, exits_true = set(), 0
    reach = 0.30 / mpu

    def side_spaces(d):
        mrr = d.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)[:4]
        e0 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
        e1 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
        short = e0 if math.hypot(*e0) < math.hypot(*e1) else e1
        L = math.hypot(*short) or 1.0
        nx_, ny_ = short[0] / L, short[1] / L
        c = d.centroid
        found = []
        for sgn in (1, -1):
            q = Point(c.x + sgn * nx_ * (L / 2 + reach), c.y + sgn * ny_ * (L / 2 + reach))
            hit = next((sp[0] for sp in spaces if sp[1].buffer(1e-6).contains(q)), "OUT")
            found.append(hit)
        return found

    for i, d in enumerate(doors + front):
        a, b = side_spaces(d)
        if a == b:
            continue
        te.add(frozenset((a, b)))
        if i >= len(doors):
            exits_true += 1
    out = {"EXIT": "OUT", "EXTERIOR": "OUT"}
    pe = {frozenset((out.get(p2t.get(e.a, e.a), p2t.get(e.a, e.a)), out.get(p2t.get(e.b, e.b), p2t.get(e.b, e.b))))
          for e in edges if e.kind == "door"}
    exits_pred = sum(1 for e in edges if e.kind == "door" and "EXIT" in (e.a, e.b))
    return {"rooms": (mr.tp, mr.n_pred, mr.n_true), "edges": (len(pe & te), len(pe), len(te)), "mpu": mpu,
            "exits": (exits_true, exits_pred), "outdoor_spaces": outdoor}


def run(n: int, data_dir: Path, oracle: str = "walls,doors,windows") -> tuple[dict, list]:
    plans = load(data_dir)
    split = data_dir / "raw" / "resplan" / "split.json"
    ids = None
    if split.exists():
        sp = json.loads(split.read_text())
        ids = set(sp.get("test", [])) if isinstance(sp, dict) else None
    pool = [p for p in plans if ids is None or p.get("id") in ids] or plans
    step = max(1, len(pool) // n)
    sample = pool[::step][:n]
    agg = defaultdict(lambda: [0, 0, 0])
    worst = []
    for plan in sample:
        try:
            r = score_plan(plan)
        except Exception as e:  # noqa: BLE001 - a crash is a result
            worst.append((0.0, plan.get("id"), f"crash: {e!r}"[:160]))
            continue
        for k in ("rooms", "edges"):
            for j in range(3):
                agg[k][j] += r[k][j]
        agg["exits"][0] += r["exits"][0]
        agg["exits"][1] += r["exits"][1]
        agg["outdoor"][0] += r["outdoor_spaces"]
        tp, npred, ntrue = r["rooms"]
        f1 = 2 * tp / (npred + ntrue) if npred + ntrue else 1.0
        worst.append((round(f1, 3), plan.get("id"), {"rooms": r["rooms"], "edges": r["edges"]}))

    def prf(t):
        tp, npred, ntrue = t
        p = tp / npred if npred else 0.0
        r_ = tp / ntrue if ntrue else 0.0
        return {"precision": round(p, 4), "recall": round(r_, 4), "f1": round(2 * p * r_ / (p + r_), 4) if p + r_ else 0.0,
                "tp": tp, "pred": npred, "true": ntrue}

    res = {"plans": len(sample), "split": "test" if ids else "all", "oracle_inputs": oracle,
           "spaces_iou50": prf(agg["rooms"]), "door_edges": prf(agg["edges"]),
           "exits": {"front_doors_true": agg["exits"][0], "doors_labelled_exit": agg["exits"][1]},
           "outdoor_spaces_not_scored": agg["outdoor"][0]}
    return res, sorted(worst, key=lambda x: x[0])[:10]
