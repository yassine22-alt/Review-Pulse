"""J5 - Consistency (K) and completeness (P) checks.

K-A1 chain sums, K-A2 written vs drawn, K-A3 stated vs computed area,
K-X1 / P-3 tag-schedule join, P-1 / P-2 / P-4 presence.
"""

from __future__ import annotations

from collections import defaultdict

from shapely.geometry import Polygon

from ..annotate.text_classify import tag_key
from ..rules.schema import Rule
from ..schema import Dimension
from .context import Context
from .policy import Raw, compare


def _chains(ctx: Context) -> dict[str, list[Dimension]]:
    ch: dict[str, list[Dimension]] = defaultdict(list)
    for d in ctx.model.sheet.dimensions:
        if d.chain_id:
            ch[d.chain_id].append(d)
    return ch


def fn_sum_parts(rule: Rule, ctx: Context) -> list[Raw]:
    out = []
    for cid, dims in _chains(ctx).items():
        overall = [d for d in dims if d.prov.evidence.get("overall")]
        parts = [d for d in dims if not d.prov.evidence.get("overall")]
        if not overall or len(parts) < 2:
            continue
        tot = overall[0]
        if tot.value_m is None or any(p.value_m is None for p in parts):
            out.append(Raw([cid], None, note="a dimension value could not be read"))
            continue
        s = sum(p.value_m for p in parts)
        diff = tot.value_m - s
        tol = max(0.005 * tot.value_m, 0.005)
        violated = abs(diff) > tol
        parts_txt = " + ".join(f"{p.value_m:.2f}" for p in parts)
        out.append(Raw([cid, tot.id] + [p.id for p in parts], violated, beyond_band=violated,
                       detected=f"{parts_txt} = {s:.2f} m", required=f"= {tot.value_m:.2f} m (overall)",
                       vars={"chain": {"diff": f"{diff:+.2f} m", "__str__": cid}},
                       evidence={"polylines": [[p.p1, p.p2] for p in parts] + [[tot.p1, tot.p2]],
                                 "labels": [{"at": tot.p2, "text": f"diff {diff:+.2f} m"}],
                                 "parts": [p.value_m for p in parts], "sum": round(s, 4),
                                 "stated_total": tot.value_m, "difference": round(diff, 4)}))
    return out


def fn_drawn_vs_stated(rule: Rule, ctx: Context) -> list[Raw]:
    out = []
    for d in ctx.model.sheet.dimensions:
        if d.value_m is None or d.measured_m is None:
            continue
        diff = d.value_m - d.measured_m
        tol = max(0.01 * d.measured_m, 0.010)
        violated = abs(diff) > tol
        out.append(Raw([d.id], violated, beyond_band=violated, metric=True,
                       detected=f"written {d.value_m:.2f} m, drawn {d.measured_m:.2f} m",
                       required=f"difference <= {tol:.3f} m",
                       vars={"dim": {"diff": f"{diff:+.2f} m", "__str__": d.id}},
                       evidence={"polylines": [[d.p1, d.p2]], "labels": [{"at": d.p1, "text": f"{diff:+.2f} m"}]}))
    return out


def fn_stated_vs_computed_area(rule: Rule, ctx: Context) -> list[Raw]:
    out = []
    rel = rule.check.tolerance_rel if rule.check.tolerance_rel is not None else 0.05
    for r in ctx.model.rooms:
        if r.stated_area_m2 is None or r.area_m2 is None:
            continue
        diff = r.stated_area_m2 - r.area_m2
        violated = abs(diff) > rel * r.area_m2
        c = Polygon(r.polygon).centroid
        out.append(Raw([r.id], violated, beyond_band=violated, metric=True,
                       detected=f"stated {r.stated_area_m2:.2f} m², computed {r.area_m2:.2f} m²",
                       required=f"within {rel:.0%}",
                       vars={"room": {"label": ctx.name(r.id), "__str__": ctx.name(r.id)}},
                       evidence={"polygons": [r.polygon], "labels": [{"at": (c.x, c.y), "text": f"{diff:+.2f} m²"}]}))
    return out


def _schedule_rows(ctx: Context) -> dict[str, dict]:
    rows = {}
    for s in ctx.model.schedules:
        for row in s.get("rows", []):
            if row.get("tag"):
                rows[tag_key(str(row["tag"]))] = row
    return rows


