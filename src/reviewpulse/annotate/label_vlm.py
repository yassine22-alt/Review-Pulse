"""Second reader for scanned text: a local vision-language model re-reads OCR words the classifier
could not use (decision A27 extended to images).

Only text is asked of the model, never geometry: benchmarks find these models read printed text well
and locate lines badly (docs/related_work.md). A word that OCR read but the lexicon could not type
(a misread room label) is cropped from the page and transcribed again; the transcription goes through
the same classifier as any text, but only when it agrees with what OCR read (the second reader
corrects, it never invents: on a blank crop the model answers "Living Room"). The word keeps ``prov.evidence['vlm_text']`` and ``label_source``
``vlm`` so a FAIL never rests on it alone, like LLM-typed labels.

Default model: qwen2.5vl:7b served by Ollama (Apache-2.0, local, temperature 0, fixed seed), with a
disk cache keyed by the crop. Off by default (no measured gain, see enabled()); on with REVIEWPULSE_LABEL_VLM=1.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path

import numpy as np

MODEL = "qwen2.5vl:7b"
PAD_PX = 6
CACHE = Path(os.environ.get("REVIEWPULSE_CACHE", Path.home() / ".cache" / "reviewpulse")) / "label_vlm"
PROMPT = ("Transcribe the text in this image exactly as written (it is a label on a floor plan). "
          "Answer with the text only, nothing else.")


def enabled() -> bool:
    """Off by default. Measured on 20 CubiCasa test scans (181 spaces, 27 Oct 2026): labels read
    correctly 50.8% without and with it. Of 120 words re-read, 81 answers were inventions (blocked by
    the agreement gate), 2 became correct labels, and correct readings were sometimes corrupted
    (HUONE -> HOME). Re-measure with scripts/eval_ocr_labels.py --vlm before enabling."""
    return os.environ.get("REVIEWPULSE_LABEL_VLM", "0") == "1"


MIN_SIDE_PX = 64          # vision encoders reject or misread very small images: OCR boxes can be 8 px tall


def _png(crop: np.ndarray) -> bytes:
    from PIL import Image

    im = Image.fromarray(crop)
    k = MIN_SIDE_PX / max(min(im.size), 1)
    if k > 1:
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def transcribe(crop: np.ndarray, host: str | None = None, model: str = MODEL, timeout_s: float = 900.0) -> str:
    import urllib.request

    png = _png(crop)
    key = hashlib.sha256(png + model.encode()).hexdigest()[:24]
    f = CACHE / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))["text"]
    host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    body = {"model": model, "prompt": PROMPT, "images": [base64.b64encode(png).decode()], "stream": False,
            # a label is a few words; on blank or unreadable crops the model otherwise loops until the
            # server aborts ("token repeat limit reached")
            "options": {"temperature": 0, "seed": 42, "num_predict": 24, "repeat_penalty": 1.15}}
    req = urllib.request.Request(host + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        text = json.loads(r.read())["response"].strip().strip('"').strip()
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    return text


AGREE_MIN = 0.6          # similarity of the second reading to the OCR reading


def _letters(s: str) -> str:
    from .text_classify import normalise

    return re.sub(r"[^a-z]", "", normalise(s))


def agrees(ocr: str, vlm: str) -> bool:
    """The second reading may correct the OCR reading, never replace it: measured, the model invents
    "10'x20' Living Room" for a blank crop. Similar letters, similar length."""
    from difflib import SequenceMatcher

    a, b = _letters(ocr), _letters(vlm)
    if not a or not b or not (0.5 <= len(b) / len(a) <= 2.0):
        return False
    return SequenceMatcher(None, a, b).ratio() >= AGREE_MIN


def candidates(items) -> list:
    """Words worth a second reading: not typed as label, area or dimension, with at least two letters."""
    return [t for t in items if t.kind not in ("room_label", "area", "dimension", "title_block")
            and len(re.findall(r"[^\W\d_]", t.text)) >= 2]


def reread_labels(items, image: np.ndarray, to_pixels) -> int:
    """Re-read candidate words from ``image`` (grey page); ``to_pixels(bbox)`` maps a text bbox to
    (x0, y0, x1, y1) in image pixels. Returns how many words became room labels."""
    from .text_classify import classify

    h, w = image.shape[:2]
    gained = 0
    for t in candidates(items):
        x0, y0, x1, y1 = to_pixels(t.bbox)
        x0, x1 = sorted((int(x0) - PAD_PX, int(x1) + PAD_PX))
        y0, y1 = sorted((int(y0) - PAD_PX, int(y1) + PAD_PX))
        crop = image[max(y0, 0):min(y1, h), max(x0, 0):min(x1, w)]
        if crop.size == 0:
            continue
        try:
            text = transcribe(crop)
        except OSError as e:          # server down, model missing, refused image: keep the OCR reading
            t.prov.evidence["vlm_error"] = repr(e)[:120]
            continue
        if not agrees(t.text, text):
            t.prov.evidence["vlm_rejected"] = text[:60]
            continue
        c = classify(text)
        if c.kind == "room_label":
            t.kind, t.value, t.unit, t.norm = c.kind, c.value, c.unit, c.norm
            t.prov.evidence.update(vlm_text=text, label_source="vlm")
            gained += 1
    return gained
