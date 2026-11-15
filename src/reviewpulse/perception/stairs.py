"""Stairs from geometry: a statistical model of a flight, not a pile of thresholds.

A flight of stairs is a comb: parallel tread strokes at an even pitch p, all spanning (about) the same interval along
the tread direction. This module looks for exactly that, and says how sure it is:

  1. strokes are grouped by direction, then into bands that share an interval along the stroke (a flight is one band;
     two flights side by side are two bands);
  2. in a band, strokes at (nearly) the same offset are one level, and pieces of a broken tread are joined, so a tread
     drawn twice (edge and nosing) or in several pieces is still one level;
  3. a comb (pitch p, phase) is searched for among the levels' offsets with a Rayleigh statistic over the pitches a
     tread can have; levels are assigned to teeth and the longest run of consecutive teeth is kept;
  4. the run is tested against chance: the probability that random levels would fill that many consecutive teeth,
     corrected for the number of combs tried (a Bonferroni bound). Only runs below P_ACCEPT become stairs;
  5. the pitch is the least-squares slope of offset against tooth index, with its standard error. A measurement is
     `trusted` only when the fit is tight and the run is significant.

Measurements live in the element's provenance evidence (the element schema is unchanged):
  tread_depth_m, tread_depth_sd_m   pitch of the treads and its standard error
  width_m                           extent of the treads along their length (includes any stringer or handrail)
  n_levels, steps_min, steps_max    treads found; steps are n_levels-1 or n_levels depending on how the flight is drawn
  p_value, trusted, shape           significance against chance; whether a number can be relied on; "straight"
Nothing is reported when the scale is unknown: a tread depth in sheet units means nothing.
"""

from __future__ import annotations

import math

import numpy as np

from ..schema import Element, Prov, Sheet

PITCH_RANGE_M = (0.18, 0.45)       # a tread cannot be outside this
TREAD_LEN_M = (0.55, 3.6)          # nor a flight's width
FLIGHT_MAX_M = 7.0                 # a single flight is shorter than this along its run
ANGLE_TOL_DEG = 2.0
GAP_MAX_M = 0.12                  # a tread broken into pieces: gaps up to this are still one tread
FLIGHT_END_TOL = 0.15              # treads of one flight start and end within 15% of their length of each other
LEVEL_EPS_M = 0.07                 # strokes this close in offset are one level (two treads are never < 0.18 m apart)
TOOTH_TOL_M = 0.04                 # a level within this of a tooth belongs to it
MIN_TEETH = 4
NOISE_FLOOR_M = 0.01               # drawing noise: a fit is never treated as tighter than this
P_ACCEPT = 1e-3                    # chance of a false flight in a random band
TRUST_CONFIDENCE = 0.8             # calibrated probability a flight must reach before its numbers are trusted
TRUST_SD_M = 0.012                 # standard error of the pitch under which a depth is reported as trusted
PITCH_GRID = np.arange(PITCH_RANGE_M[0], PITCH_RANGE_M[1] + 1e-9, 0.0025)


# ---- segments, directions, bands -----------------------------------------------------------------------------------


def _segments(sheet: Sheet, mpu: float):
    """(primitive id, x0, y0, x1, y1) for every straight stroke, polylines split into their segments."""
    out = []
    for p in sheet.primitives:
        if p.hidden or p.prov.evidence.get("dim_graphic") or p.kind not in ("line", "polyline", "polygon"):
            continue
        pts = list(p.pts) + ([p.pts[0]] if p.kind == "polygon" and len(p.pts) > 2 else [])
        for a, b in zip(pts, pts[1:]):
            if 0.1 <= math.hypot(b[0] - a[0], b[1] - a[1]) * mpu <= TREAD_LEN_M[1]:
                out.append((p.id, a[0], a[1], b[0], b[1]))
    return out


def _direction_groups(angles: np.ndarray) -> list[np.ndarray]:
    """Indices grouped by direction (mod 180 degrees), consecutive angles within ANGLE_TOL_DEG joined, wrapping around."""
    order = np.argsort(angles)
    groups, cur = [], [order[0]]
    for a, b in zip(order, order[1:]):
        if angles[b] - angles[a] <= ANGLE_TOL_DEG:
            cur.append(b)
        else:
            groups.append(cur)
            cur = [b]
    groups.append(cur)
    if len(groups) > 1 and angles[order[0]] + 180.0 - angles[order[-1]] <= ANGLE_TOL_DEG:
        groups[0] = groups.pop() + groups[0]
    return [np.array(g) for g in groups]


