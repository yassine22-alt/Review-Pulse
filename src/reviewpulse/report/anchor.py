"""Where to put a finding's marker: its evidence, else its subjects."""

from __future__ import annotations

from shapely.geometry import Polygon

from ..schema import BuildingModel, Finding


def anchor_point(f: Finding, model: BuildingModel) -> tuple[float, float] | None:
    ev = f.evidence
    for lab in ev.get("labels", []):
        if lab.get("at"):
            return tuple(lab["at"])
    for pts in ev.get("points", []):
        if pts:
            return tuple(pts)
    for poly in ev.get("polygons", []):
        if len(poly) >= 3:
            c = Polygon(poly).representative_point()
            return (c.x, c.y)
    for pl in ev.get("polylines", []):
        if pl:
            return tuple(pl[0])
    for sid in f.subject_ids:
        r = next((r for r in model.rooms if r.id == sid), None)
        if r:
            c = Polygon(r.polygon).representative_point()
            return (c.x, c.y)
        e = next((e for e in model.elements if e.id == sid), None)
        if e:
            return tuple(e.geom[0])
    return None
