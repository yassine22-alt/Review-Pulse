"""The meaning of a table header, from a YAML vocabulary of header words (any language), and the unit a header or a cell states.

Words are the default and need no model. A multilingual embedding match (bge-m3, served by the local Ollama) is added for a
header the words cannot place, but only when REVIEWPULSE_EMBED is set to "on" (or "1", "bge-m3") by the caller: unset means
words only, so nothing here needs a GPU.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..annotate.text_classify import normalise
from ..interpreter.units import UnitError, is_unit

_PATH = Path(__file__).with_name("vocabulary.yaml")


@lru_cache(maxsize=1)
def vocabulary() -> dict:
    return yaml.safe_load(_PATH.read_text(encoding="utf-8"))


def fold(text: str) -> str:
    """Lower case, no accents, ss for the German sharp s, punctuation as spaces (a '#' and an 'x' are kept)."""
    t = normalise(str(text)).replace("ß", "ss").replace("°", " ")
    t = re.sub(r"[^a-z0-9#]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> list[str]:
    return fold(text).split()


@dataclass(frozen=True)
class HeaderMatch:
    meaning: str | None
    score: float
    via: str = "words"            # words, embedding, content or none
    ambiguous: bool = False


@lru_cache(maxsize=1)
def _phrases() -> list[tuple[str, tuple[str, ...], bool]]:
    """(meaning, tokens, exact only). A word written '=floor' types a header only when the header is exactly that word."""
    out = []
    for meaning, spec in vocabulary()["meanings"].items():
        seen = set()
        for w in spec["words"]:
            w = str(w)
            exact = w.startswith("=")
            t = tuple(tokens(w.lstrip("=")))
            if t and (t, exact) not in seen:
                seen.add((t, exact))
                out.append((meaning, t, exact))
    return out


def dim_of(meaning: str | None) -> str:
    return vocabulary()["meanings"][meaning]["dim"] if meaning else "text"


def header_core(text: str) -> str:
    """The header without what is in brackets (the unit)."""
    return re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", " ", str(text))


def _score(P: tuple[str, ...], H: tuple[str, ...]) -> float:
    if P == H:
        return 1.0
    ps, hs = set(P), set(H)
    if ps <= hs and (len(P) >= 2 or len(P[0]) >= 3):
        if len(hs) - len(ps) >= 2:                      # two words the phrase does not explain: "Bottom of Glass" is not "Glass"
            return 0.5
        return 0.7 + 0.15 * len(P) / len(H)
    if hs <= ps and all(len(t) >= 3 for t in H):
        return 0.5                                       # part of a phrase ("Nominal" of "Nominal size") is not enough to type a column
    if len(H) == 1 and len(P) == 1 and len(P[0]) >= 8 and len(H[0]) >= 10 and P[0] in H[0]:
        return 0.65                                   # a German compound: Feuerwiderstandsklasse contains Feuerwiderstand
    return 0.0


def match_alternatives(header: str) -> list[HeaderMatch]:
    """Every meaning the header can have, best first (a header such as 'Plafond' is a height or a finish: the cells decide)."""
    H = tuple(tokens(header_core(header)))
    best: dict[str, float] = {}
    for meaning, P, exact in _phrases():
        s = (1.0 if P == H else 0.0) if exact else (_score(P, H) if H else 0.0)
        if s > best.get(meaning, 0.0):
            best[meaning] = s
    order = list(vocabulary()["meanings"])
    return [HeaderMatch(m, s, "words") for m, s in sorted(best.items(), key=lambda kv: (-kv[1], order.index(kv[0]))) if s > 0]


def match_words(header: str) -> HeaderMatch:
    H = tuple(tokens(header_core(header)))
    if not H:
        return HeaderMatch(None, 0.0, "none")
    best: dict[str, float] = {}
    for meaning, P, exact in _phrases():
        s = (1.0 if P == H else 0.0) if exact else _score(P, H)
        if s > best.get(meaning, 0.0):
            best[meaning] = s
    if not best:
        return HeaderMatch(None, 0.0, "none")
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    m1, s1 = ranked[0]
    top = [m for m, s in ranked if s >= s1 - 1e-9]
    ambiguous = len(top) > 1
    if ambiguous:                                      # the first one of the vocabulary wins; the doubt is recorded
        order = list(vocabulary()["meanings"])
        m1 = min(top, key=order.index)
    return HeaderMatch(m1, s1 * (0.8 if ambiguous else 1.0), "words", ambiguous)


def embedding_enabled() -> bool:
    return os.environ.get("REVIEWPULSE_EMBED", "").strip().lower() in {"on", "1", "true", "bge-m3"}


@lru_cache(maxsize=1)
def _embedder():
    from ..interpreter.drawing_evidence import OllamaEmbedder

    emb = OllamaEmbedder()
    return emb if emb.available() else None


def match_embedding(header: str, threshold: float = 0.62) -> HeaderMatch:
    """The meaning whose word list is nearest to the header by bge-m3. Only when the caller allows it and the model is served."""
    if not embedding_enabled():
        return HeaderMatch(None, 0.0, "none")
    try:
        emb = _embedder()
        if emb is None:
            return HeaderMatch(None, 0.0, "none")
        import math

        names = list(vocabulary()["meanings"])
        docs = [f"{n.replace('_', ' ')}: " + ", ".join(str(w).lstrip("=") for w in vocabulary()["meanings"][n]["words"][:8]) for n in names]
        vecs = emb([header_core(header), *docs])
        q, rest = vecs[0], vecs[1:]

        def cos(a, b):
            return sum(x * y for x, y in zip(a, b, strict=True)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)

        sims = [cos(q, v) for v in rest]
        i = max(range(len(sims)), key=sims.__getitem__)
        return HeaderMatch(names[i], sims[i], "embedding") if sims[i] >= threshold else HeaderMatch(None, 0.0, "none")
    except Exception:  # noqa: BLE001 - no server, no embeddings: words only
        return HeaderMatch(None, 0.0, "none")


def match_header(header: str) -> HeaderMatch:
    m = match_words(header)
    if m.meaning is None or m.score < 0.6:
        e = match_embedding(header)
        if e.meaning is not None:
            return e
    return m


def canonical_unit(text: str | None) -> str | None:
    """A unit written the way drawings write it ('mm', 'in.', 'sq ft', 'HR', '"') as a symbol of the unit table, or None."""
    if text is None:
        return None
    s = str(text).strip().strip(".,;:")
    if not s:
        return None
    aliases = vocabulary()["unit_aliases"]
    for cand in (s, s.lower(), s.lower() + "."):
        if cand in aliases:
            return str(aliases[cand])
    for cand in (s, s.lower()):
        if re.fullmatch(r"[^\W\d_]+\d?|%|°[CF]", cand) and is_unit(cand):
            return cand
    s2 = s.replace(" ", "")
    for cand in (s2, s2.lower()):
        if cand in aliases:
            return str(aliases[cand])
    try:
        return s if is_unit(s) and re.fullmatch(r"[A-Za-z0-9./^*%°²³-]+", s) else None
    except UnitError:
        return None


def header_unit(header: str) -> str | None:
    """The unit a header states: in brackets ('Width (mm)', 'Area [m2]'), after a comma or slash ('Width, mm'), or as its last word."""
    for inner in re.findall(r"[\(\[\{]([^\)\]\}]*)[\)\]\}]", str(header)):
        for part in re.split(r"[;/]|\s+or\s+", inner):
            u = canonical_unit(part)
            if u:
                return u
    h = str(header).strip()
    m = re.search(r"[,/]\s*([^,/\s]+)\s*$", h)
    if m:
        u = canonical_unit(m.group(1))
        if u:
            return u
    return None


def kind_words() -> dict[str, set[str]]:
    return {k: {fold(w) for w in v.get("title", [])} for k, v in vocabulary()["kinds"].items()}
