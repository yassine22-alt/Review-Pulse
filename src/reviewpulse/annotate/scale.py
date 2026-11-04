"""R7 - Scale recovery.

1. DXF with known units: exact; DIMENSION measurements are cross-checked.
2. Otherwise: pair dimension texts with thin dimension lines that carry
   terminators, compute s_i = D_mm / d_mm, take a robust consensus
   (median, MAD), snap to a standard scale.
3. Fallbacks: title-block "1:100" (unverified), user calibration, none (T3).

Thresholds come from the 2026 structural-plan study (Talebi-Kalaleh & Mei)
and are starting points to tune on the gold set.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from ..core.geometry import angle_diff, seg_angle, seg_len
from ..schema import Primitive, Scale, Sheet, TextItem
from .text_classify import dimension_metres, normalise

THIN_MAX_MM = 0.30
TEXT_LINE_MAX_DIST_MM = 12.0
TEXT_LINE_MAX_ANGLE = 6.0
LINE_MIN_MM = 3.0
NEAREST_SLACK_MM = 1.0     # both edges of one stroke, or a doubled line, count as the nearest
TERM_MIN_MM, TERM_MAX_MM = 0.8, 6.0
TERM_MIN_CROSS_DEG = 20.0
TERM_MID_TOL_MM = 1.2
TRIANGLE_TOL_MM = 1.6
MIN_CANDIDATES = 3
MIN_CONFIDENCE = 0.6
SNAP_TOL = 0.015
OUTLIER_TOL = 0.02
STANDARD_SCALES = [10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500]
TITLE_SCALE_RE = re.compile(r"(ech|echelle|scale)\s*[:=]?\s*1\s*[:/]\s*(\d+)")


@dataclass
class DimPair:
    text_id: str
    line_id: str
    p1: tuple[float, float]
    p2: tuple[float, float]
    stated_mm: float            # real millimetres written in the text
    drawn: float                # length on the sheet (sheet units)
    ratio: float                # stated_mm / drawn
    ambiguous: bool = False
    term_ids: list = field(default_factory=list)
    u: float = 1.0              # sheet units per nominal paper millimetre


@dataclass
class ScaleReport:
    method: str
    candidates: list[DimPair] = field(default_factory=list)
    inliers: list[DimPair] = field(default_factory=list)
    outliers: list[DimPair] = field(default_factory=list)
    ratio: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        def d(p: DimPair):
            return dict(text_id=p.text_id, line_id=p.line_id, p1=p.p1, p2=p.p2, stated_mm=p.stated_mm,
                        drawn=round(p.drawn, 4), ratio=round(p.ratio, 4))

        return dict(method=self.method, ratio=self.ratio, notes=self.notes,
                    candidates=[d(p) for p in self.candidates], inliers=[d(p) for p in self.inliers],
                    outliers=[d(p) for p in self.outliers])


def _segments(prims: list[Primitive]):
    for p in prims:
        if p.hidden or p.kind not in ("line", "polyline"):
            continue
        for a, b in zip(p.pts, p.pts[1:]):
            yield p, a, b


def _terminator(end, direction_deg, short_segs, short_tree, filled_tris, u: float) -> str | None:
    """Id of the terminator at a dimension-line end (oblique tick or filled arrow), else None."""
    for i in short_tree.query(Point(end).buffer(TERM_MAX_MM * u)):
        p, a, b = short_segs[i]
        L = seg_len(a, b)
        if not (TERM_MIN_MM * u <= L <= TERM_MAX_MM * u):
            continue
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if math.dist(mid, end) > TERM_MID_TOL_MM * u:
            continue
        if angle_diff(seg_angle(a, b), direction_deg) > TERM_MIN_CROSS_DEG:
            return p.id
    for pid, c in filled_tris:
        if math.dist(c, end) <= TRIANGLE_TOL_MM * u:
            return pid
    return None


NOMINAL_TEXT_MM = 2.5     # dimension text is ~2.5 mm high on paper: the scale-free ruler


def dimension_pairs(sheet: Sheet) -> list[DimPair]:
    """Pair every dimension text with the dimension line it labels.

    Thresholds are paper millimetres (Talebi-Kalaleh & Mei 2026) expressed in units of
    the text height, so the same test works on PDF paper space and on DXF drawing units
    at any scale. Stroke width is used only where it is known (PDF)."""
    texts = [t for t in sheet.texts if t.kind == "dimension" and t.value is not None
             and not t.prov.evidence.get("in_table")]
    if not texts:
        return []
    paper = sheet.coord_unit == "paper_mm"
    segs = [(p, a, b) for p, a, b in _segments(sheet.primitives)
            if not (paper and p.width is not None and p.width > THIN_MAX_MM) and not p.filled
            and not p.prov.evidence.get("glazing")]
    if not segs:
        return []
    heights = sorted(t.height for t in texts if t.height)
    h_med = heights[len(heights) // 2] if heights else None
    u_sheet = (h_med / NOMINAL_TEXT_MM) if (h_med and not paper) else 1.0
    seg_tree = STRtree([LineString([a, b]) for _, a, b in segs])
    filled_tris = []
    for p in sheet.primitives:
        if p.filled and p.kind == "polygon" and len(p.pts) == 3:
            filled_tris.append((p.id, (sum(x for x, _ in p.pts) / 3, sum(y for _, y in p.pts) / 3)))

    pairs = []
    for t in texts:
        u = (t.height / NOMINAL_TEXT_MM) if (t.height and not paper) else u_sheet
        cx, cy = (t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2
        best = None
        near = []
        for i in seg_tree.query(Point(cx, cy).buffer(TEXT_LINE_MAX_DIST_MM * u)):
            p, a, b = segs[i]
            if seg_len(a, b) < LINE_MIN_MM * u:
                continue
            ang = seg_angle(a, b)
            if angle_diff(ang, t.rotation_deg % 180) > TEXT_LINE_MAX_ANGLE:
                continue
            ls = LineString([a, b])
            dist = ls.distance(Point(cx, cy))
            if dist > TEXT_LINE_MAX_DIST_MM * u:
                continue
            f = ls.project(Point(cx, cy), normalized=True)
            if not (0.05 <= f <= 0.95):
                continue
            near.append((dist, p, a, b, ang))
        # a dimension text labels the nearest parallel line beside it; when that line has no ticks
        # (lost in a scan) the text is unpaired rather than lent to a farther line (a wall face or
        # door jamb with perpendicular ends would pass as a dimension at the wrong length)
        d0 = min((n[0] for n in near), default=0.0)
        for dist, p, a, b, ang in near:
            if dist > d0 + NEAREST_SLACK_MM * u:
                continue
            t1 = _terminator(a, ang, segs, seg_tree, filled_tris, u)
            t2 = _terminator(b, ang, segs, seg_tree, filled_tris, u) if t1 else None
            if not (t1 and t2):
                continue
            if best is None or dist < best[0]:
                best = (dist, p, a, b, [t1, t2])
        if best is None:
            continue
        _, p, a, b, terms = best
        drawn = seg_len(a, b)
        readings = [t.unit] if t.unit else ["mm", "cm"]
        for unit in readings:
            m = dimension_metres(t.value, unit)
            if m:
                pairs.append(DimPair(t.id, p.id, a, b, m * 1000, drawn, m * 1000 / drawn,
                                     ambiguous=len(readings) > 1, term_ids=terms, u=u))
    return pairs


def consensus(pairs: list[DimPair], snap_to=STANDARD_SCALES) -> tuple[float | None, list[DimPair], list[DimPair], float]:
    """Return (snapped ratio, inliers, outliers, confidence)."""
    if not pairs:
        return None, [], [], 0.0
    sure = [p.ratio for p in pairs if not p.ambiguous] or [p.ratio for p in pairs]
    med = statistics.median(sure)
    mad = statistics.median([abs(r - med) for r in sure])
    tau = max(0.01 * med, 4 * mad)
    # ambiguous texts keep only the reading closest to the median
    chosen: dict[str, DimPair] = {}
    for p in pairs:
        if p.text_id not in chosen or abs(p.ratio - med) < abs(chosen[p.text_id].ratio - med):
            chosen[p.text_id] = p
    cands = list(chosen.values())
    inl = [p for p in cands if abs(p.ratio - med) <= tau]
    if not inl:
        return None, [], cands, 0.0
    s_hat = sum(p.ratio for p in inl) / len(inl)
    for std in snap_to:
        if abs(s_hat - std) / std <= SNAP_TOL:
            s_hat = float(std)
            break
    out = [p for p in cands if abs(p.ratio - s_hat) / s_hat > OUTLIER_TOL]
    return s_hat, inl, out, len(inl) / len(cands)


def title_block_scale(texts: list[TextItem]) -> int | None:
    for t in texts:
        m = TITLE_SCALE_RE.search(normalise(t.text))
        if m:
            return int(m.group(2))
    return None


DRAWING_UNIT_MM = [1.0, 10.0, 1000.0, 25.4, 304.8]     # mm, cm, m, inch, foot per drawing unit


# "not to scale" notes; matched on accent-stripped lower-case text (annotate.text_classify.normalise)
NOT_TO_SCALE_RE = re.compile(
    r"\bn\.?\s?t\.?\s?s\b|not to scale|sans echelle|pas a l'?echelle|non a l'?echelle|hors echelle"
    r"|nicht (?:ma(?:ss|ß)stablich|im ma(?:ss|ß)stab)|unma(?:ss|ß)stablich|no a escala|sin escala|non in scala"
    r"|fuori scala|niet op schaal|sem escala|fora de escala|ei mittakaavassa|ej skalenlig|inte skalenlig"
    r"|بدون مقياس|ليس بمقياس")
NTS_MAX_CONFIDENCE = 0.5


def not_to_scale(sheet: Sheet) -> str | None:
    """The sheet's own "not to scale" note, if it carries one."""
    from .text_classify import normalise

    for t in sheet.texts:
        if NOT_TO_SCALE_RE.search(normalise(t.text)):
            return t.text
    return None


