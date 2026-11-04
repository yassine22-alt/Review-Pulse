"""Learned wall / door / window segmentation for raster pages (R13 step 3, decision A14).

The model (scripts/train_raster_seg.py) was trained at a known median wall thickness in pixels;
a new page is first rescaled so that its own wall thickness matches, which makes the model
independent of scan resolution and drawing scale. Prediction runs on overlapping tiles.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[4] / "data" / "models" / "raster_seg"
TILE = 1024
OVERLAP = 128


def model_available(model_dir: Path = MODEL_DIR) -> bool:
    return (model_dir / "best.pt").exists()


@lru_cache(maxsize=1)
def _load(model_dir: str = str(MODEL_DIR)):
    import segmentation_models_pytorch as smp
    import torch

    ck = torch.load(Path(model_dir) / "best.pt", map_location="cpu", weights_only=False)
    cfg = ck["config"]
    model = smp.Unet(cfg["encoder"], encoder_weights=None, in_channels=3, classes=len(cfg["classes"]))
    model.load_state_dict(ck["state_dict"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return model.to(device).eval(), cfg, device


def estimate_wall_thickness_px(binary: np.ndarray) -> float | None:
    """Dominant wall thickness: the mode of 2 x distance-transform values along the skeleton,
    ignoring strokes thinner than 3 px (dimension lines, text, hatch)."""
    from scipy import ndimage
    from skimage.morphology import skeletonize

    if binary.sum() < 100:
        return None
    dt = ndimage.distance_transform_edt(binary)
    v = 2 * dt[skeletonize(binary)]
    v = v[v >= 3]
    if len(v) < 50:
        return None
    hist, edges = np.histogram(v, bins=np.arange(3, max(5, v.max() + 2), 1.0))
    return float(edges[int(np.argmax(hist))] + 0.5)


def wall_thickness_modes(binary: np.ndarray, min_share: float = 0.08) -> list[float]:
    """All significant wall-thickness classes (e.g. exterior and partition walls), thinnest first.
    A class is a peak of the skeleton-length-weighted stroke-width histogram that holds at least
    ``min_share`` of the stroke length and is clearly thicker than the drawing's line weight."""
    from scipy import ndimage
    from skimage.morphology import skeletonize

    if binary.sum() < 100:
        return []
    dt = ndimage.distance_transform_edt(binary)
    v = 2 * dt[skeletonize(binary)]
    if len(v) < 50:
        return []
    hist, edges = np.histogram(v, bins=np.arange(0, v.max() + 2, 1.0))
    smooth = np.convolve(hist, np.ones(3), mode="same")
    total = hist.sum()
    peaks = []
    for i in range(len(smooth)):
        lo, hi = max(i - 1, 0), min(i + 2, len(smooth))
        if smooth[i] < smooth[lo:hi].max() or smooth[i] == 0:
            continue
        if hist[max(i - 2, 0):i + 3].sum() >= min_share * total:
            c = float(edges[i] + 0.5)
            if not peaks or c - peaks[-1] > 2:
                peaks.append(c)
    if not peaks:
        return []
    # the thinnest class is the pen weight of the line work; walls are clearly heavier than it
    walls = [p for p in peaks[1:] if p >= max(3.0, 1.8 * peaks[0])]
    return walls or ([peaks[0]] if peaks[0] >= 3 else [])


def predict_refined(gray: np.ndarray, binary: np.ndarray | None = None, tol: float = 0.25):
    """``predict`` at the scale where the page's walls match the training wall thickness, with that
    thickness measured on the model's own wall mask (ink-based estimates see the outlines of hollow
    or grey walls, not the walls). The mask measure is stable while walls are shown at or below
    training size and collapses when they are blown up (the model then marks only their outlines),
    so the page is probed downscaled - the training convention (longest side ``max_side``) and half
    of it - and the probes' thickness decides the final scale. Falls back to the ink estimate.
    Returns (prob, class map, rescale, wall thickness in page px or None)."""
    cfg = _load()[1]
    s0 = cfg.get("max_side", 1024) / max(gray.shape)
    probes = []
    for s in (s0, s0 / 2):
        _p, c, used = predict(gray, t_px=cfg["train_wall_thickness_px"] / s)
        t = median_wall_thickness_px(c == 1)
        if t:
            probes.append(t)
    t = float(np.mean(probes)) if probes else None
    prob, cls, s = predict(gray, binary if t is None else None, t_px=t)
    t_final = median_wall_thickness_px(cls == 1)
    if t and t_final and abs(t_final / t - 1) <= tol:
        t = t_final
    return prob, cls, s, t


def median_wall_thickness_px(wall: np.ndarray) -> float | None:
    """The training script's measure (median of 2 x distance transform on the wall skeleton), so a
    page is compared with ``train_wall_thickness_px`` like for like."""
    from scipy import ndimage
    from skimage.morphology import skeletonize

    if wall.sum() < 50:
        return None
    v = ndimage.distance_transform_edt(wall)[skeletonize(wall)]
    return float(2 * np.median(v)) if len(v) else None


def predict(gray: np.ndarray, binary: np.ndarray | None = None,
            t_px: float | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    """Class probabilities (C, H, W) at the page's own resolution, the class map, and the rescale
    factor that was applied (page px -> model px). The page wall thickness is ``t_px`` when given,
    otherwise estimated from ``binary``."""
    import torch
    import torch.nn.functional as F
    from PIL import Image

    model, cfg, device = _load()
    H, W = gray.shape
    scale = 1.0
    t = t_px or (estimate_wall_thickness_px(binary) if binary is not None else None)
    if t:
        scale = float(np.clip(cfg["train_wall_thickness_px"] / t, 0.15, 4.0))
    sw, sh = max(32, int(round(W * scale))), max(32, int(round(H * scale)))
    img = np.asarray(Image.fromarray(gray).resize((sw, sh), Image.BILINEAR), np.float32) / 255.0
    a = (img - cfg["norm_mean"]) / cfg["norm_std"]
    C = len(cfg["classes"])
    acc = np.zeros((C, sh, sw), np.float32)
    cnt = np.zeros((sh, sw), np.float32)
    step = TILE - OVERLAP
    with torch.no_grad():
        for y0 in range(0, max(sh - OVERLAP, 1), step):
            for x0 in range(0, max(sw - OVERLAP, 1), step):
                tile = a[y0:y0 + TILE, x0:x0 + TILE]
                th, tw = tile.shape
                ph, pw = (32 - th % 32) % 32, (32 - tw % 32) % 32
                tp = np.pad(tile, ((0, ph), (0, pw)), constant_values=(1.0 - cfg["norm_mean"]) / cfg["norm_std"])
                x = torch.from_numpy(tp)[None, None].repeat(1, 3, 1, 1).to(device)
                with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                    p = model(x).float().softmax(1)[0, :, :th, :tw].cpu().numpy()
                acc[:, y0:y0 + th, x0:x0 + tw] += p
                cnt[y0:y0 + th, x0:x0 + tw] += 1
    prob = acc / np.maximum(cnt, 1)
    t = torch.from_numpy(prob)[None]
    prob = F.interpolate(t, size=(H, W), mode="bilinear", align_corners=False)[0].numpy()
    return prob, prob.argmax(0).astype(np.uint8), scale


def model_info() -> dict:
    p = MODEL_DIR / "config.json"
    return json.loads(p.read_text()) if p.exists() else {}