def _bands(a: np.ndarray, b: np.ndarray) -> list[list[int]]:
    """Strokes whose intervals along the stroke direction overlap (transitively) form one band."""
    order = np.argsort(a)
    bands, cur, reach = [], [order[0]], b[order[0]]
    for i in order[1:]:
        if a[i] <= reach:
            cur.append(i)
            reach = max(reach, b[i])
        else:
            bands.append(cur)
            cur, reach = [i], b[i]
    bands.append(cur)
    return bands


def _flights(off: np.ndarray, ua: np.ndarray, ub: np.ndarray) -> list[list[tuple]]:
    """Candidate flights: tread runs that share the same interval along the stroke direction.

    1. strokes at one offset (within LEVEL_EPS_M) and joined end to end (gaps up to GAP_MAX_M, a broken tread) form a
       run; two runs on one line separated by more than that are different treads (the two flights of a U-shaped stair);
    2. runs are grouped by interval: a flight's treads start and end at the same places;
    3. runs of a group within LEVEL_EPS_M of one another are one tread drawn twice (edge and nosing).
    Each result item is (offset, start, end, length, stroke indices).
    """
    order = np.argsort(off)
    levels, cur = [], [order[0]]
    for x, y in zip(order, order[1:]):
        if off[y] - off[x] <= LEVEL_EPS_M:
            cur.append(y)
        else:
            levels.append(cur)
            cur = [y]
    levels.append(cur)
    runs = []
    for lv in levels:
        lv = sorted(lv, key=lambda i: ua[i])
        piece = [lv[0]]
        reach = ub[lv[0]]
        for i in lv[1:]:
            if ua[i] - reach <= GAP_MAX_M:
                piece.append(i)
                reach = max(reach, ub[i])
            else:
                runs.append(piece)
                piece, reach = [i], ub[i]
        runs.append(piece)
    items = []
    for r in runs:
        s0, e0, cov = _union_length([(float(ua[i]), float(ub[i])) for i in r])
        if TREAD_LEN_M[0] <= e0 - s0 <= TREAD_LEN_M[1]:
            items.append((float(np.mean(off[r])), s0, e0, e0 - s0, r))
    items.sort(key=lambda t: t[1])
    clusters: list[list[tuple]] = []
    for it in items:
        for c in clusters:
            tol = FLIGHT_END_TOL * c[0][3] + 0.05
            if abs(it[1] - c[0][1]) <= tol and abs(it[2] - c[0][2]) <= tol:
                c.append(it)
                break
        else:
            clusters.append([it])
    out = []
    for c in clusters:
        c.sort(key=lambda t: t[0])
        merged = [c[0]]
        for it in c[1:]:
            if it[0] - merged[-1][0] <= LEVEL_EPS_M:
                prev = merged[-1]
                merged[-1] = ((prev[0] + it[0]) / 2, min(prev[1], it[1]), max(prev[2], it[2]),
                              max(prev[2], it[2]) - min(prev[1], it[1]), prev[4] + it[4])
            else:
                merged.append(it)
        out.append(merged)
    return out


def _union_length(iv: list[tuple[float, float]]) -> tuple[float, float, float]:
    """(start, end, covered length) of the union of intervals."""
    iv = sorted(iv)
    covered = 0.0
    cs, ce = iv[0]
    for s, e in iv[1:]:
        if s <= ce + 1e-9:
            ce = max(ce, e)
        else:
            covered += ce - cs
            cs, ce = s, e
    covered += ce - cs
    return iv[0][0], max(e for _, e in iv), covered


# ---- the comb ------------------------------------------------------------------------------------------------------


def _best_combs(offsets: np.ndarray, top: int = 3) -> list[tuple[float, float]]:
    """Candidate (pitch, phase) pairs with the strongest periodicity of the offsets (Rayleigh statistic)."""
    best = []
    for p in PITCH_GRID:
        z = np.exp(2j * np.pi * offsets / p).mean()
        best.append((abs(z), p, (np.angle(z) / (2 * np.pi)) * p))
    best.sort(reverse=True)
    out, used = [], []
    for _, p, phi in best:
        if all(abs(p - q) > 0.02 for q in used):
            out.append((float(p), float(phi)))
            used.append(p)
        if len(out) >= top:
            break
    return out


def _run_of_teeth(offsets: np.ndarray, p: float, phi: float) -> list[int]:
    """Indices of the levels in the longest run of consecutive teeth (one gap allowed: an occluded tread)."""
    k = np.rint((offsets - phi) / p).astype(int)
    near = np.abs(offsets - phi - k * p) <= TOOTH_TOL_M
    teeth = sorted(set(k[near].tolist()))
    if not teeth:
        return []
    best, cur = [], [teeth[0]]
    for t in teeth[1:]:
        if t - cur[-1] <= 2:
            cur.append(t)
        else:
            best = max(best, cur, key=len)
            cur = [t]
    best = max(best, cur, key=len)
    keep = set(range(best[0], best[-1] + 1))
    return [i for i in range(len(offsets)) if near[i] and int(k[i]) in keep]


