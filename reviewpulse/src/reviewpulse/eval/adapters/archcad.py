"""ArchCAD adapter (huggingface.co/datasets/jackluoluo/ArchCAD, CC BY-NC 4.0, gated).

41,097 slices of real architectural and structural CAD drawings, each a 14 m x 14 m area
(980 x 980 units, so 1 unit = 14/980 m: median single-door arc radius 57.4 units = 0.82 m), every
primitive labelled with a semantic class and, for countable objects, an instance.

Read from the JSON modality, not the SVG: the JSON keeps the CAD entity (LINE, ARC, CIRCLE,
ELLIPSE), its line type, colour and arc direction, in y-up drawing coordinates. The slices carry no
text, no layers and (measured on 500) a single colour and line weight, so only geometry tells a
wall from anything else: a test of drawings exported without drawing conventions.

There is no official split. Each slice is assigned by a hash of its name (stable, independent of
how many files are present): 5% test, 5% val, 90% train. Evaluation uses slices that contain walls
(a third of ArchCAD is structural: beams, piles, rebar, with no wall to find).

ArchCAD has no window class; glazing is labelled ``Glass`` (19), which is what a plan draws in a
window opening. It is scored as the window group. Glass is "uncountable" (no instance id), so each
group of glass primitives that touch, or run side by side as the panes of one window symbol, is one
window instance.
"""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from functools import lru_cache
from pathlib import Path

from ...core.ids import IdFactory
from ...schema import Primitive, Prov, Scale, Sheet
from .primitive_scoring import aggregate, score_model

SIZE = 980.0
UNIT_M = 14.0 / SIZE
CLASSES = {0: "axis & grid", 1: "single door", 2: "double door", 3: "parent-child door", 4: "other door",
           5: "elevator", 6: "staircase", 7: "sink", 8: "urinal", 9: "toilet", 10: "bathtub", 11: "squat toilet",
           12: "other fixtures", 13: "drain", 14: "table", 15: "chair", 16: "bed", 17: "sofa", 18: "hole",
           19: "glass", 20: "wall", 21: "concrete column", 22: "steel column", 23: "concrete beam",
           24: "steel beam", 25: "parking space", 26: "foundation", 27: "pile", 28: "rebar", 29: "fire hydrant",
           100: "others"}
GROUPS = {"wall": {20}, "door": {1, 2, 3, 4}, "window": {19}}
SPLITS = (("test", 0.05), ("val", 0.05), ("train", 0.90))
ELLIPSE_SEGMENTS = 32
GLASS_JOIN = 1.0           # units (1.4 cm): glass strokes of one window touch
# ... or run side by side: a window symbol draws 2-4 parallel panes a few cm apart, joined only by
# jamb lines labelled wall. Measured: touching alone split one 0.8 m window into 4 "windows".
WINDOW_DEPTH_M = 0.4       # panes of one window lie within a wall thickness of each other
PARALLEL_DEG = 5.0
SIDE_BY_SIDE = 0.5         # share of the shorter pane covered by the other along their direction