def recover_scale(sheet: Sheet, calibrate: tuple[float, float, float, float, float] | None = None) -> tuple[Scale, ScaleReport]:
    """Scale (see _recover_scale). A drawing that declares itself not to scale is never measured as if
    it were: an estimated scale is capped below the T2 confidence, so metric rules give at most
    WARNING. DXF model-space units (true size by construction) and a user calibration are kept."""
    scale, rep = _recover_scale(sheet, calibrate)
    note = not_to_scale(sheet)
    if note:
        msg = f"the drawing says it is not to scale ({note!r})"
        if scale.method not in ("dxf_units", "user") and scale.metres_per_unit:
            scale = scale.model_copy(update={"confidence": min(scale.confidence, NTS_MAX_CONFIDENCE)})
            msg += ": measurements are estimates (tier T3)"
        rep.notes.append(msg)
        if msg not in sheet.warnings:
            sheet.warnings.append(msg)
    return scale, rep


def _recover_scale(sheet: Sheet, calibrate: tuple[float, float, float, float, float] | None = None) -> tuple[Scale, ScaleReport]:
    """Scale from (in order) DXF units, user calibration, dimension consensus, title block.
    The dimension pairs are always returned in the report: they also identify dimension
    graphics (kept out of wall detection) and feed the written-vs-drawn check."""
    pairs = dimension_pairs(sheet)
    drawing = sheet.coord_unit == "drawing_unit"
    s_hat, inl, out, conf = consensus(pairs, DRAWING_UNIT_MM if drawing else STANDARD_SCALES)
    n_cand = len({p.text_id for p in pairs})
    rep = ScaleReport(method="dimension_consensus", candidates=pairs, inliers=inl, outliers=out, ratio=s_hat)

    if drawing and sheet.scale.metres_per_unit:
        from ..ingest.dxf_reader import dimension_drawn_check

        rep.method = sheet.scale.method
        rep.notes += dimension_drawn_check(sheet)
        if s_hat and abs(s_hat / 1000 - sheet.scale.metres_per_unit) > 0.02 * sheet.scale.metres_per_unit:
            rep.notes.append(f"$INSUNITS says {sheet.scale.metres_per_unit} m/unit but dimensions say {s_hat / 1000:g}")
        return sheet.scale, rep
    if calibrate:
        scale, crep = _calibrated(calibrate)
        crep.candidates, crep.inliers, crep.outliers = pairs, inl, out
        return scale, crep
    if s_hat and n_cand >= MIN_CANDIDATES and conf >= MIN_CONFIDENCE:
        return Scale(metres_per_unit=s_hat / 1000, method="dimension_consensus", confidence=round(conf, 3),
                     n_candidates=n_cand, n_inliers=len(inl)), rep
    rep.notes.append(f"dimension consensus failed: {n_cand} candidates, confidence {conf:.2f}")
    if drawing:
        prior = symbol_prior_scale(sheet)
        if prior:
            mpu, n_doors = prior
            rep.method = "symbol_prior"
            rep.notes.append(f"no units and no readable dimensions: scale estimated from {n_doors} door symbols "
                             f"(median leaf = {DOOR_PRIOR_M} m); estimated, tier T3")
            return Scale(metres_per_unit=mpu, method="symbol_prior", confidence=0.5, n_candidates=n_doors), rep
        rep.method = "none"
        rep.notes.append("unitless drawing and no calibration")
        return Scale(n_candidates=n_cand), rep
    denom = title_block_scale(sheet.texts)
    if denom:
        rep.method = "title_block"
        rep.notes.append(f"title block says 1:{denom} (unverified)")
        return Scale(metres_per_unit=denom / 1000, method="title_block", confidence=0.7,
                     n_candidates=n_cand, n_inliers=len(inl)), rep
    rep.method = "none"
    return Scale(n_candidates=n_cand), rep


