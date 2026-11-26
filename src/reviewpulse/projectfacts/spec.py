"""Loads fields.yaml. No field, label word or value word is written in code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from ..drawingset.vocab import fold

SPEC_PATH = Path(__file__).with_name("fields.yaml")
LANGS = ("en", "fr", "de")


def tokens(text: str) -> tuple[str, ...]:
    """Folded words of a text (accents gone, apostrophes and dots as separators)."""
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("Ä", "Ae").replace("Ö", "Oe").replace("Ü", "Ue")
    return tuple(re.findall(r"[a-z0-9]+", fold(text).replace("'", " ")))


@dataclass
class Field:
    name: str
    kind: str                                   # number, bool, category
    unit: str
    description: str
    cues: list[tuple[str, tuple[str, ...]]]     # (language, folded words)
    patterns: list[re.Pattern] = field(default_factory=list)
    value_patterns: list[re.Pattern] = field(default_factory=list)
    values: dict[str, list[tuple[str, ...]]] = field(default_factory=dict)
    free: bool = False
    scan_into: list[str] = field(default_factory=list)
    by_level: bool = False
    storey_words: frozenset[str] = frozenset()
    true_phrases: list[tuple[str, ...]] = field(default_factory=list)
    false_phrases: list[tuple[str, ...]] = field(default_factory=list)

    @property
    def internal(self) -> bool:
        """A field read only to be scanned for others (the project title line): it is not itself asked about."""
        return bool(self.scan_into)


@dataclass
class Spec:
    fields: dict[str, Field]
    qualifiers: frozenset[str]
    unit_words: dict[tuple[str, ...], str]      # written form (tokens) -> unit symbol
    area_to_m2: dict[str, float]
    length_to_m: dict[str, float]
    true_words: list[tuple[str, ...]]
    false_words: list[tuple[str, ...]]
    unstated: list[tuple[str, ...]]
    number_words: dict[str, dict[str, int]]
    raw: dict = field(default_factory=dict)


def _toks(words) -> list[tuple[str, ...]]:
    out = [tokens(str(w)) for w in words]
    return [t for t in out if t]


@lru_cache(maxsize=1)
def load_spec(path: str | None = None) -> Spec:
    raw = yaml.safe_load(Path(path or SPEC_PATH).read_text(encoding="utf-8"))
    fields = {}
    for name, d in raw["fields"].items():
        cues = [(lang, t) for lang in LANGS for t in _toks(d.get("cues", {}).get(lang, []))]
        fields[name] = Field(
            name=name, kind=d["kind"], unit=str(d.get("unit", "1")), description=d.get("description", ""), cues=cues,
            patterns=[re.compile(p) for p in d.get("patterns", [])],
            value_patterns=[re.compile(p) for p in d.get("value_patterns", [])],
            values={k: _toks(v) for k, v in d.get("values", {}).items()},
            free=bool(d.get("free", False)), scan_into=list(d.get("scan_into", [])), by_level=bool(d.get("by_level", False)),
            storey_words=frozenset(w for t in _toks(d.get("storey_words", [])) for w in t),
            true_phrases=_toks(d.get("true_phrases", [])), false_phrases=_toks(d.get("false_phrases", [])))
    units = {}
    for sym, words in raw["units"].items():
        for w in words:
            t = tokens(str(w))
            if t:
                units[t] = sym
    return Spec(fields=fields, qualifiers=frozenset(w for t in _toks(raw["qualifiers"]) for w in t), unit_words=units,
                area_to_m2=raw["area_factor_to_m2"], length_to_m=raw["length_factor_to_m"],
                true_words=_toks(raw["bool_words"]["positive"]), false_words=_toks(raw["bool_words"]["negative"]),
                unstated=_toks(raw["unstated_words"]) + [("n", "a")],
                number_words={lang: {tokens(k)[0]: int(v) for k, v in d.items()} for lang, d in raw["number_words"].items()},
                raw=raw)


def find_run(hay: tuple[str, ...], needle: tuple[str, ...]) -> int:
    """Index of the first place `needle` occurs as consecutive words in `hay`, or -1."""
    n = len(needle)
    for i in range(len(hay) - n + 1):
        if hay[i:i + n] == needle:
            return i
    return -1
