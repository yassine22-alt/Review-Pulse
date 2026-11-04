"""Train the learned primitive classifier (wall / door / window / other) on several drawing styles.

    python scripts/train_primitive_classifier.py --n-train 6965 --n-val 810 --synth 2000 --synth-val 300

Domains:
- FloorPlanCAD train/val (real CAD drawings, labels from the dataset's per-primitive annotations);
- generated plans (synth/random_plan.py: four wall styles, five door styles, four layer schemes,
  metres or millimetres, DXF and PDF), labelled from the generator's truth geometry;
- ArchCAD train/val (optional, --archcad N): real CAD slices with no colours, layers or line weights,
  so walls must be told from geometry alone (eval/adapters/archcad.py; its test split is never used).
A classifier trained on one style rejects walls drawn in another (measured: every wall of a generated
plan was called "other" by the FloorPlanCAD-only model), so every style the product must read is in
the training set.

Features come from reviewpulse.perception.learned.features (rule pipeline run once per drawing, learned
pass off). Features are cached in data/cache/primitive_features/. LightGBM multiclass with early
stopping on the combined val set; the wall threshold maximises the mean of the per-domain
length-weighted wall F1. No test split is touched here.
Writes data/models/primitive_lgbm/{model.txt,meta.json} (or --out).
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "primitive_features"


def featurise_fpcad(path: str):
    from reviewpulse.annotate.text_classify import classify_items
    from reviewpulse.eval.adapters.floorplancad import GROUPS, UNIT_M
    from reviewpulse.ingest.svg_reader import extract_svg
    from reviewpulse.perception.learned.features import labels_from_gt, sheet_features
    from reviewpulse.pipeline import build_model
    from reviewpulse.schema import Scale

    try:
        s = extract_svg(Path(path), Path(path).stem)
        classify_items(s.texts)
        s.scale = Scale(metres_per_unit=UNIT_M, method="user", confidence=1.0)
        m = build_model(s, learned=False)
        ids, X = sheet_features(m)
        return X, labels_from_gt(m, ids, GROUPS)
    except Exception as e:  # noqa: BLE001 - one bad drawing must not stop training
        print("skip", path, repr(e)[:120], flush=True)
        return None


def featurise_synth(seed: int):
    """Both formats of one generated plan."""
    from reviewpulse.ingest.classify import inspect_file
    from reviewpulse.perception.learned.features import sheet_features
    from reviewpulse.perception.learned.synth_labels import labels_from_synth_truth
    from reviewpulse.pipeline import build_model, extract_stub
    from reviewpulse.synth.random_plan import random_plan

    try:
        with tempfile.TemporaryDirectory() as td:
            p = random_plan(td, seed=seed)
            truth = json.loads(Path(p["truth"]).read_text(encoding="utf-8"))
            Xs, ys = [], []
            for fmt in ("dxf", "pdf"):
                stub = inspect_file(p[fmt])[0]
                m = build_model(extract_stub(stub, Path(td), preview=False), learned=False)
                ids, X = sheet_features(m)
                Xs.append(X)
                ys.append(labels_from_synth_truth(m, ids, truth, fmt))
            return np.concatenate(Xs), np.concatenate(ys)
    except Exception as e:  # noqa: BLE001
        print("skip synth", seed, repr(e)[:120], flush=True)
        return None


def featurise_archcad(name: str):
    from reviewpulse.eval.adapters import archcad
    from reviewpulse.perception.learned.features import labels_from_gt, sheet_features
    from reviewpulse.pipeline import build_model

    try:
        m = build_model(archcad.load_sheet(ROOT / "data", name), learned=False)
        ids, X = sheet_features(m)
        return X, labels_from_gt(m, ids, archcad.GROUPS)
    except Exception as e:  # noqa: BLE001
        print("skip archcad", name, repr(e)[:120], flush=True)
        return None


def collect(fn, items: list, workers: int, tag: str):
    Xs, ys = [], []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for k, res in enumerate(ex.map(fn, items, chunksize=4)):
            if res is not None and len(res[0]):
                Xs.append(res[0])
                ys.append(res[1])
            if (k + 1) % 200 == 0:
                print(f"  {tag}: featurised {k + 1}/{len(items)}", flush=True)
    return np.concatenate(Xs), np.concatenate(ys)


def cached(name: str, fn, items: list, workers: int, chunk: int = 500):
    """Features of ``items``, saved per chunk so an interrupted run resumes where it stopped."""
    from reviewpulse.perception.learned.features import FEATURES

    d = CACHE / name
    d.mkdir(parents=True, exist_ok=True)
    Xs, ys = [], []
    for k in range(0, len(items), chunk):
        path = d / f"{k:06d}.npz"
        if path.exists():
            try:
                # closed before a recompute replaces it: Windows refuses to rename over an open file
                with np.load(path, allow_pickle=False) as z:
                    same = list(z["features"]) == list(FEATURES)
                    if same:
                        Xs.append(z["X"])
                        ys.append(z["y"])
                if same:
                    continue
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                print(f"{path.name}: unreadable (interrupted write), recomputing", flush=True)
        X, y = collect(fn, items[k:k + chunk], workers, f"{name} {k}")
        tmp = path.with_name(path.stem + ".tmp.npz")
        np.savez_compressed(tmp, X=X, y=y, features=np.array(FEATURES))
        _durable_replace(tmp, path)    # a power cut never leaves a half-written chunk
        Xs.append(X)
        ys.append(y)
        print(f"{name}: {min(k + chunk, len(items))}/{len(items)} drawings cached", flush=True)
    return np.concatenate(Xs), np.concatenate(ys)


CKPT_EVERY = 100        # boosting rounds between checkpoints (about 7 min on the full data)
PATIENCE = 100          # early stopping: rounds without a better validation loss


def _durable_replace(tmp: Path, dst: Path) -> None:
    """Flush ``tmp`` to disk, then rename it over ``dst``: after a power cut the file holds either the
    previous or the new content. A rename alone is not enough: the rename can reach the disk before
    the data does, leaving a file of zeros."""
    with open(tmp, "rb+") as f:
        os.fsync(f.fileno())
    tmp.replace(dst)


def train_resumable(lgb, params: dict, dtr, dva, rounds: int, out: Path, fingerprint: dict):
    """lgb.train with a checkpoint every CKPT_EVERY rounds: a run cut by a shutdown continues from its
    last checkpoint instead of starting over. Early stopping keeps its best round across resumes; a
    checkpoint from other data or parameters is ignored. (Bagging draws after a resume differ from an
    uninterrupted run, so the result is equivalent, not bit-identical.)"""
    out.mkdir(parents=True, exist_ok=True)
    ckpt, state_p = out / "checkpoint.txt", out / "checkpoint.json"
    fp = json.loads(json.dumps(fingerprint))
    state = {"fingerprint": fp, "iteration": 0, "best_score": None, "best_iter": 0}
    init = None
    if ckpt.exists() and state_p.exists():
        try:
            saved = json.loads(state_p.read_text(encoding="utf-8"))
            if saved.get("fingerprint") == fp:
                init, state = lgb.Booster(model_file=str(ckpt)), saved
                print(f"resuming from checkpoint at round {state['iteration']}", flush=True)
            else:
                print("checkpoint is from other data or parameters: starting over", flush=True)
        except (OSError, ValueError, lgb.basic.LightGBMError):
            print("checkpoint unreadable: starting over", flush=True)

    def checkpoint(env):
        it = env.iteration + 1                      # global: counts the rounds of the initial model
        score = env.evaluation_result_list[0][2]
        if state["best_score"] is None or score < state["best_score"]:
            state["best_score"], state["best_iter"] = score, it
        if it % CKPT_EVERY == 0:
            tmp = ckpt.with_name("checkpoint.tmp.txt")
            env.model.save_model(str(tmp))
            _durable_replace(tmp, ckpt)
            state["iteration"] = it
            tmp = state_p.with_name("checkpoint.tmp.json")
            tmp.write_text(json.dumps(state), encoding="utf-8")
            _durable_replace(tmp, state_p)
        if it - state["best_iter"] >= PATIENCE:
            raise lgb.callback.EarlyStopException(state["best_iter"] - 1, env.evaluation_result_list)

    left = rounds - state["iteration"]
    booster = init
    if left > 0 and state["iteration"] - state["best_iter"] < PATIENCE:
        booster = lgb.train(params, dtr, num_boost_round=left, valid_sets=[dva], init_model=init,
                            keep_training_booster=True, callbacks=[checkpoint, lgb.log_evaluation(200)])
    booster.best_iteration = state["best_iter"]
    return booster


def finish_checkpoint(out: Path) -> None:
    for name in ("checkpoint.txt", "checkpoint.json"):
        (out / name).unlink(missing_ok=True)


def wall_f1(prob, y, L, t, wall):
    call = prob[:, wall] >= t
    is_w = y == wall
    tp, fp, fn = L[call & is_w].sum(), L[call & ~is_w].sum(), L[~call & is_w].sum()
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def per_class(pred, y, classes):
    out = {}
    for c, name in enumerate(classes):
        tp = int(((pred == c) & (y == c)).sum())
        p = tp / max(int((pred == c).sum()), 1)
        r = tp / max(int((y == c).sum()), 1)
        out[name] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0}
    return out


def main() -> None:
    import lightgbm as lgb

    from reviewpulse.perception.learned.features import CLASSES, FEATURES

    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=6965)
    ap.add_argument("--n-val", type=int, default=810)
    ap.add_argument("--synth", type=int, default=2000, help="generated training plans (each DXF + PDF)")
    ap.add_argument("--synth-val", type=int, default=300)
    ap.add_argument("--synth-weight", type=float, default=0.3,
                    help="total weight of generated rows relative to FloorPlanCAD rows")
    ap.add_argument("--archcad", type=int, default=0, help="ArchCAD train slices (0: domain not used)")
    ap.add_argument("--archcad-val", type=int, default=600)
    ap.add_argument("--archcad-weight", type=float, default=0.5,
                    help="total weight of ArchCAD rows relative to FloorPlanCAD rows")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=4000)
    ap.add_argument("--lr", type=float, default=0.08)
    ap.add_argument("--out", default=str(ROOT / "data" / "models" / "primitive_lgbm"))
    ap.add_argument("--meta-only", action="store_true",
                    help="load the model already in --out and only (re)write meta.json")
    a = ap.parse_args()
    base = ROOT / "data" / "raw" / "floorplancad" / "FloorPlanCAD"
    tr = sorted(str(p) for p in (base / "train").glob("*.svg"))
    va = sorted(str(p) for p in (base / "val").glob("*.svg"))
    tr = tr[:: max(1, len(tr) // a.n_train)][: a.n_train]
    va = va[:: max(1, len(va) // a.n_val)][: a.n_val]
    t0 = time.time()
    # domain -> (train X, train y, val X, val y, total weight relative to FloorPlanCAD rows)
    dom = {"floorplancad": cached(f"fpcad_train_{len(tr)}", featurise_fpcad, tr, a.workers)
           + cached(f"fpcad_val_{len(va)}", featurise_fpcad, va, a.workers) + (1.0,)}
    dom["synth"] = (cached(f"synth_train_{a.synth}", featurise_synth, list(range(100000, 100000 + a.synth)), a.workers)
                    + cached(f"synth_val_{a.synth_val}", featurise_synth, list(range(200000, 200000 + a.synth_val)),
                             a.workers) + (a.synth_weight,))
    if a.archcad:
        from reviewpulse.eval.adapters import archcad

        def spread(names, n):
            return names[:: max(1, len(names) // n)][:n]

        atr = spread(archcad.names(ROOT / "data", "train"), a.archcad)
        ava = spread(archcad.names(ROOT / "data", "val"), a.archcad_val)
        dom["archcad"] = (cached(f"archcad_train_{len(atr)}", featurise_archcad, atr, a.workers)
                          + cached(f"archcad_val_{len(ava)}", featurise_archcad, ava, a.workers) + (a.archcad_weight,))
    n_ref = len(dom["floorplancad"][1])
    print(f"features {time.time() - t0:.0f}s: " + "; ".join(
        f"{k} {v[0].shape} classes {np.bincount(v[1], minlength=len(CLASSES)).tolist()}" for k, v in dom.items()),
        flush=True)

    X = np.concatenate([v[0] for v in dom.values()])
    y = np.concatenate([v[1] for v in dom.values()])
    counts = np.bincount(y, minlength=len(CLASSES)).astype(float)
    cw = {c: float(counts.sum() / (len(CLASSES) * max(n, 1))) ** 0.5 for c, n in enumerate(counts)}
    dw = np.concatenate([np.full(len(v[1]), v[4] * n_ref / max(len(v[1]), 1)) for v in dom.values()])
    w = np.array([cw[c] for c in y]) * dw
    dtr = lgb.Dataset(X, y, weight=w, feature_name=list(FEATURES))
    dva = lgb.Dataset(np.concatenate([v[2] for v in dom.values()]), np.concatenate([v[3] for v in dom.values()]),
                      reference=dtr)
    params = dict(objective="multiclass", num_class=len(CLASSES), learning_rate=a.lr, num_leaves=63,
                  min_data_in_leaf=50, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
                  lambda_l2=1.0, seed=7, verbose=-1, num_threads=a.workers)
    if a.meta_only:
        booster = lgb.Booster(model_file=str(Path(a.out) / "model.txt"))
    else:
        booster = train_resumable(lgb, params, dtr, dva, a.rounds, Path(a.out),
                                  fingerprint={"params": params, "rows": len(y),
                                               "val_rows": sum(len(v[3]) for v in dom.values()),
                                               "domains": sorted(dom), "rounds": a.rounds})

    li = list(FEATURES).index("length_m")
    wall = CLASSES.index("wall")
    pv = {k: booster.predict(v[2]) for k, v in dom.items()}
    best_t, best = 0.5, (-1.0, {})
    for t in np.arange(0.2, 0.81, 0.05):
        f1 = {k: float(wall_f1(pv[k], v[3], v[2][:, li], t, wall)) for k, v in dom.items()}   # numpy float32 is not JSON
        if np.mean(list(f1.values())) > best[0]:
            best_t, best = round(float(t), 2), (float(np.mean(list(f1.values()))), f1)
    print(f"wall threshold {best_t}: val length F1 " + ", ".join(f"{k} {v:.4f}" for k, v in best[1].items()), flush=True)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if not a.meta_only:
        booster.save_model(str(out / "model.txt"))       # at best_iteration
        finish_checkpoint(out)
    imp = {k: float(v) for k, v in sorted(zip(FEATURES, booster.feature_importance("gain").tolist()),
                                          key=lambda x: -x[1])[:15]}
    meta = {"classes": CLASSES, "features": FEATURES, "best_iteration": booster.best_iteration,
            "wall_threshold": best_t,
            "val_wall_length_f1_at_threshold": {k: round(v, 4) for k, v in best[1].items()},
            "val_per_primitive_count": {k: per_class(pv[k].argmax(1), v[3], CLASSES) for k, v in dom.items()},
            "data": {"floorplancad": {"train_drawings": len(tr), "val_drawings": len(va),
                                      "licence": "CC BY-NC 4.0"},
                     "synth": {"train_plans": a.synth, "val_plans": a.synth_val, "formats": ["dxf", "pdf"],
                               "weight": a.synth_weight}},
            "top_features_gain": imp, "seed": 7}
    if a.archcad:
        meta["data"]["archcad"] = {"train_slices": len(atr), "val_slices": len(ava), "licence": "CC BY-NC 4.0",
                                   "weight": a.archcad_weight}
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps(meta, indent=1), flush=True)


if __name__ == "__main__":
    main()
