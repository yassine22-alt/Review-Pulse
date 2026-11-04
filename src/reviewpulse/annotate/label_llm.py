"""Fallback for room labels the lexicon does not know: ask the local LLM (Ollama, qwen2.5:7b).

Only label-like notes go to the model (short, has letters, not a dimension/tag/title field). The
answer is constrained to the vocabulary's room types plus ``not_a_room``; decoding is deterministic
(temperature 0, fixed seed) and every answer is cached on disk, so a plan reads the same way every
time. A type found this way is marked ``prov.evidence['label_source'] = 'llm'`` with confidence
0.6; the engine never lets a FAIL rest on such a room type (it asks to verify it instead).

Off with REVIEWPULSE_LABEL_LLM=0; silently skipped when Ollama is not running.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..schema import TextItem
from .text_classify import label_core, normalise

ROOM_TYPES = ["bedroom", "bathroom", "wc", "kitchen", "living", "corridor", "entry", "garage", "storage",
              "stairs", "terrace", "office", "other"]
LLM_CONFIDENCE = 0.6
BATCH = 40
CACHE = Path(__file__).resolve().parents[3] / "data" / "cache" / "label_llm.json"

SYSTEM = (
    "You read room labels from architectural floor plans of any country. A label may be a full word, "
    "an abbreviation (e.g. Finnish MH = makuuhuone = bedroom, German WZ = Wohnzimmer = living room), "
    "or several words. For each label give the room type it names:\n"
    "bedroom (sleeping room), bathroom (bath/shower/sauna/washroom), wc (toilet only), kitchen, "
    "living (living, dining, lounge, family room), corridor (hall, passage, landing), entry (entrance, "
    "vestibule, draught lobby), garage (garage, carport), storage (storage, closet, wardrobe, laundry, "
    "utility, technical room, cellar), stairs, terrace (balcony, terrace, porch, patio, garden), "
    "office (study, library), other (a named room of another kind), not_a_room (not a room name: "
    "a note, a material, a direction, a person, a sheet field). Answer for every label, in order.")

SCHEMA = {
    "type": "object",
    "properties": {"labels": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"},
                       "room_type": {"type": "string", "enum": ROOM_TYPES + ["not_a_room"]}},
        "required": ["text", "room_type"]}}},
    "required": ["labels"],
}


def is_candidate(t: TextItem) -> bool:
    if t.kind != "note":
        return False
    s = normalise(t.text)
    return (1 <= len(s) <= 30 and re.search(r"[^\W\d_]", s) is not None and len(s.split()) <= 4
            and not re.fullmatch(r"[\d\W]+", s))


def _load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def classify_labels(texts: list[str], client=None, cache_path: Path | None = None) -> dict[str, tuple[str | None, float]]:
    """text -> (room type or None, confidence). Cached per model and normalised label."""
    if client is None:
        from ..rules.draft import OllamaClient

        client = OllamaClient()
    model = getattr(client, "model", "llm")
    cache_path = cache_path or CACHE
    cache = _load_cache(cache_path)
    key = {t: f"{model}|{label_core(t) or normalise(t)}" for t in texts}
    todo = sorted({key[t].split("|", 1)[1] for t in texts if key[t] not in cache})
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        user = "Labels:\n" + "\n".join(f"{k + 1}. {s}" for k, s in enumerate(chunk))
        try:
            out = client.complete(SYSTEM, user, SCHEMA)
        except RuntimeError:
            break
        got = out.get("labels") or []
        for k, s in enumerate(chunk):
            # answers are matched by position; a reply that echoes another label is not trusted
            ans = got[k] if k < len(got) else None
            ok = ans and normalise(str(ans.get("text", ""))).strip(" .") in (s, s.strip(" ."))
            cache[f"{model}|{s}"] = ans["room_type"] if ok else None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    res = {}
    for t in texts:
        v = cache.get(key[t])
        res[t] = (v, LLM_CONFIDENCE) if v and v != "not_a_room" else (None, 0.0)
    return res


def enabled() -> bool:
    return os.environ.get("REVIEWPULSE_LABEL_LLM", "1") != "0"


def apply_llm_labels(items: list[TextItem], client=None, cache_path: Path | None = None) -> int:
    """Turn label-like notes the lexicon missed into room labels where the LLM names a room type."""
    cands = [t for t in items if is_candidate(t)]
    if not cands or not enabled():
        return 0
    if client is None:
        from ..rules.draft import OllamaClient

        client = OllamaClient()
        if not client.available():
            return 0
    got = classify_labels([t.text for t in cands], client, cache_path)
    n = 0
    for t in cands:
        rtype, conf = got.get(t.text, (None, 0.0))
        if rtype:
            t.kind, t.norm = "room_label", rtype
            t.prov.confidence = min(t.prov.confidence, conf)
            t.prov.evidence["label_source"] = "llm"
            n += 1
    if n:
        from .text_classify import attach_label_numbers

        attach_label_numbers(items)
    return n
