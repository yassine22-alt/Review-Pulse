"""Fuse the rule walls with the learned primitive classifier: the rules propose, the classifier disposes.

Rebuilding every wall from the lines the classifier keeps changes how the remaining lines pair, so walls
the rules had right (and the room closure that depends on them) can be lost: on generated plans, rooms
merged (8 -> 1) although the classifier agreed with 99 % of the wall lines. Fusion keeps the rule
result as the base and changes it only where the classifier has evidence:

- a rule wall whose member lines the classifier rejects becomes a candidate (cls ``other``), with
  the classifier's verdict kept as evidence (the source of the precision gain on real CAD). The verdict
  is the length-weighted mean wall probability of the lines, against the model's tuned threshold: with
  yes/no calls, a pair of equal faces with one face called wall ties at a share of 0.5 and was kept
  (measured: free-standing hatched strips in a FloorPlanCAD hall, faces at 0.7 and 0.13, cut it in 8);
- a wall from the classifier-driven rebuild that no kept wall already covers is added (the source of
  the recall gain: faces the pairing rules could not match).
"""

from __future__ import annotations

import math

from shapely.geometry import LineString
from shapely.strtree import STRtree

from ...schema import Element, Primitive, Sheet

KEEP_MIN = 0.5          # wall probability a wall's member lines must reach (default; the pipeline passes
                        # the model's tuned threshold)
COVERED = 0.5           # a rebuilt wall this much inside kept walls is the same wall


def _length(p: Primitive) -> float:
    if p.kind in ("line", "polyline") and len(p.pts) >= 2:
        return sum(math.dist(a, b) for a, b in zip(p.pts, p.pts[1:]))
    if p.kind == "polygon" and len(p.pts) >= 3:
        pts = p.pts + p.pts[:1]
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    return 0.0


def learned_wall_prob(e: Element, by_id: dict[str, Primitive]) -> float | None:
    """Length-weighted mean wall probability of the element's member lines (None: none scored)."""
    tot = yes = 0.0
    for m in e.member_ids:
        p = by_id.get(m)
        if p is None or "learned_wall" not in p.prov.evidence:
            continue
        ev = p.prov.evidence
        L = _length(p)
        tot += L
        yes += L * ev.get("p_wall", 1.0 if ev["learned_wall"] else 0.0)
    return yes / tot if tot > 0 else None


def _body(e: Element):
    return LineString(e.geom).buffer(max(e.thickness or 0.0, 1e-9) / 2, cap_style="flat")


REPLACED = 0.9          # share of a mixed wall's believed faces the rebuilt walls must carry


def _rebuilt_alternative(e: Element, by_id: dict, rebuilt: list[Element], tree, bodies) -> list[Element]:
    """A kept rule wall that pairs a believed face with a line the classifier rejects (a wall face
    with a lift car, fixture or finish line inside the room) has the wrong body: it reaches into the
    room. When walls rebuilt from believed lines only carry its believed faces, they replace it."""
    faces = [by_id[m] for m in e.member_ids if m in by_id and "learned_wall" in by_id[m].prov.evidence]
    if not faces or all(p.prov.evidence["learned_wall"] for p in faces):
        return []
    believed = [LineString(p.pts) for p in faces if p.prov.evidence["learned_wall"] and len(p.pts) >= 2]
    if not believed or tree is None:
        return []
    cands = []
    for b in believed:
        for i in tree.query(b):
            r = rebuilt[i]
            if any(m in r.member_ids for m in e.member_ids) and r not in cands and all(
                    by_id[m].prov.evidence.get("learned_wall") for m in r.member_ids if m in by_id):
                cands.append(r)
    if not cands:
        return []
    from shapely.ops import unary_union

    cover = unary_union([bodies[rebuilt.index(r)] for r in cands]).buffer(1e-6)
    tot = sum(b.length for b in believed)
    carried = sum(b.intersection(cover).length for b in believed)
    return cands if tot and carried >= REPLACED * tot else []


def fuse_walls(sheet: Sheet, rule_walls: list[Element], rebuilt: list[Element],
               threshold: float = KEEP_MIN) -> tuple[list[Element], dict]:
    by_id = {p.id: p for p in sheet.primitives}
    kept, out, stats = [], [], {"rejected": 0, "added": 0, "replaced": 0}
    rb = [e for e in rebuilt if e.cls == "wall" and len(e.geom) == 2]
    rb_bodies = [_body(e) for e in rb]
    rb_tree = STRtree(rb_bodies) if rb_bodies else None
    used: set[int] = set()
    for e in rule_walls:
        prob = learned_wall_prob(e, by_id) if e.cls == "wall" else None
        if prob is not None:
            e.prov.evidence["learned_wall_prob"] = round(prob, 3)
        if e.cls == "wall" and prob is not None and prob < threshold:
            out.append(e.model_copy(update={"cls": "other", "attrs": dict(e.attrs, candidate=True)}))
            stats["rejected"] += 1
            continue
        alt = _rebuilt_alternative(e, by_id, rb, rb_tree, rb_bodies) if e.cls == "wall" else []
        if alt:
            out.append(e.model_copy(update={"cls": "other", "attrs": dict(e.attrs, candidate=True, replaced=True)}))
            for r in alt:
                if id(r) not in used:
                    used.add(id(r))
                    r.prov.evidence["fused_from"] = "learned_rebuild"
                    out.append(r)
                    kept.append(r)
            stats["replaced"] += 1
            continue
        out.append(e)
        if e.cls == "wall":
            kept.append(e)
    bodies = [_body(e) for e in kept]
    tree = STRtree(bodies) if bodies else None
    for e in rb:
        if id(e) in used:
            continue
        b = _body(e)
        inside = sum(b.intersection(bodies[i]).area for i in tree.query(b)) if tree is not None else 0.0
        if b.area > 0 and inside < COVERED * b.area:
            e.prov.evidence["fused_from"] = "learned_rebuild"
            out.append(e)
            stats["added"] += 1
    return out, stats
