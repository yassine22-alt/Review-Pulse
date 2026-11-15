"""Meaning-preserving rewrites of a requirement sentence. The reference rule must not change.

If a checker or a drafter reacts to any of these, it is relying on surface form instead of meaning.
"""

from __future__ import annotations

import copy
import random
import re

from .synth import Item

UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?(mm|cm|m)(?![\w²])")
KINDS = ("spacing", "reference_prefix", "reference_suffix", "distractor", "unit_swap", "shout", "newline_wrap")
DISTRACTORS = {"en": "These requirements apply to all new works and to works on existing buildings. ",
               "fr": "Les présentes exigences s'appliquent à tous les travaux neufs et aux travaux sur existant. "}
REFS = {"en": ("Subject to Article 4, ", " See also Table 2 and Annex 3."),
        "fr": ("Sous réserve de l'article 4, ", " Voir aussi le tableau 2 et l'annexe 3.")}


def _fmt(value: float, fr: bool) -> str:
    text = f"{value:g}"
    return text.replace(".", ",") if fr else text


def _swap_units(text: str, fr: bool, rng: random.Random) -> str:
    def repl(m):
        raw = float(m.group(1).replace(",", "."))
        metres = raw * {"mm": 0.001, "cm": 0.01, "m": 1.0}[m.group(2)]
        unit = rng.choice([u for u in ("mm", "cm", "m") if u != m.group(2)])
        scaled = round(metres / {"mm": 0.001, "cm": 0.01, "m": 1.0}[unit], 6)
        return f"{_fmt(scaled, fr)} {unit}"

    return UNIT_RE.sub(repl, text)


def perturb(item: Item, kind: str, seed: int = 0) -> Item:
    rng = random.Random(f"{item.id}-{kind}-{seed}")
    fr = item.lang == "fr"
    text = item.text
    if kind == "spacing":
        words = text.split(" ")
        text = "".join(w + rng.choice([" ", "  ", " ", "   "]) for w in words).strip()
    elif kind == "reference_prefix":
        text = REFS[item.lang][0] + text[0].lower() + text[1:]
    elif kind == "reference_suffix":
        text = text + REFS[item.lang][1]
    elif kind == "distractor":
        text = DISTRACTORS[item.lang] + text
    elif kind == "unit_swap":
        text = _swap_units(text, fr, rng)
    elif kind == "shout":
        text = text.upper()
    elif kind == "newline_wrap":
        words = text.split(" ")
        text = " ".join(w + ("\n" if i % 6 == 5 else "") for i, w in enumerate(words)).replace(" \n", "\n")
    else:
        raise KeyError(kind)
    clone = copy.deepcopy(item)
    clone.text = text
    return clone
