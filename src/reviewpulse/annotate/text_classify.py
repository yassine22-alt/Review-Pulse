"""R6 - Text classification.

Order: area, dimension, tag, room label, title-block field, otherwise note.
Room labels in any language listed in annotate/lexicon/ (curated + mined from data); decimal commas; OCR-like typos tolerated for labels.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..schema import TextItem


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("²", "2")
    return re.sub(r"\s+", " ", s.strip().lower())


AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(m2|m\^2|㎡)")
DIM_RE = re.compile(r"^\s*(\d{1,2}[.,]\d{1,3}|\d{3,5}|\d{1,3})\s*(mm|cm|m)?\s*$")
TAG_RE = re.compile(r"^([pfdwv])[ -]?(\d{1,3})$")

LEXICON_DIR = Path(__file__).with_name("lexicon")


@lru_cache(maxsize=1)
def room_lexicon() -> dict[str, str]:
    """Normalised label core -> room type, from lexicon/curated.yaml (by language) plus the
    data-mined lexicon/mined_*.yaml files. Curated entries win; a curated word listed under two
    room types is an error in the lexicon."""
    import yaml

    lex: dict[str, str] = {}
    cur = yaml.safe_load((LEXICON_DIR / "curated.yaml").read_text(encoding="utf-8"))["types"]
    for rtype, langs in cur.items():
        for words in langs.values():
            for w in words:
                k = label_core(str(w))
                if k in lex and lex[k] != rtype:
                    raise ValueError(f"room lexicon: {w!r} listed as {lex[k]} and {rtype}")
                lex[k] = rtype
    for f in sorted(LEXICON_DIR.glob("mined_*.yaml")):
        for rtype, words in (yaml.safe_load(f.read_text(encoding="utf-8")).get("types") or {}).items():
            for w in words:
                lex.setdefault(label_core(str(w)), rtype)
    return lex


TITLE_KEYWORDS = {
    "scale": r"\b(echelle|ech|scale)\b",
    "date": r"\bdate\b",
    "revision": r"\b(indice|revision|rev)\b",
    "project": r"\b(projet|project)\b",
    "author": r"\b(dessine|drawn|auteur|author)\b",
    "title": r"\b(titre|title|plan)\b",
}

# OCR confusions in the trailing index ("Chambre l" -> "Chambre 1")
_OCR_INDEX = str.maketrans({"l": "1", "i": "1", "o": "0", "s": "5"})


@dataclass
class Classified:
    kind: str
    value: float | None = None
    unit: str | None = None
    norm: str | None = None


def label_core(text: str) -> str:
    """The part of a label that names the room: normalised, without a second name, a stated area,
    or a trailing index."""
    t = normalise(text)
    t = re.split(r"\s*[/+&]\s*", t)[0]                             # "sejour/salon" -> "sejour"
    t = re.sub(r"\b([a-z])\.(?=[a-z])", r"\1", t)                  # "s.d.b" -> "sdb", "w.c." -> "wc."
    t = re.sub(r"[\s.]*\d+([.,]\d+)?\s*m2.*$", "", t).strip()     # drop a trailing stated area
    # drop a trailing index: digits, or a separated OCR look-alike letter ("chambre l" = "chambre 1")
    t = re.sub(r"(?:[\s\-_]*[0-9]{1,2}|[\s\-_]+[lios])$", "", t).strip()
    return t.strip(" .:-")


def match_room(text: str) -> str | None:
    """Return the normalised room type if the text is a room label."""
    t = label_core(text)
    if not t:
        return None
    lex = room_lexicon()
    if t in lex:
        return lex[t]
    # "<entry> <qualifier>" ("chambre parents"): the longest entry the label starts with
    head = t
    while " " in head:
        head = head.rsplit(" ", 1)[0]
        if head in lex and len(t) - len(head) <= 6:
            return lex[head]
    return None


FUZZY_MIN_LEN = 5


def _edits(a: str, b: str, cap: int) -> int:
    """Levenshtein distance, stopping early once it exceeds ``cap``."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def match_room_fuzzy(text: str) -> str | None:
    """Tolerant match for OCR-read labels ("OLOHUOME" -> olohuone): only for cores of at least
    FUZZY_MIN_LEN letters, at most 1 edit (2 from 9 letters), and only when every closest entry names
    the same room type. Short abbreviations are never guessed (UH is not MH)."""
    t = label_core(text)
    if len(t) < FUZZY_MIN_LEN:
        return None
    cap = 1 if len(t) < 9 else 2
    best, types = cap + 1, set()
    for w, rt in room_lexicon().items():
        if len(w) < FUZZY_MIN_LEN:
            continue
        d = _edits(t, w, cap)
        if d < best:
            best, types = d, {rt}
        elif d == best:
            types.add(rt)
    return next(iter(types)) if best <= cap and len(types) == 1 else None