def split_of(name: str) -> str:
    u = int(hashlib.sha1(name.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    acc = 0.0
    for split, share in SPLITS:
        acc += share
        if u < acc:
            return split
    return SPLITS[-1][0]


@lru_cache(maxsize=1)
def _zip(path: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(path)


def archive(data_dir: Path) -> Path:
    p = data_dir / "raw" / "archcad" / "data" / "json.zip"
    if not p.exists():
        raise NotImplementedError("ArchCAD not found: python scripts/fetch_datasets.py archcad")
    return p


def names(data_dir: Path, split: str) -> list[str]:
    z = _zip(str(archive(data_dir)))
    return sorted(Path(n).stem for n in z.namelist() if n.endswith(".json") and split_of(Path(n).stem) == split)


def entities(data_dir: Path, name: str) -> list[dict]:
    return json.loads(_zip(str(archive(data_dir))).read(f"json/{name}.json"))["entities"]


def _ellipse_pts(e: dict) -> list[tuple[float, float]]:
    cx, cy = e["center"]
    mx, my = e["major_axis"]
    r = e["ratio"]
    t0, t1 = e["start_param"], e["end_param"]
    if not e.get("is_ccw", True):
        t0, t1 = t1, t0
    sweep = (t1 - t0) % (2 * math.pi) or 2 * math.pi
    out = []
    for i in range(ELLIPSE_SEGMENTS + 1):
        t = t0 + sweep * i / ELLIPSE_SEGMENTS
        c, s = math.cos(t), math.sin(t)
        out.append((round(cx + c * mx - s * r * my, 6), round(cy + c * my + s * r * mx, 6)))
    return out


def to_sheet(ents: list[dict], name: str) -> Sheet:
    """CAD entities -> Sheet in drawing units; labels go to ``prov.evidence['gt']`` (evaluation only)."""
    ids = IdFactory(name)
    prims = []
    for k, e in enumerate(ents):
        t = e.get("type")
        lt = str(e.get("linetype") or "")
        rgb = e.get("rgb")
        common = dict(color="#{:02x}{:02x}{:02x}".format(*rgb) if rgb else None,
                      dashed=bool(lt) and lt.lower() not in ("continuous", "bylayer", "byblock"),
                      prov=Prov(source="vector", stage="archcad_json",
                                evidence={"entity": k, "gt": {"semantic": int(e["semantic"]),
                                                               "instance": e.get("instance", -1)}}))
        if t == "LINE":
            a, b = tuple(e["start"]), tuple(e["end"])
            if a != b:
                prims.append(Primitive(id=ids("line", [a, b]), kind="line", pts=[a, b], **common))
        elif t == "ARC":
            a0, a1 = float(e["start_angle"]), float(e["end_angle"])
            if e.get("direction") == 1:          # clockwise from start_angle to end_angle
                a0, a1 = a1, a0
            c = tuple(e["center"])
            prims.append(Primitive(id=ids("arc", c, e["radius"], a0), kind="arc", center=c,
                                   radius=float(e["radius"]), a0=a0 % 360, a1=a1 % 360, **common))
        elif t == "CIRCLE":
            c = tuple(e["center"])
            prims.append(Primitive(id=ids("circle", c, e["radius"]), kind="circle", center=c,
                                   radius=float(e["radius"]), **common))
        elif t == "ELLIPSE":
            pts = _ellipse_pts(e)
            prims.append(Primitive(id=ids("polyline", pts), kind="polyline", pts=pts, **common))
    _glass_instances(prims)
    return Sheet(id=name, source_file=f"archcad:{name}", mode="vector", coord_unit="drawing_unit",
                 width=SIZE, height=SIZE, primitives=prims)


def _glass_instances(prims: list[Primitive]) -> None:
    """Give unlabelled glass primitives an instance per connected group (one window each)."""
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    from ...core.geometry import arc_points, side_by_side

    glass = [p for p in prims if p.prov.evidence["gt"]["semantic"] in GROUPS["window"]
             and p.prov.evidence["gt"]["instance"] in (-1, None)]
    if not glass:
        return
    geoms = []
    for p in glass:
        if p.kind == "arc":
            geoms.append(LineString(arc_points(p.center, p.radius, p.a0, p.a1, 8)))
        elif p.kind == "circle":
            geoms.append(Point(p.center).buffer(p.radius).boundary)
        else:
            geoms.append(LineString(p.pts))
    parent = list(range(len(glass)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tree = STRtree(geoms)
    depth = WINDOW_DEPTH_M / UNIT_M
    for i, g in enumerate(geoms):
        for j in tree.query(g, predicate="dwithin", distance=GLASS_JOIN):
            parent[find(int(j))] = find(i)
        if glass[i].kind != "line":
            continue
        for j in tree.query(g, predicate="dwithin", distance=depth):
            j = int(j)
            if j != i and glass[j].kind == "line" and side_by_side(glass[i].pts, glass[j].pts, PARALLEL_DEG, SIDE_BY_SIDE):
                parent[find(j)] = find(i)
    for i, p in enumerate(glass):
        p.prov.evidence["gt"]["instance"] = f"glass_{find(i)}"


def load_sheet(data_dir: Path, name: str, scale_mode: str = "oracle") -> Sheet:
    s = to_sheet(entities(data_dir, name), name)
    if scale_mode == "oracle":
        s.scale = Scale(metres_per_unit=UNIT_M, method="user", confidence=1.0)
    return s


def has_walls(data_dir: Path, name: str) -> bool:
    return any(e.get("semantic") in GROUPS["wall"] for e in entities(data_dir, name))


def score_file(data_dir: Path, name: str, scale_mode: str = "oracle", learned: bool = False) -> dict:
    from ...pipeline import build_model

    return score_model(build_model(load_sheet(data_dir, name, scale_mode), learned=learned), GROUPS, learned)


def run(n: int, split: str, data_dir: Path, scale_mode: str = "oracle", learned: bool = False) -> tuple[dict, list]:
    pool = names(data_dir, split)
    step = max(1, len(pool) // (3 * n))           # spread over the split; a third has no walls
    chosen = [nm for nm in pool[::step] if has_walls(data_dir, nm)][:n]
    results = []
    for nm in chosen:
        try:
            results.append((nm, score_file(data_dir, nm, scale_mode, learned)))
        except Exception as e:  # noqa: BLE001 - a crash is a result
            results.append((nm, e))
    out, worst = aggregate(results, learned)
    scaled = out.pop("_scaled")
    out = {"split": split, "scale_mode": scale_mode, "selection": "slices with walls", **out}
    if scale_mode != "oracle":
        out["scale_estimated_on"] = f"{scaled}/{len(chosen)} slices"
    return out, worst
