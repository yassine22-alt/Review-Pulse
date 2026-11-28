"""What the sheet says in words: notes, legend entries and callouts about things a plan view does not draw to measure.

Plan review checklists ask whether "smoke alarms are shown", "the fire rating is noted", "the handrail is called out". On a vector
sheet these are words in the text layer (a legend entry, a general note, a callout beside a symbol). They are counted here, never
measured: the fact is that the sheet MENTIONS the item, which is the part a reviewer ticks on a checklist. It does not say that
the item is in the right place or of the right kind.

The kinds of note are data (lexicon/notes.yaml), not code: a new kind, in any language or discipline, is one entry there.
Counting is a deterministic pattern match over the sheet text read in reading order, so the same sheet
always gives the same counts and nothing here calls a model. A sheet whose text was not read (outlined text, no OCR) has no counts:
absence of words there says nothing.
"""

from __future__ import annotations

import re
from pathlib import Path


def load_kinds(path: Path | None = None) -> dict[str, tuple[re.Pattern, str]]:
    """The kinds of note declared in lexicon/notes.yaml (or another file of the same shape): name -> (pattern, description)."""
    import yaml

    path = path or Path(__file__).parent / "lexicon" / "notes.yaml"
    table = yaml.safe_load(path.read_text(encoding="utf-8"))["kinds"]
    return {name: (re.compile("|".join(f"(?:{p})" for p in spec["patterns"]), re.I), spec["describes"])
            for name, spec in table.items()}


_KINDS = load_kinds()
_COMPILED = {name: rx for name, (rx, _) in _KINDS.items()}
DESCRIPTIONS = {name: desc for name, (_, desc) in _KINDS.items()}


def _reading_order(texts) -> list:
    """Top to bottom, left to right, in lines: a phrase split over two runs on one line ("SMOKE" "DETECTOR") stays together."""
    def line(t):
        h = t.height or max(t.bbox[3] - t.bbox[1], 1e-6)
        return (-round(((t.bbox[1] + t.bbox[3]) / 2) / h), t.bbox[0])
    return sorted(texts, key=line)


def note_counts(texts) -> dict[str, int] | None:
    """Number of mentions of each kind of safety provision on the sheet, or None when no text was read at all."""
    texts = [t for t in texts if t.text and t.text.strip()]
    if not texts:
        return None
    body = " ".join(" ".join(t.text.split()) for t in _reading_order(texts))
    return {name: len(rx.findall(body)) for name, rx in _COMPILED.items()}


def parse_fire_minutes(cell: str) -> float | None:
    """A fire rating cell of a door schedule ("20 MIN", "1 HR", "1-1/2 HR", "EI30", "NR", "-") as minutes; none for an unreadable cell."""
    t = " ".join((cell or "").lower().split())
    if not t:
        return None
    if t in {"-", "--", "none", "n/a", "na", "nr", "non", "aucun", "keine", "0"} or t.startswith(("not rated", "non rated")):
        return 0.0
    m = re.search(r"(\d+)\s*-\s*(\d+)/(\d+)\s*(?:hr|hour|h)", t)
    if m:
        return (int(m.group(1)) + int(m.group(2)) / int(m.group(3))) * 60
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*[- ]?\s*(?:hr|hour|heure|stunde|h)s?\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 60
    m = re.search(r"(?:rei|ei|f)\s?(\d{2,3})\b", t) or re.search(r"(\d+)\s*[- ]?\s*(?:min|minute)s?\b", t)
    if m:
        return float(m.group(1))
    return float(t) if re.fullmatch(r"\d{2,3}", t) else None


def kinds_named(sentence: str) -> list[str]:
    """The kinds of note a sentence of a requirement document is about, by the same words the sheets are searched for."""
    return [name for name, rx in _COMPILED.items() if rx.search(sentence or "")]
