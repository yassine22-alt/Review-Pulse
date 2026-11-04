"""J4 - Metric checks: door width, corridor width, room area/width, light ratio.

Every finding states detected and required values with units and draws the
measured polygon. Results are tagged ``metric`` so the policy caps them at
WARNING when the scale is estimated.
"""

from __future__ import annotations

from shapely.geometry import Polygon

from ..annotate.text_classify import tag_key
from ..rules.schema import Rule
from .context import Context
from .policy import AREA_TOL_REL, Raw, compare, length_tol


def _tol(rule: Rule, value: float, area: bool = False) -> float:
    if rule.check.tolerance_m is not None:
        return rule.check.tolerance_m
    if rule.check.tolerance_rel is not None:
        return rule.check.tolerance_rel * abs(value)
    return AREA_TOL_REL * abs(value) if area else length_tol(value)


def _limit(rule: Rule) -> float:
    v = float(rule.check.value)
    unit = rule.check.unit
    return v / 100 if unit == "cm" else v / 1000 if unit == "mm" else v


def _schedule_width(ctx: Context, tag: str | None) -> float | None:
    if not tag:
        return None
    for s in ctx.model.schedules:
        for row in s.get("rows", []):
            if tag_key(str(row.get("tag", ""))) == tag_key(tag) and row.get("width_m"):
                return float(row["width_m"])
    return None


def fn_width_m(rule: Rule, ctx: Context) -> list[Raw]:
    out = []
    allowance = float(rule.params.get("frame_allowance_m", 0.0))
    limit = _limit(rule)
    for el in ctx.elements_for(rule.applies_to):
        drawn = el.attrs.get("width_m")
        if drawn is None:
            out.append(Raw([el.id], None, note="width unknown"))
            continue
        clear = drawn - allowance
        sched = _schedule_width(ctx, el.tag)
        # with two sources, judge on the conservative one: the smaller for a minimum, the larger for a maximum
        if sched:
            used = max(clear, sched) if rule.check.op in ("<=", "<") else min(clear, sched)
        else:
            used = clear
        tol = _tol(rule, limit)
        violated, beyond = compare(used, rule.check.op, limit, tol)
        det = f"{used:.2f} m" + (f" (drawn {drawn:.2f} m, schedule {sched:.2f} m)" if sched else "")
        if allowance:
            det += f" after frame allowance {allowance:.2f} m"
        name = el.tag or el.id[-6:]
        out.append(Raw([el.id], violated, beyond_band=beyond, metric=True, deciding_ids=[el.id],
                       detected=det, required=f"{rule.check.op} {limit:.2f} m",
                       vars={"subject": {"tag": name, "__str__": name}},
                       evidence={"polygons": [el.geom] + ([el.attrs["swing_polygon"]] if el.attrs.get("swing_polygon") else []),
                                 "labels": [{"at": el.attrs.get("mid", el.geom[0]), "text": f"{used:.2f} m"}]}))
    return out


def _room_metric(rule: Rule, ctx: Context, attr: str, area: bool) -> list[Raw]:
    out = []
    limit = _limit(rule)
    for room in ctx.rooms_for(rule.applies_to):
        val = getattr(room, attr)
        if val is None:
            out.append(Raw([room.id], None, note=f"{attr} unknown"))
            continue
        tol = _tol(rule, limit, area)
        violated, beyond = compare(val, rule.check.op, limit, tol)
        unit = "m²" if area else "m"
        c = Polygon(room.polygon).centroid
        out.append(Raw([room.id], violated, beyond_band=beyond, metric=True, deciding_ids=[],
                       detected=f"{val:.2f} {unit}", required=f"{rule.check.op} {limit:.2f} {unit}",
                       vars={"room": {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}},
                       evidence={"polygons": [room.polygon], "labels": [{"at": (c.x, c.y), "text": f"{val:.2f} {unit}"}]}))
    return out


