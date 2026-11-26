"""What the drawings say about a requirement: find the note, check it is about the same thing, compare its figure.

Most lines of a real checklist ask about things a plan view does not draw to measure. The answer is usually written somewhere in
the drawing set, in any wording and sometimes in another language than the requirement. For a clause no measured rule could be
written for, this module answers three questions, each with the method that is reliable for it:

  1. Which notes could be about it?   Retrieval over every passage of every sheet. Two rankings are fused: words in common
     (BM25, exact on figures and terms of art) and meaning (a multilingual embedding model, which finds "porte coupe-feu" for
     "fire door"). Fusing the two by rank is the standard that regulatory retrieval work reports as better than either alone.
     The embedding model is optional: without it only the word ranking is used, and a requirement in another language than the
     drawings finds less.
  2. Is one of them really about it?   A small model is unreliable when it writes and reliable when it chooses (measured in this
     project: docs/progress/M11). It is shown the best passages and asked to choose the one about the same thing, or none, once
     per rotation of the options (every option in every position); only a majority is believed. The cross-encoder's own score is
     not used to decide: on the permit set correct notes scored from -2.7 to +2.2 and wrong ones up to +4.2.
  3. Does its figure meet the requirement?   No model: the figures of the sentence and of the note are parsed with the unit table
     and compared ("at least 20 min" against "60 minutes" agrees; against "15 min" contradicts). When the note holds several
     figures of the same kind, the model chooses which one, again in both orders.

The result is evidence for a person, with the sheet and the words quoted. It never decides a clause: a note can be wrong, apply to
another element, or be overridden elsewhere. What it does is put the right words next to the right requirement, and say when the
drawings state a figure the requirement does not allow.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field

from ..annotate.passages import Passage
from .grounding import NONE

TOP_K = 5                    # passages shown to the model when nothing has reordered them
SHOWN_AFTER_RERANK = 3       # ... and when the cross-encoder has: its first three are shown, each in every position
RRF_K = 60                   # the usual constant of reciprocal rank fusion
SYSTEM = """A requirement from a regulation or a plan-review checklist is given, with notes copied from a set of construction
drawings. The requirement and the notes can be in different languages.

Choose the note that says how the drawings deal with what the requirement asks about: the same element and the same property.
A note about another element, or about another property of the same element, is not it. A note that only shares a word with the
requirement is not it. If no note is about it, answer "none".
Reply with JSON only: {"choice": "<id or none>"}."""
FIGURE_SYSTEM = """A requirement limits one quantity (its limit is given). A note from the drawings states figures, each with the
words written around it. Choose the figure that is the same property of the same kind of element as the limit: a fire rating
of 60 minutes is the property a limit of 20 minutes is about, even when the note gives more detail than the requirement; a
thickness is not a width, and a height is not a spacing. Choose "none" only if no figure is that property.
Reply with JSON only: {"choice": "<id or none>"}."""


# ---- 1. retrieval -------------------------------------------------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    """Words for the word ranking: lower case, accents folded, a final plural s dropped; figures are kept as they are written."""
    flat = unicodedata.normalize("NFKD", text.lower())
    flat = "".join(ch for ch in flat if not unicodedata.combining(ch))
    out = []
    for w in re.findall(r"[^\W_]+", flat):
        if len(w) >= 3 or w.isdigit():
            out.append(w[:-1] if len(w) > 3 and w.endswith("s") and not w.isdigit() else w)
    return out


def bm25_ranking(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> list[int]:
    """Indices of the documents that share a word with the query, best first (Okapi BM25)."""
    toks = [_tokens(d) for d in docs]
    n = len(docs)
    if not n:
        return []
    avg = sum(len(t) for t in toks) / n or 1.0
    df = Counter(w for t in toks for w in set(t))
    scores = []
    for t in toks:
        tf = Counter(t)
        s = 0.0
        for w in set(_tokens(query)):
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg))
        scores.append(s)
    return [i for i in sorted(range(n), key=lambda i: -scores[i]) if scores[i] > 0]


class OllamaEmbedder:
    """A multilingual embedding model served by the same Ollama that serves the reading model (default bge-m3)."""

    def __init__(self, model: str | None = None, host: str | None = None, timeout_s: float = 600.0):
        self.model = model or os.environ.get("REVIEWPULSE_EMBED_MODEL") or "bge-m3"
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self.timeout_s = timeout_s
        self.num_gpu = int(os.environ.get("REVIEWPULSE_EMBED_GPU_LAYERS", "0"))
        self._cache: dict[str, list[float]] = {}

    def _call(self, path: str, body: dict | None = None) -> dict:
        import urllib.request

        req = urllib.request.Request(self.host + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:  # noqa: S310 - the local model server
            return json.loads(r.read().decode())

    def available(self) -> bool:
        try:
            names = [m.get("name", "") for m in self._call("/api/tags").get("models", [])]
        except Exception:  # noqa: BLE001 - no server, no embeddings
            return False
        return any(n == self.model or n.split(":")[0] == self.model for n in names)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        for k in range(0, len(missing), 32):
            batch = missing[k:k + 32]
            # on the processor by default: on a small graphics card the embedding model would push the reading model out of
            # memory at every clause, and one sentence is embedded in well under a second without it
            got = self._call("/api/embed", {"model": self.model, "input": batch, "keep_alive": "30m",
                                            "options": {"num_gpu": self.num_gpu}})["embeddings"]
            self._cache.update(zip(batch, got))
        return [self._cache[t] for t in texts]


def default_embedder():
    """The embedding model when it is installed, else None (retrieval then ranks by words only)."""
    if os.environ.get("REVIEWPULSE_EMBED", "on") == "off":
        return None
    emb = OllamaEmbedder()
    return emb if emb.available() else None


def dense_ranking(query: str, docs: list[str], embedder) -> list[int]:
    vectors = embedder([query, *docs])
    q, rest = vectors[0], vectors[1:]

    def cos(a, b):
        den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
        return sum(x * y for x, y in zip(a, b)) / den if den else 0.0

    sims = [cos(q, v) for v in rest]
    return sorted(range(len(docs)), key=lambda i: -sims[i])


def fuse(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    """Reciprocal rank fusion: a document high in several rankings comes first; no score of one ranking is compared with another's."""
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking):
            score[i] = score.get(i, 0.0) + 1.0 / (k + rank + 1)
    return sorted(score, key=lambda i: -score[i])


