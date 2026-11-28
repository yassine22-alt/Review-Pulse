"""Write quantities the way the checks expect them, before a model reads the clause.

Standards written for two audiences give every dimension twice: "54 inches (1370 mm) maximum", "1.2 m (4 ft)", "5 feet
(1.5 m)". A model that sees both numbers often copies the wrong one or converts it badly (1370 mm became 13.7), and the
number check then sees two figures where the sentence states one limit. Here the imperial equivalent is dropped and the
metric figure, which the document itself rounded, is kept with its unit. Nothing is converted by hand.

Only an equivalent in a *different system* is dropped (inches or feet next to mm, cm or m). "2 m (6.5 m)" or
"300 mm (maximum 400 mm)" are different statements and are left alone. A sentence with feet and inches and no metric
figure is left as it is; units.py reads feet and inches.
"""

from __future__ import annotations

import re

NUM = r"\d[\d.,]*(?:\s+\d+/\d+)?"
IMPERIAL = r"(?:inches|inch|in\.|in\b|feet|foot|ft\.?|\"|')"
METRIC = r"(?:mm|cm|m\b|millimet\w+|centimet\w+|met(?:er|re)s?\b)"

IMP_EXPR = rf"{NUM}\s*{IMPERIAL}(?:\s*{NUM}\s*{IMPERIAL})?"        # 54 in, 3 ft 6 in
_IMP_THEN_MET = re.compile(rf"{IMP_EXPR}\s*\(\s*({NUM}\s*{METRIC})\s*\)", re.I)
_MET_THEN_IMP = re.compile(rf"({NUM}\s*{METRIC})\s*\(\s*{IMP_EXPR}\s*\)", re.I)
_SQ_FT_THEN_M2 = re.compile(r"\d[\d.,]*\s*(?:sq\.?\s*ft|square feet|sf)\s*\(\s*(\d[\d.,]*\s*(?:m2|m²|sq\.?\s*m))\s*\)", re.I)


def one_unit_system(text: str) -> str:
    """Drop the imperial equivalent: "54 inches (1370 mm)" -> "1370 mm", "1.2 m (4 ft)" -> "1.2 m"."""
    text = _IMP_THEN_MET.sub(lambda m: m.group(1), text)
    text = _MET_THEN_IMP.sub(lambda m: m.group(1), text)
    return _SQ_FT_THEN_M2.sub(lambda m: m.group(1), text)


# ---- US typography: 3', 32", 8 1/4", 6'8", 70 s.f. ---------------------------------------------------------------------------
# Plan review checklists and codes written for US readers use the foot mark and the inch mark, fractions of an inch, and "s.f.".
# They are rewritten as a number and a unit word before anything reads the sentence ("3'" -> "3 ft", "6'8\"" -> "80 in").

_FEET_INCHES = re.compile(r"(\d+)\s*['′’]\s*-?\s*(\d+)(?:\s+(\d+)/(\d+))?\s*(?:\"|″|”)")
_INCHES = re.compile(r"(?<![\d/.])(\d+)(?:(?:\s+|\s*[-‑]\s*)(\d+)/(\d+)|\.(\d+))?\s*(?:\"|″|”)")
_FRACTION_INCH = re.compile(r"(?<![\d/])(\d+)/(\d+)\s*(?:\"|″|”)")
_FEET = re.compile(r"(?<![\w/])(\d+(?:\.\d+)?)\s*['′’](?![\w'])")
_SQ_FT = re.compile(r"(?<=\d)\s*(?:s\.\s?f\.?|sq\.?\s?ft\.?|sf)(?![A-Za-z])", re.I)


