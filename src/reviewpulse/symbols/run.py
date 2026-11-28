"""The symbol finder over a whole PDF set: legend entries to exemplars, plan views searched, instances bound to rooms."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ..drawingset import DrawingSet, build_drawing_set, from_pdf
from .bind import Placed, Room, place
from .find import BAND, Exemplar, FindResult, build_exemplars, find_instances
from .primitives import Stroke, frame_turns, strokes_of_page

SEARCH_KINDS = ("plan",)


@dataclass
class ViewResult:
    sheet: int
    view: str
    result: FindResult
    placed: list[Placed]
    seconds: float = 0.0


@dataclass
class SetResult:
    drawing_set: DrawingSet
    exemplars: list[Exemplar]
    rejected: list[tuple[int, str]]
    views: list[ViewResult] = field(default_factory=list)
    strokes: dict[int, list[Stroke]] = field(default_factory=dict)


def view_ratio(ex: Exemplar, view_scale_mpp: float | None, scale_aware: bool) -> float:
    """Expected size of a symbol in a view over its size in the legend. 1.0 unless scale aware and both scales are known."""
    if scale_aware and ex.scale_mpp and view_scale_mpp:
        return ex.scale_mpp / view_scale_mpp
    return 1.0


def run_pdf(path: str | Path, method: str = "descriptor", scale_aware: bool = False, band: tuple[float, float] = BAND,
            rooms_for: Callable[[int, str], list[Room]] | None = None, kinds: tuple[str, ...] = SEARCH_KINDS,
            pages: list[int] | None = None) -> SetResult:
    import time

    pgs = from_pdf(path, pages)
    dset = build_drawing_set(pgs, Path(path).stem)
    doc = pymupdf.open(str(path))
    strokes: dict[int, list[Stroke]] = {}
    for pd in pgs:
        page = doc[pd.index]
        s = strokes_of_page(page)
        strokes[pd.index] = strokes_of_page(page, frame_turns(page, pd, s)) if len(pd.rects) else s
    scale_by_view = {v.id: (v.scale.metres_per_point if v.scale else None) for v in dset.views()}
    exemplars, rejected = build_exemplars(dset.legend, strokes, scale_by_view)
    out = SetResult(dset, exemplars, rejected, strokes=strokes)
    for sh in dset.sheets:
        for v in sh.views:
            if v.kind not in kinds:
                continue
            t0 = time.time()
            vm = v.scale.metres_per_point if v.scale else None
            ratio = {e.id: view_ratio(e, vm, scale_aware) for e in exemplars}
            res = find_instances(strokes[sh.index], v.bbox, exemplars, ratio, band, method)
            rooms = rooms_for(sh.index, v.id) if rooms_for else []
            out.views.append(ViewResult(sh.index, v.id, res, place(res.detections, exemplars, rooms, v.id, sh.index),
                                        time.time() - t0))
    return out
