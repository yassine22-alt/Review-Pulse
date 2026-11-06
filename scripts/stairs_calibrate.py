"""Turn the stair finder's evidence into a calibrated probability that a detection is a real stair.

Labels come from FloorPlanCAD's stair class and are used ONLY here, to fit and check a 5-number logistic model.
The model is fitted on one set of drawings and its calibration is checked on drawings it never saw."""
import json, math, random, sys
from pathlib import Path
import numpy as np
from reviewpulse.ingest.svg_reader import extract_svg
from reviewpulse.perception.stairs import find_stairs, features



def fit_logistic(X, y, l2=1.0, iters=50):
    """Ridge-regularised logistic regression by Newton steps on standardised features. Returns (w, b, mean, std)."""
    mean, std = X.mean(0), X.std(0) + 1e-9
    Z = np.hstack([(X - mean) / std, np.ones((len(X), 1))])
    w = np.zeros(Z.shape[1])
    R = np.eye(Z.shape[1]) * l2; R[-1, -1] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) + R @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + R + 1e-9 * np.eye(Z.shape[1])
        w -= np.linalg.solve(H, g)
    return w[:-1], float(w[-1]), mean, std


def predict(model, X):
    w, b, mean, std = model
    return 1 / (1 + np.exp(-(((X - mean) / std) @ w + b)))

ROOT = Path("../Review-Pulse/reviewpulse/data/raw/floorplancad/FloorPlanCAD")
files = sorted(ROOT.glob("*/*.svg")); random.Random(11).shuffle(files)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 500
X, y, fid = [], [], []
for k, f in enumerate(files[:N]):
    if f.stat().st_size > 6_000_000: continue
    try:
        sheet = extract_svg(f, f.stem); st = find_stairs(sheet, 0.1)
    except Exception:
        continue
    gt = {p.id for p in sheet.primitives if (p.prov.evidence.get("gt") or {}).get("semantic") == 28}
    for e in st:
        X.append(features(e.prov.evidence)); y.append(int(len(set(e.member_ids) & gt) >= 0.5 * len(e.member_ids))); fid.append(k)
X, y, fid = np.array(X), np.array(y), np.array(fid)
train = fid < N * 0.6
model = fit_logistic(X[train], y[train])
p = predict(model, X[~train])
yt = y[~train]
print(f"detections: {len(y)}  real {y.sum()}  (train {train.sum()}, held-out {(~train).sum()})")
print("held-out Brier score %.3f  (always-the-base-rate: %.3f)" % (((p - yt) ** 2).mean(), ((yt.mean() - yt) ** 2).mean()))
for lo, hi in ((0, .5), (.5, .8), (.8, .9), (.9, .97), (.97, 1.01)):
    m = (p >= lo) & (p < hi)
    if m.sum(): print(f"predicted {lo:.2f}-{min(hi,1):.2f}: {m.sum():4d} detections, actually real {yt[m].mean():.0%}")
for thr in (0.5, 0.8, 0.9):
    m = p >= thr; print(f"keep if p>={thr}: keeps {m.sum()}/{len(p)} detections, precision {yt[m].mean():.0%}")
w, b, mean, std = fit_logistic(X, y)
Path("src/reviewpulse/perception/stairs_calibration.json").write_text(json.dumps(
    {"features": ["log10_p", "n_levels", "pitch_dev", "width_ok", "sd"], "coef": w.tolist(), "mean": mean.tolist(), "std": std.tolist(),
     "intercept": b, "fit_on": "FloorPlanCAD detections, %d drawings" % N,
     "heldout_brier": float(((p - yt) ** 2).mean())}, indent=1), encoding="utf-8")
