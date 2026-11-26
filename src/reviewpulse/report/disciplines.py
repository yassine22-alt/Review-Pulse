"""Tag clauses and sheets by discipline without language specific code, and name the code chapter of a clause.

Cue words in English, French, German and Spanish, and the sheet number prefixes of drawing conventions, are in
``disciplines.yaml``. A text scores one point per distinct cue it contains; the best score wins, a tie goes to the order of
``tie_order``, no cue gives the default. Nothing here knows a discipline by name.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

DATA = Path(__file__).with_name("disciplines.yaml")
SUFFIX = r"(?:s|es|ed|ing|er|en|e|n|x)?"


def fold(text: str) -> str:
    """Lower case without accents, so 'Küche', 'kuche' and 'KUCHE' are one word."""
    decomposed = unicodedata.normalize("NFKD", text.casefold().replace("ß", "ss"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _cues() -> dict[str, list[re.Pattern]]:
    out: dict[str, list[re.Pattern]] = {}
    for did, spec in config()["disciplines"].items():
        pats = []
        for words in (spec.get("cues") or {}).values():
            for w in words:
                w = fold(str(w))
                prefix = w.endswith("*")
                body = re.escape(w.rstrip("*")).replace(r"\ ", r"\s+")
                pats.append(re.compile(rf"(?<![a-z0-9]){body}" + (r"[a-z]*" if prefix else SUFFIX) + r"(?![a-z0-9])"))
        out[did] = pats
    return out


def label(discipline: str) -> str:
    spec = config()["disciplines"].get(discipline)
    return spec["label"] if spec else discipline


def order() -> list[str]:
    return list(config()["disciplines"])


def scores(text: str) -> dict[str, int]:
    t = fold(text or "")
    return {did: sum(1 for p in pats if p.search(t)) for did, pats in _cues().items()}


def discipline_of(text: str) -> str:
    """Discipline id of a clause or a title, from cue words in any of the four languages."""
    s = scores(text)
    best = max(s.values(), default=0)
    if best == 0:
        return config()["default"]
    tied = [d for d, v in s.items() if v == best]
    tie_order = config()["tie_order"]
    return min(tied, key=lambda d: tie_order.index(d) if d in tie_order else len(tie_order))


_SHEET_NO = re.compile(r"^\s*([A-Za-z]{1,3})\s*[-_.]?\s*\d")


def sheet_discipline(sheet_id: str = "", title: str = "", sheet_type: str = "") -> str:
    """Discipline of a sheet: its number prefix (A-101, S2.1, FP-1), else cue words in its title, else its kind."""
    m = _SHEET_NO.match(sheet_id or "")
    if m:
        prefix = m.group(1).upper()
        for did, spec in config()["disciplines"].items():
            if prefix in [str(x).upper() for x in spec.get("sheet_prefixes", [])] and did != config()["default"]:
                return did
    if title and any(v for v in scores(title).values()):
        return discipline_of(title)
    return config().get("sheet_types", {}).get(sheet_type, config()["default"])


_CHAPTER = re.compile(r"^\s*((?:[^\W\d_]{1,6}[.\s-]*)?\d+)")


def chapter_of(clause_id: str, scope: str = "") -> tuple[str, str]:
    """(chapter key, label) of the code chapter a clause belongs to. The heading the requirement document puts above the
    clause is used when there is one; otherwise the clause number up to its first dot ('R311.6' -> 'R311', 'Art. 6.1' -> 'Art. 6')."""
    m = _CHAPTER.match(clause_id or "")
    key = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".-") if m else (clause_id or "").split(".")[0].strip()
    scope = " ".join((scope or "").split())
    if scope:
        return scope, scope
    return key or "Other", f"Section {key}" if key else "Other"