class CrossEncoder:
    """A multilingual cross-encoder (bge-reranker-v2-m3, quantised ONNX, run with onnxruntime on the processor). Unlike the two
    rankings above, which compare the requirement and a passage after reading each alone, it reads them TOGETHER, so it can tell
    "a door rating of 60 minutes" is the answer to "the garage door must be a 20 minute door" and "doors 1 3/4 in thick" is not.
    That is why it is the standard second stage of retrieval, applied to the few dozen candidates the first stage keeps."""

    def __init__(self, folder: str | os.PathLike | None = None, max_length: int = 384):
        from pathlib import Path

        import onnxruntime as ort
        from tokenizers import Tokenizer

        folder = Path(folder or os.environ.get("REVIEWPULSE_RERANKER") or reranker_folder() or "")
        self.tok = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tok.enable_truncation(max_length=max_length)
        self.tok.enable_padding()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) // 2)
        self.session = ort.InferenceSession(str(folder / "model_quantized.onnx"), opts, providers=["CPUExecutionProvider"])
        self.names = {i.name for i in self.session.get_inputs()}

    def scores(self, query: str, docs: list[str], batch: int = 8) -> list[float]:
        import numpy as np

        out: list[float] = []
        for k in range(0, len(docs), batch):
            enc = self.tok.encode_batch([(query, d) for d in docs[k:k + batch]])
            feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                    "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
            logits = self.session.run(None, {n: v for n, v in feed.items() if n in self.names})[0]
            out += [float(x) for x in np.asarray(logits).reshape(len(enc), -1)[:, 0]]
        return out


def reranker_folder() -> str | None:
    from pathlib import Path

    places = [Path("data/models/reranker"), Path(__file__).resolve().parents[3] / "data" / "models" / "reranker"]
    return next((str(p) for p in places if (p / "model_quantized.onnx").is_file() and (p / "tokenizer.json").is_file()), None)


def fetch_reranker(dest: str | os.PathLike | None = None) -> str:
    """Download the cross-encoder (570 MB, Apache 2.0, BAAI bge-reranker-v2-m3 converted to ONNX). Run once."""
    import urllib.request
    from pathlib import Path

    dest = Path(dest or "data/models/reranker")
    dest.mkdir(parents=True, exist_ok=True)
    base = "https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX/resolve/main/"
    urllib.request.urlretrieve(base + "onnx/model_quantized.onnx", dest / "model_quantized.onnx")  # noqa: S310 - fixed https address
    urllib.request.urlretrieve(base + "tokenizer.json", dest / "tokenizer.json")  # noqa: S310
    return str(dest)


def default_reranker():
    """The cross-encoder when its files and the tokenizer library are installed, else None (retrieval then stops at the fusion)."""
    if os.environ.get("REVIEWPULSE_RERANK", "on") == "off" or reranker_folder() is None and not os.environ.get("REVIEWPULSE_RERANKER"):
        return None
    try:
        return CrossEncoder()
    except Exception:  # noqa: BLE001 - a missing library or a damaged file: no reranker
        return None


def rerank(clause: str, docs: list[str], pool: list[int], reranker) -> list[int]:
    """The indices of `pool` ordered by the cross-encoder, best first."""
    if not pool:
        return []
    got = reranker.scores(clause, [docs[i] for i in pool])
    return [i for _, i in sorted(zip(got, pool), key=lambda t: -t[0])]


