"""OCR for raster pages (R13 step 1, decision D9, spike S-D).

Backends, tried in order unless one is named: PaddleOCR (D9 default when installed) and EasyOCR
(PyTorch, reliable on Windows). The page is cut into overlapping tiles, each tile is read at its
native orientation and rotated by 90/180/270 degrees (plans carry vertical and upside-down text),
duplicates are merged, and boxes are mapped to sheet millimetres through the page affine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from ..core.ids import IdFactory
from ..schema import Prov, TextItem

TILE = 1536
OVERLAP = 128
MIN_SCORE = 0.5
# PaddleOCR models and page rotations; overridable per deployment (speed vs. recall, see M4 report)
DET_MODEL = os.environ.get("REVIEWPULSE_OCR_DET", "PP-OCRv6_medium_det")
REC_MODEL = os.environ.get("REVIEWPULSE_OCR_REC", "PP-OCRv6_medium_rec")
ROTATIONS = tuple(int(r) for r in os.environ.get("REVIEWPULSE_OCR_ROTATIONS", "0,90,270,180").split(","))


@dataclass
class Word:
    text: str
    score: float
    box: np.ndarray        # (4, 2) pixel corners, y down
    angle: float           # reading direction in degrees, y up (0 = left to right)
    upright: bool = True   # the box was wider than tall in the pass that read it


@lru_cache(maxsize=2)
def _easyocr(langs: tuple[str, ...] = ("fr", "en"), gpu: bool = True):
    import easyocr

    return easyocr.Reader(list(langs), gpu=gpu, verbose=False)


def ocr_device() -> str:
    """'gpu:0' when PaddlePaddle was built with CUDA and sees a GPU, else 'cpu'.
    REVIEWPULSE_OCR_DEVICE overrides (e.g. 'cpu' to keep the GPU for the segmentation model)."""
    forced = os.environ.get("REVIEWPULSE_OCR_DEVICE")
    if forced:
        return forced
    try:
        import paddle

        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu:0"
    except Exception:  # noqa: BLE001 - optional dependency or a CPU-only build
        pass
    return "cpu"


@lru_cache(maxsize=2)
def _paddle(det: str = DET_MODEL, rec: str = REC_MODEL):
    try:  # on Windows, torch's DLLs fail to load after paddle's; load torch first when present
        import torch  # noqa: F401
    except Exception:  # noqa: BLE001 - optional dependency
        pass
    from paddleocr import PaddleOCR

    return PaddleOCR(text_detection_model_name=det, text_recognition_model_name=rec, device=ocr_device(),
                     use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=True)


def available_backends() -> list[str]:
    out = []
    for name, mod in (("paddle", "paddleocr"), ("easyocr", "easyocr")):
        try:
            __import__(mod)
            out.append(name)
        except Exception:  # noqa: BLE001 - optional dependency
            pass
    return out


def _read_tile(tile: np.ndarray, backend: str, det: str = DET_MODEL, rec: str = REC_MODEL) -> list[tuple[np.ndarray, str, float]]:
    if backend == "easyocr":
        import torch

        res = _easyocr(gpu=torch.cuda.is_available()).readtext(tile, paragraph=False)
        return [(np.array(b, float), t, float(s)) for b, t, s in res]
    res = _paddle(det, rec).predict(tile)
    out = []
    for r in res:
        for poly, t, s in zip(r["rec_polys"], r["rec_texts"], r["rec_scores"]):
            out.append((np.array(poly, float), t, float(s)))
    return out


def read_page(gray: np.ndarray, backend: str | None = None, rotations=None, det: str | None = None,
              rec: str | None = None) -> list[Word]:
    """Words of a grey page image (uint8), boxes in page pixels."""
    rotations = rotations or ROTATIONS
    det, rec = det or DET_MODEL, rec or REC_MODEL
    backend = backend or (available_backends() or [None])[0]
    if backend is None:
        raise RuntimeError("no OCR backend installed: pip install easyocr (or paddleocr + paddlepaddle==3.2.0)")
    H, W = gray.shape
    words: list[Word] = []
    step = TILE - OVERLAP
    for y0 in range(0, max(H - OVERLAP, 1), step):
        for x0 in range(0, max(W - OVERLAP, 1), step):
            tile = gray[y0:y0 + TILE, x0:x0 + TILE]
            if tile.size == 0 or tile.min() > 200:
                continue
            for rot in rotations:
                k = rot // 90
                t = np.ascontiguousarray(np.rot90(tile, k))
                th, tw = tile.shape
                for box, text, score in _read_tile(np.dstack([t] * 3), backend, det, rec):
                    text = text.strip()
                    if score < MIN_SCORE or not text:
                        continue
                    # engines also read tall boxes (they turn them internally): such a read says
                    # nothing about the reading direction of this pass
                    bw, bh = np.ptp(box[:, 0]), np.ptp(box[:, 1])
                    upright = bool(bw >= bh or len(text) <= 1)
                    # undo the rotation: rot90 by k maps (r, c) -> rotated; invert per k
                    pts = []
                    for x, y in box:
                        if k == 0:
                            px, py = x, y
                        elif k == 1:          # image rotated 90 deg counter-clockwise
                            px, py = tw - 1 - y, x
                        elif k == 2:
                            px, py = tw - 1 - x, th - 1 - y
                        else:
                            px, py = y, th - 1 - x
                        pts.append((px + x0, py + y0))
                    # text made readable by turning the image counter-clockwise by rot originally ran
                    # at -rot degrees (y up)
                    words.append(Word(text, score, np.array(pts), angle=float((-rot) % 360), upright=upright))
    return _dedupe(words)


def _dedupe(words: list[Word]) -> list[Word]:
    from shapely.geometry import Polygon

    # a read from the pass in which the text was upright wins over reads of the turned box
    words = sorted(words, key=lambda w: (not w.upright, -w.score))
    kept: list[tuple[Word, Polygon]] = []
    for w in words:
        poly = Polygon(w.box).buffer(0)
        if poly.is_empty:
            continue
        if any(poly.intersection(p).area > 0.5 * min(poly.area, p.area) for _, p in kept):
            continue
        kept.append((w, poly))
    return [w for w, _ in kept]


def to_text_items(words: list[Word], affine: list[float], sheet_id: str) -> list[TextItem]:
    a, b, c, d, e, f = affine
    ids = IdFactory(sheet_id + ":ocr")
    out = []
    for w in words:
        pts = [(a * x + b * y + c, d * x + e * y + f) for x, y in w.box]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        # text height: the short side of the box
        side = sorted([np.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]),
                       np.hypot(pts[2][0] - pts[1][0], pts[2][1] - pts[1][1])])
        out.append(TextItem(id=ids("text", w.text, bbox), text=w.text, bbox=bbox, rotation_deg=w.angle % 360,
                            height=float(side[0]), prov=Prov(source="ocr", stage="ocr", confidence=w.score)))
    return out