def fn_join(rule: Rule, ctx: Context) -> list[Raw]:
    mode = rule.params.get("mode", "widths")
    rows = _schedule_rows(ctx)
    tagged = [e for e in ctx.model.elements if e.tag and e.cls in ("door", "window")]
    plan_tags = {tag_key(e.tag) for e in tagged}
    loose_tags = {t.norm for t in ctx.model.sheet.texts
                  if t.kind == "tag" and t.norm and not t.prov.evidence.get("in_table")}
    out = []
    if mode == "widths":
        for e in tagged:
            row = rows.get(tag_key(e.tag))
            if not row or row.get("width_m") is None or e.attrs.get("width_m") is None:
                continue
            drawn, sched = float(e.attrs["width_m"]), float(row["width_m"])
            tol = max(0.005, 0.01 * sched)
            violated = abs(drawn - sched) > tol
            out.append(Raw([e.id], violated, beyond_band=violated, metric=True, deciding_ids=[e.id],
                           detected=f"plan {drawn:.2f} m, schedule {sched:.2f} m", required=f"equal within {tol:.3f} m",
                           vars={"subject": {"tag": e.tag, "__str__": e.tag}},
                           evidence={"polygons": [e.geom], "labels": [{"at": e.attrs.get("mid", e.geom[0]), "text": e.tag}]}))
        return out
    # completeness: tags without a row and rows without a tag
    all_tags = plan_tags | loose_tags
    missing_rows = sorted(t for t in all_tags if t not in rows)
    unused_rows = sorted(r for r in rows if r not in all_tags)
    for t in missing_rows:
        txt = next((x for x in ctx.model.sheet.texts if x.norm == t), None)
        out.append(Raw([t], True, detected=f"tag {t} has no schedule row", required="every tag in the schedule",
                       vars={"subject": {"tag": t, "__str__": t}},
                       evidence={"points": [((txt.bbox[0] + txt.bbox[2]) / 2, (txt.bbox[1] + txt.bbox[3]) / 2)] if txt else []}))
    for r in unused_rows:
        out.append(Raw([r], True, detected=f"schedule row {r} is used by no tag", required="every row used",
                       vars={"subject": {"tag": r, "__str__": r}}))
    if not out:
        out.append(Raw([], False, detected=f"{len(all_tags)} tags, {len(rows)} rows", required="all matched"))
    return out


def fn_present(rule: Rule, ctx: Context) -> list[Raw]:
    what = rule.params.get("what")
    m = ctx.model
    if what == "room_labels":
        out = []
        for r in m.rooms:
            out.append(Raw([r.id], r.label is None, detected="no label" if r.label is None else r.label,
                           required="a room label", vars={"room": {"label": ctx.name(r.id), "__str__": ctx.name(r.id)}},
                           evidence={"polygons": [r.polygon]} if r.label is None else {}))
        return out
    if what == "dimensions":
        n = len(m.sheet.dimensions) or sum(1 for t in m.sheet.texts
                                           if t.kind == "dimension" and not t.prov.evidence.get("in_table"))
        return [Raw(["sheet"], n == 0, detected=f"{n} dimension strings", required=">= 1")]
    if what == "title_block":
        required = rule.params.get("fields", ["scale", "revision", "date"])
        found = {t.norm for t in m.sheet.texts if t.kind == "title_block"}
        miss = [f for f in required if f not in found]
        return [Raw(["sheet"], bool(miss), detected="missing: " + ", ".join(miss) if miss else "all present",
                    required=", ".join(required))]
    if what == "opening_tags":
        out = []
        for e in m.elements:
            if e.cls not in ("door", "window"):
                continue
            name = e.tag or f"{e.cls} {e.id[-6:]}"
            out.append(Raw([e.id], e.tag is None, deciding_ids=[e.id],
                           detected="no tag" if e.tag is None else e.tag, required="a tag (P1, F2 ...)",
                           vars={"subject": {"tag": name, "__str__": name}},
                           evidence={"polygons": [e.geom]} if e.tag is None else {}))
        return out
    raise ValueError(f"present: unknown 'what' {what!r}")


def fn_programme_rooms(rule: Rule, ctx: Context) -> list[Raw]:
    """K-P1: the rooms the brief requires are on the plan, as many of each type, each at its area.

    Required areas of one type are paired with that type's rooms largest to largest (if any
    assignment meets every requirement, this one does). A shortfall becomes NOT_EVALUATED while
    unlabelled rooms remain: one of them may be the missing room."""
    rows = [r for s in ctx.model.schedules if s.get("name") == "programme" for r in s.get("rows", [])]
    tol = float(rule.params.get("area_tolerance", 0.0))
    untyped = [r.id for r in ctx.model.rooms if r.type is None and not r.is_corridor]
    need = defaultdict(lambda: {"count": 0, "areas": [], "labels": []})
    for r in rows:
        n = need[r["type"]]
        n["count"] += int(r.get("count") or 1)
        n["labels"].append(r["label"])
        if r.get("area_m2"):
            n["areas"] += [(float(r["area_m2"]), r["label"])] * int(r.get("count") or 1)
    out = []
    for rtype, n in need.items():
        plan = sorted((r for r in ctx.model.rooms if r.type == rtype), key=lambda r: -(r.area_m2 or 0))
        ids = [r.id for r in plan]
        short = len(plan) < n["count"]
        out.append(Raw(ids, None if short and untyped else short, deciding_ids=ids + (untyped if short else []),
                       vars={"subject": {"label": rtype, "__str__": rtype}},
                       detected=f"{len(plan)} {rtype} room(s) on the plan",
                       required=f"{n['count']} in the brief ({', '.join(n['labels'])})",
                       note="unlabelled rooms may include the missing ones" if short and untyped else None))
        for room, (req, label) in zip(plan, sorted(n["areas"], reverse=True)):
            if room.area_m2 is None:
                continue
            limit = req * (1 - tol)
            violated, beyond = compare(room.area_m2, ">=", limit, max(0.01 * limit, 0.05))
            out.append(Raw([room.id], violated, beyond_band=beyond, metric=True, deciding_ids=[room.id],
                           vars={"subject": {"label": ctx.name(room.id), "__str__": ctx.name(room.id)}},
                           detected=f"{room.area_m2:.2f} m2", required=f">= {limit:.2f} m2 ({label} in the brief)",
                           evidence={"polygons": [room.polygon]} if violated else {}))
    return out