FIRST_STAGE = 20             # candidates the two rankings hand to the cross-encoder


def retrieve(clause: str, passages: list[Passage], embedder=None, top: int = TOP_K, reranker=None) -> list[Passage]:
    docs = [p.text for p in passages]
    rankings = [bm25_ranking(clause, docs)]
    if embedder is not None and docs:
        try:
            # the meaning ranking is cut to its head: far down it only orders passages that have nothing to do with the clause
            rankings.append(dense_ranking(clause, docs, embedder)[:max(top * 4, FIRST_STAGE)])
        except Exception:  # noqa: BLE001 - the word ranking stands on its own
            pass
    order = fuse(rankings)
    if reranker is not None and order:
        try:
            pool = order[:FIRST_STAGE]
            order = rerank(clause, docs, pool, reranker) + order[FIRST_STAGE:]
        except Exception:  # noqa: BLE001 - the fusion stands on its own
            pass
    return [passages[i] for i in order[:top]]


# ---- 2. is one of them about the same thing? -------------------------------------------------------------------------------------

def _choose(client, system: str, payload: dict, ids: list[str]) -> str | None:
    schema = {"type": "object", "properties": {"choice": {"type": "string", "enum": [*ids, NONE]}}, "required": ["choice"]}
    try:
        out = client.complete(system, json.dumps(payload, ensure_ascii=False), schema)
    except Exception:  # noqa: BLE001 - no answer is no evidence
        return None
    got = out.get("choice") if isinstance(out, dict) else None
    return got if got in ids or got == NONE else None


def _stable(client, system: str, key: str, text: str, options: dict[str, str]) -> str | None:
    """The option a majority of position-balanced questions choose, or None. A small model favours the first option shown and
    sometimes the last. The question is therefore put once per rotation of the options, so that every option is shown in every
    position exactly once, and an option is believed only when it wins more than half of the questions. "Same in two orders", the
    rule used before, rejected a correct note whenever the model happened to lean the wrong way in one of the two. Voting over
    rotations is the usual fix for position bias in model judgements (permutation self-consistency)."""
    ids = list(options)
    votes: dict[str, int] = {}
    for k in range(len(ids)):
        rotated = {i: options[i] for i in ids[k:] + ids[:k]}
        got = _choose(client, system, {key: text[:800], "options": rotated}, ids)
        if got is not None:
            votes[got] = votes.get(got, 0) + 1
    best = max((i for i in votes if i != NONE), key=lambda i: votes[i], default=None)
    return best if best is not None and votes[best] > len(ids) / 2 and votes[best] > votes.get(NONE, 0) else None


# ---- 3. the figures --------------------------------------------------------------------------------------------------------------

@dataclass
class Check:
    required: str                 # ">= 20 min"
    stated: str | None            # "60 min", "34 to 36 in", or None when the note states no figure of that kind
    result: str                   # agrees | contradicts | no figure | unclear
    basis: str = ""               # "the model chose it among several" | "the only figure of that kind in the note"
    words: str = ""               # the words written around the figure, so a person can see what it is the figure of


def required_limits(clause: str) -> list[tuple[str, float, str]]:
    """The limits a sentence states as (comparison, value, unit): "at least 20 min" -> (">=", 20, "min"); a range gives two."""
    from ..xeval.demand import quantities
    from ..xeval.limits_arm import read_limits
    from ..xeval.slot_arm import OPS
    from ..xeval.verify import prepare
    from .quantities import normalise_quantities

    text = normalise_quantities(clause)
    out = []
    reading = read_limits(text)
    if reading is not None:
        for lim in reading.limits:
            parts = lim.literal.split(None, 1)
            if not lim.count and len(parts) == 2:
                out.append((OPS[lim.op], float(parts[0]), parts[1]))
        return out
    qs = [q for q in quantities(prepare(text)) if q.unit != "ratio"]
    if len(qs) == 2 and qs[0].span == qs[1].span and qs[0].value < qs[1].value:          # "34 to 38 in": a range
        return [(">=", qs[0].value, qs[0].unit), ("<=", qs[1].value, qs[1].unit)]
    return out


