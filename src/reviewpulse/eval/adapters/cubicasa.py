"""E2 - CubiCasa5K adapter (raster plans with SVG ground truth).

Layout: data/raw/cubicasa5k/cubicasa5k/<subset>/<id>/{F1_scaled.png, F1_original.png, model.svg}
plus train.txt / val.txt / test.txt listing "/<subset>/<id>/". The SVG coordinates are pixels of
F1_scaled.png (checked by overlay). Classes are read from the ``class`` attribute of each group:
"Wall" / "Wall External", "Door ...", "Window ...", "Column ...", "Space <Type>"; the first
<polygon> child of a group is its footprint. Openings lie inside wall polygons, so masks paint
doors and windows over walls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ...ingest.svg_reader import _parse_transform

SVG_NS = "{http://www.w3.org/2000/svg}"
CLASSES = ["background", "wall", "door", "window"]
ROOM_TYPES = {"Bedroom": "bedroom", "LivingRoom": "living", "Kitchen": "kitchen", "Bath": "bathroom",
              "Toilet": "wc", "Entry": "entry", "Storage": "storage", "Garage": "garage", "CarPort": "garage",
              "Outdoor": "terrace", "Room": "other", "DressingRoom": "storage", "Draughtroom": "other",
              "Lobby": "corridor", "Library": "office", "Sauna": "bathroom", "Undefined": "other",
              "Dining": "dining", "Hall": "corridor", "Corridor": "corridor", "UserDefined": "other"}


@dataclass
class Plan:
    path: Path
    size: tuple[int, int]                       # (width, height) of F1_scaled.png
    walls: list = field(default_factory=list)   # list of (N, 2) arrays, pixels, y down
    doors: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    rooms: list = field(default_factory=list)   # (type, (N, 2) array)


def root_dir(data_dir: Path) -> Path:
    return data_dir / "raw" / "cubicasa5k" / "cubicasa5k"


def split_ids(data_dir: Path, split: str) -> list[Path]:
    base = root_dir(data_dir)
    f = base / f"{split}.txt"
    if not f.exists():
        raise NotImplementedError("CubiCasa5K not found: python scripts/fetch_datasets.py cubicasa5k")
    return [base / ln.strip().strip("/") for ln in f.read_text().splitlines() if ln.strip()]


def _points(poly) -> np.ndarray:
    v = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", poly.get("points") or "")]
    return np.array(list(zip(v[::2], v[1::2])), float)


def parse(folder: Path) -> Plan:
    from lxml import etree
    from PIL import Image

    with Image.open(folder / "F1_scaled.png") as im:
        size = im.size
    plan = Plan(folder, size)
    root = etree.parse(str(folder / "model.svg")).getroot()

    def walk(el, m):
        m = m @ _parse_transform(el.get("transform"))
        cls = (el.get("class") or "").strip()
        head = cls.split(" ")[0] if cls else ""
        if head in ("Wall", "Door", "Window", "Column", "Space"):
            poly = el.find(f"{SVG_NS}polygon")
            if poly is not None:
                pts = _points(poly)
                if len(pts) >= 3:
                    hp = np.c_[pts, np.ones(len(pts))] @ m.T
                    pts = hp[:, :2]
                    if head == "Wall":
                        plan.walls.append(pts)
                    elif head == "Door":
                        plan.doors.append(pts)
                    elif head == "Window":
                        plan.windows.append(pts)
                    elif head == "Column":
                        plan.columns.append(pts)
                    else:
                        kind = cls.split(" ")[1] if len(cls.split(" ")) > 1 else "Undefined"
                        plan.rooms.append((ROOM_TYPES.get(kind, "other"), pts))
            if head in ("Door", "Window"):
                return          # their inner parts (panels, glass) are not separate objects
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch, m)

    walk(root, np.eye(3))
    return plan


def masks(plan: Plan, scale: float = 1.0) -> np.ndarray:
    """uint8 class mask (CLASSES order) at ``scale`` x F1_scaled size."""
    from PIL import Image, ImageDraw

    w, h = int(round(plan.size[0] * scale)), int(round(plan.size[1] * scale))
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    for cls_id, polys in ((1, plan.walls + plan.columns), (3, plan.windows), (2, plan.doors)):
        for p in polys:
            d.polygon([tuple(q) for q in p * scale], fill=cls_id)
    return np.asarray(img)


# tokens of a full CubiCasa space class ("Entry Lobby", "Utility Laundry", "Bath Shower") -> room type;
# the first token that names a type decides. Dining is counted as living space (as the lexicon does).
SPACE_TOKENS = {"bedroom": "bedroom", "livingroom": "living", "dining": "living", "kitchen": "kitchen",
                "bath": "bathroom", "sauna": "bathroom", "shower": "bathroom", "toilet": "wc",
                "entry": "entry", "draughtlobby": "entry", "lobby": "corridor", "hall": "corridor",
                "corridor": "corridor", "storage": "storage", "closet": "storage", "dressingroom": "storage",
                "utility": "storage", "laundry": "storage", "technicalroom": "storage", "garage": "garage",
                "carport": "garage", "outdoor": "terrace", "balcony": "terrace", "terrace": "terrace",
                "library": "office", "office": "office", "stairs": "stairs"}


def room_type_of(space_class: str) -> str:
    """Room type of a CubiCasa space class (the text after 'Space'); 'other' when none applies."""
    for tok in space_class.replace("-", " ").split():
        rt = SPACE_TOKENS.get(tok.lower())
        if rt:
            return rt
    return "other"