def classify(text: str) -> Classified:
    t = normalise(text)
    if not t:
        return Classified("note")

    m = AREA_RE.search(t)
    if m and len(t) <= 24:
        return Classified("area", float(m.group(1).replace(",", ".")), "m2")

    m = DIM_RE.match(t)
    if m:
        num, unit = m.group(1), m.group(2)
        val = float(num.replace(",", "."))
        if unit:
            return Classified("dimension", val, unit)
        if re.match(r"^\d{1,2}[.,]\d{1,3}$", num):
            return Classified("dimension", val, "m")
        if len(num) >= 4:
            return Classified("dimension", val, "mm")
        if len(num) == 3:
            return Classified("dimension", val, None)   # ambiguous: R7 tests both readings
        # 1-2 digit integers are too ambiguous (indices, counts)
        return Classified("note")

    m = TAG_RE.match(t.replace(" ", "")) or TAG_RE.match(t)
    if m:
        return Classified("tag", norm=f"{m.group(1).upper()}{int(m.group(2))}")

    rtype = match_room(text)
    if rtype:
        area = AREA_RE.search(t)
        return Classified("room_label", float(area.group(1).replace(",", ".")) if area else None,
                          "m2" if area else None, rtype)

    for field, pat in TITLE_KEYWORDS.items():
        if re.search(pat, t):
            return Classified("title_block", norm=field)

    return Classified("note")


def tag_key(s: str) -> str:
    """'P-1', 'p1' and 'P 01' all become 'P1'."""
    t = normalise(s).replace(" ", "").replace("-", "").replace("_", "")
    m = re.match(r"^([a-z]+)0*(\d+)$", t)
    return f"{m.group(1).upper()}{int(m.group(2))}" if m else t.upper()


def classify_items(items: list[TextItem]) -> list[TextItem]:
    for it in items:
        c = classify(it.text)
        it.kind, it.value, it.unit, it.norm = c.kind, c.value, c.unit, c.norm
        if it.kind == "note" and it.prov.source == "ocr":
            rtype = match_room_fuzzy(it.text)
            if rtype:
                it.kind, it.norm = "room_label", rtype
                it.prov.evidence["label_match"] = "fuzzy"
    attach_label_numbers(items)
    return items


AREA_PLAUSIBLE_M2 = (1.0, 300.0)
STACK_GAP = 1.6             # centre-to-centre distance across the lines, in text heights


def _axes(rot: float) -> tuple[tuple[float, float], tuple[float, float]]:
    import math

    r = math.radians(rot)
    return (math.cos(r), math.sin(r)), (-math.sin(r), math.cos(r))


def attach_label_numbers(items: list[TextItem]) -> int:
    """A bare number stacked against a room label (next line, same orientation) is the room's stated
    area whose unit the drawing or the OCR dropped ("MH" over "14.1"), not a dimension. When its value
    cannot be a room area (a lost decimal point: "575") it is set aside as a note. Returns how many
    texts were re-read."""
    labels = [t for t in items if t.kind == "room_label"]
    if not labels:
        return 0
    n = 0
    for t in items:
        if t.kind not in ("dimension", "note") or not re.fullmatch(r"\s*\d+(?:[.,]\d+)?\s*", t.text or ""):
            continue
        cx, cy = (t.bbox[0] + t.bbox[2]) / 2, (t.bbox[1] + t.bbox[3]) / 2
        best = None
        for lab in labels:
            d_rot = abs(((t.rotation_deg - lab.rotation_deg) + 90) % 180 - 90)
            if d_rot > 10:
                continue
            h = lab.height or min(lab.bbox[2] - lab.bbox[0], lab.bbox[3] - lab.bbox[1])
            if not h:
                continue
            u, v = _axes(lab.rotation_deg)
            lx, ly = (lab.bbox[0] + lab.bbox[2]) / 2, (lab.bbox[1] + lab.bbox[3]) / 2
            along = abs((cx - lx) * u[0] + (cy - ly) * u[1])
            across = abs((cx - lx) * v[0] + (cy - ly) * v[1])
            half = abs((lab.bbox[2] - lab.bbox[0]) * u[0]) / 2 + abs((lab.bbox[3] - lab.bbox[1]) * u[1]) / 2
            if 0.4 * h <= across <= STACK_GAP * h and along <= half + h:
                if best is None or across < best[0]:
                    best = (across, lab)
        if best is None:
            continue
        val = float(t.text.strip().replace(",", "."))
        lab = best[1]
        if AREA_PLAUSIBLE_M2[0] <= val <= AREA_PLAUSIBLE_M2[1]:
            t.kind, t.value, t.unit, t.norm = "area", val, "m2", None
            if lab.value is None:
                lab.value, lab.unit = val, "m2"
        else:
            t.kind, t.value, t.unit = "note", None, None
        n += 1
    return n


def dimension_metres(value: float, unit: str | None) -> float | None:
    if unit == "m":
        return value
    if unit == "cm":
        return value / 100
    if unit == "mm":
        return value / 1000
    return None