def stated_figures(note: str) -> list[tuple[float, float, str, tuple[int, int], str]]:
    """The figures a note states as (low, high, unit, span, the words around it); low == high unless the note gives a range."""
    from ..xeval.demand import quantities
    from ..xeval.verify import prepare
    from .quantities import normalise_quantities

    text = prepare(normalise_quantities(note.lower()))
    by_span: dict[tuple[int, int], list] = {}
    for q in quantities(text):
        if q.unit != "ratio":
            by_span.setdefault(q.span, []).append(q)
    out = []
    spans = sorted(by_span)
    for k, span in enumerate(spans):
        values = sorted(q.value for q in by_span[span])
        # the words that belong to this figure: from the figure before it (or the start of its sentence) to just after it, never
        # reaching into the next figure. With both figures in every option a model cannot tell the options apart
        start = max(spans[k - 1][1] if k else 0, span[0] - 70)
        end = min(spans[k + 1][0] if k + 1 < len(spans) else len(text), span[1] + 18)
        stop = text.find(". ", span[1] - 1, end)                      # the words after the figure, up to the end of its sentence
        out.append((values[0], values[-1], by_span[span][0].unit, span, text[start:end if stop < 0 else stop].strip(" ,;.")))
    return out


def _holds(op: str, low: float, high: float, limit: float) -> bool:
    tol = 0.005 * max(abs(limit), 1e-9)
    return {">=": low >= limit - tol, ">": low > limit, "<=": high <= limit + tol, "<": high < limit}[op]


def compare(clause: str, note: str, client=None) -> list[Check]:
    from . import units

    figures = stated_figures(note)
    checks = []
    for op, value, unit in required_limits(clause):
        required = f"{op} {value:g} {unit}"
        same_kind = [f for f in figures if units.compatible(f[2], unit)]
        if not same_kind:
            checks.append(Check(required, None, "no figure"))
            continue
        # Among several figures of the right kind the model chooses (multiple choice, both orders). A lone figure is taken as it is: a
        # yes/no question about it is answered "no" by a small model whatever it is shown (measured, see the progress note), and
        # the note was already chosen as being about the requirement. The check says so, and shows the words around the figure,
        # because a lone length can still be another property (a thickness for a width).
        basis = "the only figure of that kind in the note"
        chosen = same_kind[0] if len(same_kind) == 1 else None
        if chosen is None and client is not None:
            basis = "chosen by the model among several"
            options = {f"f{i}": f"{f[0]:g}{'' if f[0] == f[1] else f' to {f[1]:g}'} {f[2]}, written as: \"{f[4]}\""
                       for i, f in enumerate(same_kind)}
            got = _stable(client, FIGURE_SYSTEM, "requirement", f"{clause} (the limit to match: {op} {value:g} {unit})", options)
            chosen = same_kind[int(got[1:])] if got else None
        if chosen is None:
            checks.append(Check(required, None, "unclear"))
            continue
        low, high = (units.convert(v, chosen[2], unit) for v in chosen[:2])
        said = f"{chosen[0]:g}{'' if chosen[0] == chosen[1] else f' to {chosen[1]:g}'} {chosen[2]}"
        checks.append(Check(required, said, "agrees" if _holds(op, low, high, value) else "contradicts", basis, chosen[4]))
    return checks


# ---- together --------------------------------------------------------------------------------------------------------------------

@dataclass
class Evidence:
    candidates: list[dict] = field(default_factory=list)        # the passages retrieved, best first: {sheet, text}
    chosen: dict | None = None                                  # the passage the model chose in both orders, or None
    checks: list[dict] = field(default_factory=list)            # the figures compared, when the clause states a limit
    summary: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def find_evidence(clause: str, passages: list[Passage], client, embedder=None, reranker=None) -> Evidence:
    """Evidence in the drawings for one clause. `passages`: annotate.passages.set_passages over the whole submission."""
    if not passages:
        return Evidence(summary="the drawings carry no written notes that could be read")
    found = retrieve(clause, passages, embedder, top=SHOWN_AFTER_RERANK if reranker is not None else TOP_K, reranker=reranker)
    ev = Evidence(candidates=[{"sheet": p.sheet, "text": p.text} for p in found])
    if not found:
        ev.summary = "no note of the drawings shares a word or a meaning with this requirement"
        return ev
    options = {f"n{i}": p.text[:320] for i, p in enumerate(found)}
    got = _stable(client, SYSTEM, "requirement", clause, options)
    if got is None:
        ev.summary = "notes were found near this requirement, but none was chosen as being about it"
        return ev
    note = found[int(got[1:])]
    ev.chosen = {"sheet": note.sheet, "text": note.text}
    checks = compare(clause, note.text, client)
    ev.checks = [asdict(c) for c in checks]
    where = f"sheet {note.sheet}" if note.sheet else "the drawings"
    if any(c.result == "contradicts" for c in checks):
        bad = next(c for c in checks if c.result == "contradicts")
        ev.summary = f"{where} states {bad.stated}, and the requirement asks {bad.required}: '{note.text[:200]}'"
    elif checks and all(c.result == "agrees" for c in checks):
        ev.summary = (f"{where} states {', '.join(c.stated for c in checks)}, which meets {', '.join(c.required for c in checks)}: "
                      f"'{note.text[:200]}'")
    else:
        ev.summary = f"{where} says: '{note.text[:240]}'"
    return ev
