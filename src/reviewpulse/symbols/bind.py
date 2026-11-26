"""Bind found symbols to the room that holds them and turn the counts into fact candidates.

A room is a polygon in the page frame of the view (the fact graph's rooms, moved into page points by the caller). A symbol
belongs to the room that contains the centre of its box. A symbol in no room is bound to the view only, never guessed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

from ..ledger.candidate import Candidate
from .find import Detection, Exemplar

PRODUCER = "symbols_by_legend"
FAMILY = "vector_shape"           # one family: the same strokes cannot vouch for each other


@dataclass
class Room:
    id: str
    polygon: list[tuple[float, float]]
    label: str | None = None
    holes: list[list[tuple[float, float]]] | None = None


@dataclass
class Placed:
    detection: Detection
    exemplar: Exemplar
    view: str
    sheet: int
    room: str | None


def room_of(points: list[tuple[float, float]], rooms: list[Room]) -> list[str | None]:
    """The room id holding each point (the smallest, when rooms nest), or None."""
    polys = [Polygon(r.polygon, r.holes or []) for r in rooms]
    tree = STRtree(polys) if polys else None
    out: list[str | None] = []
    for x, y in points:
        best, area = None, None
        if tree is not None:
            for i in tree.query(Point(x, y)):
                if polys[int(i)].contains(Point(x, y)) and (area is None or polys[int(i)].area < area):
                    best, area = rooms[int(i)].id, polys[int(i)].area
        out.append(best)
    return out


def place(dets: list[Detection], exemplars: list[Exemplar], rooms: list[Room], view: str, sheet: int) -> list[Placed]:
    rid = room_of([d.centre for d in dets], rooms)
    return [Placed(d, exemplars[d.exemplar], view, sheet, r) for d, r in zip(dets, rid, strict=True)]


def counts(placed: list[Placed]) -> dict[tuple[str, str], dict[str, int]]:
    """{(view, symbol label): {room id or "": count}}; the key "" holds the symbols that are in no room."""
    out: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in placed:
        out[(p.view, p.exemplar.label)][p.room or ""] += 1
    return {k: dict(v) for k, v in out.items()}


def slug(words: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", words.lower()).strip("_")[:40] or "symbol"


def candidates(placed: list[Placed], sheet_name: str | None = None) -> list[Candidate]:
    """One candidate per (room, symbol): the number of that symbol drawn in the room. Kind "inferred": it is read from the
    shape of the drawing and the legend, not stated in words. The score is the mean match score, a ranking not a probability.
    Symbols in no room give a count on the view itself."""
    groups: dict[tuple[str, str, str, int], list[Placed]] = defaultdict(list)
    for p in placed:
        groups[(p.room or f"view:{p.view}", p.exemplar.label, p.view, p.sheet)].append(p)
    out = []
    for (entity, label, view, sheet), ps in sorted(groups.items()):
        ex = ps[0].exemplar
        x0 = min(p.detection.box[0] for p in ps)
        y0 = min(p.detection.box[1] for p in ps)
        x1 = max(p.detection.box[2] for p in ps)
        y1 = max(p.detection.box[3] for p in ps)
        out.append(Candidate(
            entity=entity, fact=f"count_{slug(label)}", value=len(ps), unit="1", kind="inferred",
            source=f"symbol matched to legend entry '{label}' on sheet {sheet_name or ex.sheet} (legend view {ex.view}), "
                   f"found on view {view} by shape",
            sheet=str(sheet_name or sheet), view=view, region=(x0, y0, x1, y1), words=label, producer=PRODUCER, family=FAMILY,
            score=sum(p.detection.score for p in ps) / len(ps)))
    return out
