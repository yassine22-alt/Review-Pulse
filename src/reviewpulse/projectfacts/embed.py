"""The optional second arm: a label the words do not know is placed by meaning (bge-m3 through Ollama).

Gated by REVIEWPULSE_EMBED (on, 1, true or bge-m3); unset means words only, so nothing here runs without being asked. The
embedder is a parameter (a function from a list of texts to a list of vectors) so tests use a small stand-in and a run on
a machine with the model served uses `OllamaEmbedder`. Only short, letters-only label candidates are embedded."""

from __future__ import annotations

import math
import os
import re

from ..drawingset.vocab import Vocab
from .read import Labeler, LabelHit, make_word_labeler
from .spec import Spec

THRESHOLD = 0.70
MARGIN = 0.03


def embedding_enabled() -> bool:
    return os.environ.get("REVIEWPULSE_EMBED", "").strip().lower() in {"on", "1", "true", "bge-m3"}


def default_embedder():
    """The served bge-m3 embedder, or None when the arm is off or the model is not served."""
    if not embedding_enabled():
        return None
    try:
        from ..interpreter.drawing_evidence import OllamaEmbedder

        emb = OllamaEmbedder()
        return emb if emb.available() else None
    except Exception:  # noqa: BLE001 - no server: words only
        return None


def _cos(a, b) -> float:
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / den if den else 0.0


def field_documents(spec: Spec) -> dict[str, str]:
    """What each field is, in words: its description and its cue words in every language."""
    out = {}
    for f in spec.fields.values():
        cues = [" ".join(c) for _, c in f.cues][:14]
        out[f.name] = f"{f.name.replace('_', ' ')}: {f.description}. " + ", ".join(cues)
    return out


def make_embedding_labeler(spec: Spec, vocab: Vocab, embedder, threshold: float = THRESHOLD) -> Labeler:
    """Words first; a label they do not know is compared with every field's document."""
    words = make_word_labeler(spec, vocab)
    docs = field_documents(spec)
    names = list(docs)
    dvec = embedder(list(docs.values()))
    cache: dict[str, LabelHit | None] = {}

    def label(text: str) -> LabelHit | None:
        hit = words(text)
        if hit is not None:
            return hit
        t = text.strip().rstrip(":=").strip()
        if not re.fullmatch(r"[^\W\d_][^\W\d_ .'/&-]*(?: [^\W\d_][^\W\d_.'/&-]*){0,4}", t):
            return None
        if t in cache:
            return cache[t]
        q = embedder([t])[0]
        sims = sorted(((_cos(q, v), n) for n, v in zip(names, dvec, strict=True)), reverse=True)
        best = sims[0]
        ok = best[0] >= threshold and best[0] - sims[1][0] >= MARGIN
        cache[t] = LabelHit(best[1], "en", None, None, "embedding", round(0.85 * best[0], 3)) if ok else None
        return cache[t]

    return label