DOOR_PRIOR_M = 0.85         # typical door leaf width; real leaves are 0.7-1.0 m nearly everywhere
DOOR_PRIOR_MIN = 3


def symbol_prior_scale(sheet: Sheet) -> tuple[float, int] | None:
    """Last-resort scale for drawings without units or dimensions: door symbols (a ~90 deg arc with a
    leaf line from its centre to one end) have a known size. Returns (metres per unit, n doors)."""
    from ..core.geometry import arc_sweep

    lines = [p for p in sheet.primitives if p.kind == "line" and not p.hidden]
    if not lines:
        return None
    tree = STRtree([LineString(p.pts) for p in lines])
    radii = []
    for a in sheet.primitives:
        if a.kind != "arc" or a.hidden or not (75 <= arc_sweep(a.a0, a.a1) <= 105) or not a.radius:
            continue
        c, r = a.center, a.radius
        ends = [(c[0] + r * math.cos(math.radians(t)), c[1] + r * math.sin(math.radians(t))) for t in (a.a0, a.a1)]
        tol = 0.06 * r
        for i in tree.query(Point(c).buffer(tol)):
            p, q = lines[i].pts[0], lines[i].pts[-1]
            for h, o in ((p, q), (q, p)):
                if math.dist(h, c) <= tol and any(math.dist(o, e) <= tol for e in ends):
                    radii.append(r)
                    break
            else:
                continue
            break
    if len(radii) < DOOR_PRIOR_MIN:
        return None
    return DOOR_PRIOR_M / statistics.median(radii), len(radii)


def _calibrated(cal):
    x1, y1, x2, y2, metres = cal
    d = math.dist((x1, y1), (x2, y2))
    return (Scale(metres_per_unit=metres / d, method="user", confidence=1.0),
            ScaleReport(method="user", notes=[f"user calibration: {d:.3f} units = {metres} m"]))


def paper_mm_assumed(sheet: Sheet) -> float:
    """metres per unit used when the scale is unknown (1:100 for paper, mm for drawings)."""
    return 0.1 if sheet.coord_unit == "paper_mm" else 0.001