def _p_value(n_levels: int, run_teeth: int, pitch: float, tol: float) -> float:
    """Chance that `n_levels` random offsets would put one level inside each of `run_teeth` consecutive teeth.

    Each tooth is a window of width 2*tol (tol = the fit's own worst residual, never below the drawing-noise floor);
    the levels are spread over run_teeth*pitch. Ordered choices of distinct levels for the teeth give
    N!/(N-m)! * (2*tol/span)^m. Multiplied by the number of combs that were tried (pitches x phases), a Bonferroni bound.
    """
    m, span = run_teeth, run_teeth * pitch
    log_p = sum(math.log(max(n_levels - i, 1)) for i in range(m)) + m * math.log(min(1.0, 2 * tol / span))
    tests = len(PITCH_GRID) * max(1.0, pitch / (2 * tol))
    return float(min(1.0, math.exp(min(0.0, log_p)) * tests))


def _fit(k: np.ndarray, o: np.ndarray) -> tuple[float, float]:
    """Least-squares pitch and its standard error from tooth index and mean offset."""
    kc = k - k.mean()
    slope = float((kc * (o - o.mean())).sum() / (kc * kc).sum())
    resid = o - o.mean() - slope * kc
    dof = max(1, len(k) - 2)
    return abs(slope), float(math.sqrt((resid ** 2).sum() / dof) / math.sqrt((kc * kc).sum()))


def features(ev: dict) -> list[float]:
    """The few numbers the confidence model reads (all from the finder's own evidence)."""
    return [math.log10(max(ev["p_value"], 1e-12)), float(ev["n_levels"]), abs(ev["tread_depth_m"] - 0.28),
            1.0 if 0.8 <= ev["width_m"] <= 2.6 else 0.0, ev["tread_depth_sd_m"]]


def calibrated(ev: dict) -> float | None:
    """Estimated probability that a detection is a real stair, from stairs_calibration.json when it exists."""
    import json
    from pathlib import Path

    path = Path(__file__).with_name("stairs_calibration.json")
    if not path.exists():
        return None
    m = json.loads(path.read_text(encoding="utf-8"))
    z = (np.array(features(ev)) - np.array(m["mean"])) / np.array(m["std"])
    return float(1 / (1 + math.exp(-(float(z @ np.array(m["coef"])) + m["intercept"]))))


def note(trace: list | None, why: str) -> None:
    if trace is not None:
        trace.append(why)


def _consecutive(k: np.ndarray) -> np.ndarray:
    """Mask of the longest run of tooth indices with gaps of at most one missing tooth."""
    teeth = sorted(set(k.tolist()))
    best, cur = [], [teeth[0]]
    for t in teeth[1:]:
        if t - cur[-1] <= 2:
            cur.append(t)
        else:
            best = max(best, cur, key=len)
            cur = [t]
    best = set(max(best, cur, key=len))
    return np.array([int(x) in best for x in k])