def us_typography(text: str) -> str:
    """Feet and inch marks and "s.f." as unit words, so that the rest of the pipeline sees a number and a unit."""
    def feet_inches(m):
        total = int(m.group(1)) * 12 + int(m.group(2)) + (int(m.group(3)) / int(m.group(4)) if m.group(3) and int(m.group(4)) else 0)
        return f"{total:g} in"

    def inches(m):
        whole = float(m.group(1))
        if m.group(2) and int(m.group(3)):
            whole += int(m.group(2)) / int(m.group(3))
        elif m.group(4):
            whole = float(f"{m.group(1)}.{m.group(4)}")
        return f"{whole:g} in"

    text = _FEET_INCHES.sub(feet_inches, text)
    text = _INCHES.sub(inches, text)
    text = _FRACTION_INCH.sub(lambda m: f"{int(m.group(1)) / int(m.group(2)):g} in" if int(m.group(2)) else m.group(0), text)
    text = _FEET.sub(lambda m: f"{m.group(1)} ft", text)
    text = re.sub(r"(?<=\d) (in|ft)\s*[x×]\s*(?=\d)", r" \1 x ", text)          # 22"x30" -> 22 in x 30 in
    return _SQ_FT.sub(" sq ft", text)


def normalise_quantities(text: str) -> str:
    """Everything done to the figures of a sentence before it is read: US typography, then one unit system."""
    return one_unit_system(us_typography(strip_examples(strip_references(text))))


_EXAMPLE = re.compile(r"\s*\(\s*(?:e\.\s?g\.|i\.\s?e\.|such as|for example|for instance|par exemple|p\.\s?ex\.|z\.\s?b\.|"
                      r"zum beispiel|por ejemplo|ad esempio|per esempio)[^)]*\)", re.I)


def strip_examples(text: str) -> str:
    """A parenthesis that only gives examples ("all rooms (e.g. bedrooms, kitchen, etc.)") restricts nothing: left in, its words look
    like the categories the requirement is about and the rule gets limited to them."""
    return _EXAMPLE.sub("", text)


# ---- references to sections of the code: "311.6", "Table 302.1(1)", "(FBC-R R311.7, R312.1)" --------------------------------------
# Codes, standards and checklists cite their own sections inline. A section number is not a figure of the requirement, and left in
# the sentence it is read as a second quantity ("min. 3 ft wide. 311.6"), so every limit looks like two. They are taken out of the
# text the checks and the model read (the clause shown to the person is never changed).

_UNIT_AFTER = r"(?!\s*(?:m\b|mm\b|cm\b|km\b|in\b|ft\b|sq\b|ft2|m2|%|deg|°|per\s*cent))"
_REF = (r"(?:(?:Table|Figure|Fig\.|Section|Sec\.|Chapter|Ch\.|IRC|IBC|IECC|IFC|NFPA|FBC(?:-[A-Z]+)?|ADA|ANSI|ICC)\s*)?"
        r"[A-Z]?\d{2,4}(?:\.\d+)+(?:\([0-9A-Za-z]{1,3}\))*" + _UNIT_AFTER)
_REF_LIST = rf"{_REF}(?:\s*(?:,|;|and|&)\s*{_REF})*"
_BRACKETED_REF = re.compile(rf"\s*\(\s*(?:[A-Za-z][A-Za-z\-]{{1,8}}\s+)?{_REF_LIST}\s*\)")
_LEADING_WORD_REF = re.compile(rf"\s*\b(?:per|see|under|in accordance with|according to|pursuant to|as per)\s+{_REF_LIST}", re.I)
_TRAILING_REF = re.compile(rf"(?:\s*[,;]?\s+|\s*\.\s+)(?:[A-Z]{{2,6}}\s+)?{_REF_LIST}\s*\.?\s*$")


def strip_references(text: str) -> str:
    """The sentence without the section numbers it cites ("Hallways must be min. 3 ft wide. 311.6" -> "... wide.")."""
    before = None
    while before != text:                     # a sentence can end with several references one after the other
        before = text
        text = _BRACKETED_REF.sub("", text)
        text = _LEADING_WORD_REF.sub("", text)
        text = _TRAILING_REF.sub(".", text) if _TRAILING_REF.search(text) else text
    return re.sub(r"\.\s*\.", ".", text).strip()

# a code named by initials after the last full stop ("... treads min. 9 in. PA UCC") is a citation, not part of the sentence
_TRAILING_CODE = re.compile(r"(?<=[.!?])\s+(?:[A-Z][A-Z\-]{1,7}\s*){1,4}$")
_strip_references_core = strip_references


def strip_references(text: str) -> str:  # noqa: F811 - the public name includes the trailing code names
    return _TRAILING_CODE.sub("", _strip_references_core(text)).strip()