def fn_area_m2(rule: Rule, ctx: Context) -> list[Raw]:
    return _room_metric(rule, ctx, "area_m2", area=True)


def fn_min_width_m(rule: Rule, ctx: Context) -> list[Raw]:
    return _room_metric(rule, ctx, "min_width_m", area=False)


def fn_ratio(rule: Rule, ctx: Context) -> list[Raw]:
    """C-V1: glazed area (window width x schedule height) over floor area. Heights only
    from the schedule; without them the result is NOT_EVALUATED, never an assumed height."""
    out = []
    limit = float(rule.check.value)
    heights = {}
    for s in ctx.model.schedules:
        for row in s.get("rows", []):
            if row.get("height_m"):
                heights[tag_key(str(row.get("tag", "")))] = float(row["height_m"])
    for room in ctx.rooms_for(rule.applies_to):
        wins = [ctx.element(e.via) for e in ctx.model.edges
                if e.kind == "window" and room.id in (e.a, e.b) and "EXTERIOR" in (e.a, e.b) and e.via]
        wins = [w for w in wins if w]
        if not room.area_m2:
            out.append(Raw([room.id], None, note="floor area unknown"))
            continue
        if any(not w.tag or tag_key(w.tag) not in heights for w in wins):
            out.append(Raw([room.id], None, missing=["window heights (schedule)"]))
            continue
        glazed = sum(w.attrs.get("width_m", 0) * heights[tag_key(w.tag)] for w in wins)
        r = glazed / room.area_m2
        violated, beyond = compare(r, rule.check.op, limit, 0.005)
        out.append(Raw([room.id] + [w.id for w in wins], violated, beyond_band=beyond, metric=True,
                       deciding_ids=[w.id for w in wins], detected=f"{r:.3f}", required=f"{rule.check.op} {limit:.3f}",
                       vars={"room": {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}},
                       evidence={"polygons": [room.polygon] + [w.geom for w in wins]}))
    return out


def fn_escape_window(rule: Rule, ctx: Context) -> list[Raw]:
    """C-V2: each room has at least one exterior window large enough to escape through: clear width
    from the drawing, height from the schedule (never assumed). Limits from rule params."""
    min_w = float(rule.params.get("min_width_m", 0.60))
    min_h = float(rule.params.get("min_height_m", 1.00))
    heights = {}
    for s in ctx.model.schedules:
        for row in s.get("rows", []):
            if row.get("height_m"):
                heights[tag_key(str(row.get("tag", "")))] = float(row["height_m"])
    out = []
    for room in ctx.rooms_for(rule.applies_to):
        wins = [ctx.element(e.via) for e in ctx.model.edges
                if e.kind == "window" and room.id in (e.a, e.b) and "EXTERIOR" in (e.a, e.b) and e.via]
        wins = [w for w in wins if w]
        name = {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}
        if not wins:
            out.append(Raw([room.id], True, metric=True, detected="no exterior window",
                           required=f"window >= {min_w:.2f} m wide and >= {min_h:.2f} m high",
                           vars={"room": name}, evidence={"polygons": [room.polygon]}))
            continue
        if any(not w.tag or tag_key(w.tag) not in heights for w in wins):
            out.append(Raw([room.id], None, missing=["window heights (schedule)"]))
            continue
        best = max(wins, key=lambda w: (w.attrs.get("width_m", 0) >= min_w, heights[tag_key(w.tag)]))
        wv, hv = float(best.attrs.get("width_m", 0)), heights[tag_key(best.tag)]
        ok = wv >= min_w - 0.01 and hv >= min_h - 0.01
        out.append(Raw([room.id, best.id], not ok, metric=True, deciding_ids=[best.id],
                       detected=f"{best.tag}: {wv:.2f} x {hv:.2f} m",
                       required=f">= {min_w:.2f} x {min_h:.2f} m", vars={"room": name},
                       evidence={"polygons": [room.polygon, best.geom]}))
    return out
