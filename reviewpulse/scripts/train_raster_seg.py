"""Train the raster wall / door / window segmentation model (R13, decision A14).

    python scripts/train_raster_seg.py --epochs 40 --max-minutes 150

U-Net with an ImageNet-pretrained ResNet34 encoder (segmentation-models-pytorch), 4 classes
(background, wall, door, window), trained on CubiCasa5K train renders from
scripts/prepare_cubicasa_seg.py, selected on val mean IoU of wall/door/window.
Augmentations mimic scans: flips, 90-degree rotations, blur, noise, contrast, slight scale jitter.
Outputs data/models/raster_seg/{best.pt, config.json, log.jsonl}. Working checkpoints live in
data/models/raster_seg/train/ (best + last, written atomically) so a reader of best.pt - on Windows
a loaded checkpoint stays memory-mapped - can never break training; ``--resume`` continues from
last.pt with the same schedule, and best.pt is published once at the end.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "cubicasa_seg"
OUT = ROOT / "data" / "models" / "raster_seg"
N_CLASSES = 4


def save_atomic(obj, path: Path, tries: int = 10) -> None:
    import os

    tmp = path.with_suffix(".tmp")
    torch.save(obj, tmp)
    for i in range(tries):
        try:
            os.replace(tmp, path)
            return
        except OSError:
            time.sleep(2 + i)
    raise OSError(f"could not replace {path} (file in use)")


def wall_thickness_px(mask: np.ndarray) -> float | None:
    """Median wall thickness in pixels: 2 x distance-transform value on the wall skeleton."""
    from scipy import ndimage
    from skimage.morphology import skeletonize

    w = mask == 1
    if w.sum() < 50:
        return None
    dt = ndimage.distance_transform_edt(w)
    sk = skeletonize(w)
    v = dt[sk]
    return float(2 * np.median(v)) if len(v) else None


class Tiles(Dataset):
    def __init__(self, split: str, crop: int, train: bool, seed: int = 0):
        self.items = sorted(p for p in (DATA / split).glob("*.png") if not p.stem.endswith("_mask"))
        self.crop, self.train = crop, train
        self.rng = random.Random(seed)

    def __len__(self):
        return len(self.items)

    def _load(self, i):
        p = self.items[i]
        img = Image.open(p).convert("L")
        msk = Image.open(p.with_name(p.stem + "_mask.png"))
        return img, msk

    def __getitem__(self, i):
        img, msk = self._load(i)
        rng = random.Random(self.rng.random() * 1e9 + i) if self.train else random.Random(i)
        if self.train:
            s = rng.uniform(0.75, 1.25)
            size = (max(8, int(img.width * s)), max(8, int(img.height * s)))
            img, msk = img.resize(size, Image.BILINEAR), msk.resize(size, Image.NEAREST)
            if rng.random() < 0.3:
                img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.2)))
        a, m = np.asarray(img, np.float32) / 255.0, np.asarray(msk, np.int64)
        c = self.crop
        H, W = a.shape
        if H < c or W < c:
            ph, pw = max(0, c - H), max(0, c - W)
            a = np.pad(a, ((0, ph), (0, pw)), constant_values=1.0)
            m = np.pad(m, ((0, ph), (0, pw)), constant_values=0)
            H, W = a.shape
        if self.train:
            # bias crops towards content: try a few positions, keep the one with most structure
            best = None
            for _ in range(4):
                y, x = rng.randint(0, H - c), rng.randint(0, W - c)
                score = int((m[y:y + c, x:x + c] > 0).sum())
                if best is None or score > best[0]:
                    best = (score, y, x)
            _, y, x = best
            a, m = a[y:y + c, x:x + c], m[y:y + c, x:x + c]
            k = rng.randint(0, 3)
            a, m = np.rot90(a, k), np.rot90(m, k)
            if rng.random() < 0.5:
                a, m = a[:, ::-1], m[:, ::-1]
            if rng.random() < 0.5:
                lo, hi = rng.uniform(0.0, 0.25), rng.uniform(0.75, 1.0)
                a = lo + a * (hi - lo)
            if rng.random() < 0.3:
                a = a + np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, rng.uniform(0.01, 0.06), a.shape)
            a = np.clip(a, 0, 1)
        x = torch.from_numpy(np.ascontiguousarray(a)).float()[None].repeat(3, 1, 1)
        x = (x - 0.45) / 0.25
        return x, torch.from_numpy(np.ascontiguousarray(m))


def build_model():
    import segmentation_models_pytorch as smp

    return smp.Unet("resnet34", encoder_weights="imagenet", in_channels=3, classes=N_CLASSES)


def dice_loss(logits, target, eps=1.0):
    p = logits.softmax(1)
    oh = F.one_hot(target, N_CLASSES).permute(0, 3, 1, 2).float()
    inter = (p * oh).sum((0, 2, 3))
    union = p.sum((0, 2, 3)) + oh.sum((0, 2, 3))
    return 1 - ((2 * inter + eps) / (union + eps))[1:].mean()


@torch.no_grad()
def evaluate(model, ds: Tiles, device, max_items: int = 200) -> dict:
    model.eval()
    inter = np.zeros(N_CLASSES)
    union = np.zeros(N_CLASSES)
    for i in range(min(len(ds), max_items)):
        img, msk = ds._load(i)
        a = (np.asarray(img, np.float32) / 255.0 - 0.45) / 0.25
        H, W = a.shape
        ph, pw = (32 - H % 32) % 32, (32 - W % 32) % 32
        a = np.pad(a, ((0, ph), (0, pw)), constant_values=(1.0 - 0.45) / 0.25)
        x = torch.from_numpy(a)[None, None].repeat(1, 3, 1, 1).to(device)
        with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
            pred = model(x).argmax(1)[0, :H, :W].cpu().numpy()
        m = np.asarray(msk)
        for c in range(N_CLASSES):
            inter[c] += np.logical_and(pred == c, m == c).sum()
            union[c] += np.logical_or(pred == c, m == c).sum()
    iou = inter / np.maximum(union, 1)
    model.train()
    return {"iou_wall": float(iou[1]), "iou_door": float(iou[2]), "iou_window": float(iou[3]),
            "miou_fg": float(iou[1:].mean())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--crop", type=int, default=512)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--max-minutes", type=float, default=150)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--resume", action="store_true", help="continue from train/last.pt")
    a = ap.parse_args()
    random.seed(a.seed)
    np.random.seed(a.seed)
    torch.manual_seed(a.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    OUT.mkdir(parents=True, exist_ok=True)

    train = Tiles("train", a.crop, True, a.seed)
    val = Tiles("val", a.crop, False)
    # median wall thickness of the training renders (the inference rescaling target)
    t_px = [wall_thickness_px(np.asarray(Image.open(p.with_name(p.stem + "_mask.png"))))
            for p in train.items[:: max(1, len(train.items) // 200)]]
    t_px = float(np.median([t for t in t_px if t]))
    config = {"arch": "Unet", "encoder": "resnet34", "classes": ["background", "wall", "door", "window"],
              "norm_mean": 0.45, "norm_std": 0.25, "train_wall_thickness_px": t_px, "crop": a.crop,
              "seed": a.seed, "data": "CubiCasa5K train (CC BY-NC 4.0)", "max_side": 1024}
    (OUT / "config.json").write_text(json.dumps(config, indent=1))
    print("train", len(train), "val", len(val), "wall thickness px", round(t_px, 2), "device", device, flush=True)

    dl = DataLoader(train, batch_size=a.batch, shuffle=True, num_workers=a.workers, drop_last=True,
                    persistent_workers=a.workers > 0, pin_memory=True)
    model = build_model().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    steps = a.epochs * len(dl)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: 0.5 * (1 + math.cos(math.pi * min(s, steps) / steps)))
    weights = torch.tensor([0.5, 1.0, 2.0, 2.0], device=device)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")
    t0, best, start, spent = time.time(), -1.0, 0, 0.0
    WORK = OUT / "train"
    WORK.mkdir(exist_ok=True)
    if a.resume and (WORK / "last.pt").exists():
        ck = torch.load(WORK / "last.pt", map_location=device, weights_only=False)
        model.load_state_dict(ck["state_dict"])
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        scaler.load_state_dict(ck["scaler"])
        start, best, spent = ck["epoch"], ck["best"], ck["minutes"]
        torch.set_rng_state(ck["rng"])
        print(f"resumed after epoch {start}, best {best:.4f}, {spent:.1f} min spent", flush=True)
    t0 -= spent * 60
    log = open(OUT / "log.jsonl", "a")
    for ep in range(start, a.epochs):
        tot, n = 0.0, 0
        for x, y in dl:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                out = model(x)
                loss = F.cross_entropy(out, y, weight=weights) + dice_loss(out.float(), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot += float(loss.detach())
            n += 1
            if n % 100 == 0:
                print(f"epoch {ep + 1} step {n}/{len(dl)} loss {tot / n:.4f} "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
        metrics = evaluate(model, val, device)
        rec = {"epoch": ep + 1, "loss": round(tot / max(n, 1), 4), **{k: round(v, 4) for k, v in metrics.items()},
               "minutes": round((time.time() - t0) / 60, 1)}
        print(json.dumps(rec), flush=True)
        log.write(json.dumps(rec) + "\n")
        log.flush()
        if metrics["miou_fg"] > best:
            best = metrics["miou_fg"]
            save_atomic({"state_dict": model.state_dict(), "config": config, "epoch": ep + 1, "val": metrics},
                        WORK / "best.pt")
        save_atomic({"state_dict": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                     "scaler": scaler.state_dict(), "epoch": ep + 1, "best": best, "rng": torch.get_rng_state(),
                     "minutes": (time.time() - t0) / 60}, WORK / "last.pt")
        if (time.time() - t0) / 60 > a.max_minutes:
            print("time budget reached", flush=True)
            break
    import shutil

    for _ in range(10):            # publish the selected checkpoint for inference
        try:
            shutil.copyfile(WORK / "best.pt", OUT / "best.pt.new")
            Path(OUT / "best.pt.new").replace(OUT / "best.pt")
            break
        except OSError:
            time.sleep(5)
    print("best val miou_fg", round(best, 4), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