def find_stairs(sheet: Sheet, mpu: float | None, trace: list | None = None, _tests: int | None = None) -> list[Element]:
    if not mpu:
        return []
    segs = _segments(sheet, mpu)
    if len(segs) < MIN_TEETH:
        return []
    ids = [s[0] for s in segs]
    A = np.array([[s[1], s[2]] for s in segs], float)
    B = np.array([[s[3], s[4]] for s in segs], float)
    angle = np.degrees(np.arctan2(B[:, 1] - A[:, 1], B[:, 0] - A[:, 0])) % 180.0
    out: list[Element] = []
    claimed: set[int] = set()
    work = []                                           # every candidate flight on the sheet
    for group in _direction_groups(angle):
        if len(group) < MIN_TEETH:
            continue
        th = math.radians(float(np.median(angle[group])))
        u, n = np.array([math.cos(th), math.sin(th)]), np.array([-math.sin(th), math.cos(th)])
        pa, pb = A[group] @ u * mpu, B[group] @ u * mpu
        ua, ub = np.minimum(pa, pb), np.maximum(pa, pb)
        off = (A[group] @ n + B[group] @ n) / 2 * mpu
        for info in _flights(off, ua, ub):
            if len(info) >= MIN_TEETH:
                work.append((group, u, n, info))
    sheet_tests = _tests or 1                           # second pass: corrected for every candidate that got this far
    reached = 0
    for group, u, n, info in work:
        if True:
            lo = np.array([i[0] for i in info])
            for pitch0, phi in _best_combs(lo):
                run = _run_of_teeth(lo, pitch0, phi)
                if len(run) < MIN_TEETH:
                    continue
                run = np.array(run)
                # the treads of one flight share a length and start and end together; the first and last strokes often do
                # not (a landing edge, a rail), so such strokes are set aside instead of failing the whole flight
                c0 = np.array([info[i][3] for i in run])
                s0 = np.array([info[i][1] for i in run])
                e0 = np.array([info[i][2] for i in run])
                mc = float(np.median(c0))
                good = (np.abs(c0 - mc) <= 0.3 * mc) & (np.abs(s0 - np.median(s0)) <= FLIGHT_END_TOL * mc)                     & (np.abs(e0 - np.median(e0)) <= FLIGHT_END_TOL * mc)
                run = run[good]
                if len(run) < MIN_TEETH:
                    note(trace, "treads differ in length or ends")
                    continue
                k = np.rint((lo[run] - phi) / pitch0).astype(int)
                keep = _consecutive(k)
                run, k = run[keep], k[keep]
                if len(run) < MIN_TEETH:
                    note(trace, "treads not consecutive")
                    continue
                teeth = sorted(set(k.tolist()))
                if len(teeth) < MIN_TEETH:
                    continue
                mean_off = np.array([float(np.mean(lo[run][k == t])) for t in teeth])
                pitch, sd = _fit(np.array(teeth, float), mean_off)
                if not (PITCH_RANGE_M[0] <= pitch <= PITCH_RANGE_M[1]) or pitch * (teeth[-1] - teeth[0]) > FLIGHT_MAX_M:
                    continue
                covs = np.array([info[i][3] for i in run])
                if covs.max() > 1.35 * np.median(covs) or covs.min() < 0.65 * np.median(covs):
                    note(trace, "tread lengths differ")
                    continue
                starts, ends = np.array([info[i][1] for i in run]), np.array([info[i][2] for i in run])
                tol = 0.15 * float(np.median(covs))
                if np.ptp(starts) > 2 * tol or np.ptp(ends) > 2 * tol:
                    note(trace, "tread ends do not line up")
                    continue
                inside = (lo >= mean_off.min() - TOOTH_TOL_M) & (lo <= mean_off.max() + TOOTH_TOL_M)
                in_run = np.zeros(len(lo), bool)
                in_run[run] = True
                if int((inside & ~in_run).sum()) > 0.25 * len(teeth):
                    note(trace, "strokes between the treads: texture")
                    continue
                reached += 1
                window = int(((lo >= mean_off.min() - pitch) & (lo <= mean_off.max() + pitch)).sum())
                fit_resid = np.abs(mean_off - (mean_off.mean() + (np.array(teeth) - np.mean(teeth)) * pitch)).max()
                pv = min(1.0, sheet_tests * _p_value(window, len(teeth), pitch, max(float(fit_resid), NOISE_FLOOR_M)))
                if pv >= P_ACCEPT:
                    note(trace, f"not significant (p={pv:.1e}, {len(teeth)} treads)")
                    continue
                members = sorted({int(group[i]) for r in run for i in info[r][4]})
                if any(m in claimed for m in members):
                    continue
                claimed.update(members)
                x0, x1 = float(starts.min()) / mpu, float(ends.max()) / mpu
                y0, y1 = float(mean_off.min()) / mpu, float(mean_off.max()) / mpu
                corners = [x0 * u + y0 * n, x1 * u + y0 * n, x1 * u + y1 * n, x0 * u + y1 * n]
                ev = {"tread_depth_m": round(pitch, 4), "tread_depth_sd_m": round(sd, 4),
                      "width_m": round(float(np.median(covs)), 3), "n_levels": len(teeth),
                      "steps_min": len(teeth) - 1, "steps_max": len(teeth), "p_value": pv, "shape": "straight"}
                conf = calibrated(ev)
                ev["confidence_source"] = "calibrated on labelled drawings (stairs_calibration.json)" if conf is not None                     else "significance only (1 - p_value); not calibrated"
                conf = conf if conf is not None else 1.0 - pv
                ev["trusted"] = bool(sd <= TRUST_SD_M and pv < P_ACCEPT / 10 and conf >= TRUST_CONFIDENCE)
                out.append(Element(
                    id=f"stair_{len(out)}", cls="stair", geom=[(float(c[0]), float(c[1])) for c in corners],
                    member_ids=[ids[m] for m in members],
                    prov=Prov(source="derived", stage="stairs_v2", confidence=round(conf, 4), evidence=ev)))
                break
    if _tests is None and reached > 1:
        return find_stairs(sheet, mpu, trace, _tests=reached)
    return out
