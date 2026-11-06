"""Accuracy of the stair finder against synthetic stairs with known truth."""
import statistics
import sys
from collections import defaultdict
from reviewpulse.perception.stairs import find_stairs
from reviewpulse.xeval.stairgen import make_case

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
det = errs = 0
rel = []
miss_by_style = defaultdict(lambda: [0, 0])
n_ok = steps_ok = cover = trusted_n = trusted_bad = 0
for s in range(N):
    c = make_case(s, True)
    found = find_stairs(c.sheet, c.mpu)
    for st in c.styles:
        miss_by_style[st][1] += 1
    # match: a detection whose width agrees with the truth
    hit = [e for e in found if abs(e.prov.evidence["width_m"] - c.width) < 0.25 * c.width + 0.05]
    if not hit:
        for st in c.styles:
            miss_by_style[st][0] += 1
        continue
    e = max(hit, key=lambda x: x.prov.evidence["n_levels"])
    ev = e.prov.evidence
    det += 1
    err = abs(ev["tread_depth_m"] - c.pitch)
    errs += 1
    rel.append(err)
    cover += err <= 2 * max(ev["tread_depth_sd_m"], 0.002)
    n_ok += ev["n_levels"] == c.treads
    steps_ok += ev["steps_min"] <= c.treads - 1 <= ev["steps_max"] or ev["steps_min"] <= c.treads <= ev["steps_max"]
    if ev["trusted"]:
        trusted_n += 1
        trusted_bad += err > 0.01
fp_cases = fp = 0
for s in range(1000, 1000 + N):
    c = make_case(s, False)
    fp_cases += 1
    fp += bool(find_stairs(c.sheet, c.mpu))
rel.sort()
print(f"stairs found {det}/{N} = {det / N:.0%}")
print(f"tread depth error: median {statistics.median(rel) * 100:.2f} cm, 95th pct {rel[int(0.95 * len(rel))] * 100:.2f} cm, max {rel[-1] * 100:.2f} cm")
print(f"error within 2 standard errors (calibration, ideal ~95%): {cover}/{det} = {cover / det:.0%}")
print(f"number of treads exactly right: {n_ok}/{det}; true step count inside [steps_min, steps_max]: {steps_ok}/{det}")
print(f"marked trusted: {trusted_n}, of which depth off by more than 1 cm: {trusted_bad}")
print(f"false stair on drawings with clutter but no stair: {fp}/{fp_cases}")
print("missed, by style present (missed/total):", {k: f"{v[0]}/{v[1]}" for k, v in sorted(miss_by_style.items())})
