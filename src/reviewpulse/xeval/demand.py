"""Demand analysis: what do real requirement sentences ask to be measured, and how much can we measure today?

No model and no labels. A deterministic parser finds each quantity (number, unit) in a sentence, a keyword table
names what it is a quantity of, and a second table says whether a plan reader gives us that measurement.
The tables are editable and are the only judgement in the analysis; the counts come from the text.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# ---- quantities ----------------------------------------------------------------------------------

def _unit_patterns() -> list[tuple[str, str]]:
    """(regex, canonical symbol), longest spellings first: the words people write, then every symbol of the unit table with
    its SI prefixes. Symbols are matched case-sensitively (a lower-case "a" after a number is a word, not an ampere)."""
    from ..interpreter import units as U

    out: list[tuple[str, str]] = []
    words = sorted(((w, sym) for sym, ws in U._DATA.get("words", {}).items() for w in ws), key=lambda t: -len(t[0]))
    for word, sym in words:
        out.append((r"(?i:" + re.escape(word).replace(r"\ ", r"\s?") + r")(?![^\W\d_])", sym))
    extra = [(r"m\s?2|m²", "m2"), (r"m\s?3|m³", "m3"), (r"°C|°F", "Cel"), (r"l/s", "L/s"), (r"W/m2K|W/\(?m2\s?K\)?", "W/m2K"),
             (r"kN/m2", "kN/m2"), (r"kg/m2", "kg/m2"), (r"dB", "dB"), (r"lux", "lx"), (r"per ?cent|pour ?cent", "%")]
    out += extra
    prefixes = sorted(U.PREFIXES, key=len, reverse=True)
    symbols = sorted((s for s in U.UNITS if s not in ("1", "count") and s.isascii()), key=len, reverse=True)
    for sym in symbols:
        if sym in U.PREFIXABLE:
            out.append(((r"(?-i:(?:" + "|".join(map(re.escape, prefixes)) + r")?" + re.escape(sym) + r")") + r"(?![A-Za-zµ°²³0-9])", sym))
        else:
            out.append((r"(?-i:" + re.escape(sym) + r")(?![A-Za-zµ°²³0-9])", sym))
    out += [(r"%", "%"), (r"°", "deg")]
    return out


UNITS = _unit_patterns()
UNIT_RE = "|".join(f"(?P<u{i}>{pat})" for i, (pat, _) in enumerate(UNITS))
NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?"
QUANTITY = re.compile(rf"(?P<num>{NUMBER})\s*(?:-|–|to|à|et|and|or)?\s*(?P<num2>{NUMBER})?\s*(?:{UNIT_RE})", re.I)
RATIO = re.compile(r"\b1\s?(?::|in)\s?(\d{1,3})\b")
COUNT = re.compile(r"\b(?:at least|no (?:more|fewer|less) than|more than|not (?:more|less) than|up to|minimum of)"
                   r"\s+(?:one|two|three|four|five|six|\d+)\b|\b(?:one|two|three|\d+)\s+"
                   r"(?:storeys?|stor(?:e)?ys?|floors?|exits?|stairs?|persons?|people|occupants?|doors?|"
                   r"bedrooms?|escape routes?)\b", re.I)


def to_number(text: str, french: bool = False) -> float:
    if french or re.fullmatch(r"\d+,\d{1,2}", text):
        return float(text.replace(" ", "").replace(",", "."))
    return float(text.replace(",", ""))


@dataclass
class Quantity:
    value: float
    unit: str
    span: tuple[int, int]


def quantities(sentence: str, french: bool = False) -> list[Quantity]:
    sentence = re.sub(r"\s+", " ", sentence)     # PDF text often has double spaces
    found = []
    for m in QUANTITY.finditer(sentence):
        unit = next(UNITS[i][1] for i in range(len(UNITS)) if m.group(f"u{i}"))
        written = m.group(0)[len(m.group("num")):].strip()
        from ..interpreter.units import is_unit

        if is_unit(written):               # a prefixed symbol keeps the unit as it was written ("kPa", "mm")
            unit = written
        try:
            found.append(Quantity(to_number(m.group("num"), french), unit, m.span()))
            if m.group("num2"):         # a range keeps both bounds
                found.append(Quantity(to_number(m.group("num2"), french), unit, m.span()))
        except ValueError:
            continue
    for m in RATIO.finditer(sentence):
        found.append(Quantity(1 / float(m.group(1)), "ratio", m.span()))
    return found


# ---- what a quantity is a quantity of -----------------------------------------------------------

PROPERTY_WORDS = [  # (property, regex), first match wins; text is lower-case
    ("fire resistance", r"fire[- ]resist|fire rating|rated|reaction to fire|integrity|insulation .*minutes|ei ?\d|rei"),
    ("acoustic", r"sound|acoustic|noise|decibel|\bdb\b|airborne|impact"),
    ("thermal / energy", r"thermal|u-value|insulat|heat loss|energy|transmittance|w/m2k|overheating"),
    ("ventilation / air", r"ventilat|air ?flow|air change|extract|airtight|l/s"),
    ("lighting / daylight", r"daylight|illuminat|lux|glaz|light"),
    ("structural load", r"load|kn|stress|strength|deflection|span"),
    ("slope / gradient", r"gradient|slope|ramp|incline|pitch|1 in \d|1:\d"),
    ("stair geometry", r"riser|rise\b|going|tread|stair|step|flight|landing|nosing"),
    ("headroom / height", r"headroom|height|high\b|clear height|ceiling|sill|above floor|above ground|storey height"),
    ("width / clear opening", r"width|wide|clear opening|door|opening|corridor|passage"),
    ("distance / travel", r"distance|travel|within \d|from any|no further|separation|away from|boundary"),
    ("floor area", r"floor area|area of|total area|\barea\b|m2|m²|room size"),
    ("depth / thickness / diameter / length",
     r"depth|thick|diameter|length|long\b|cover|cavity|radius"),
    ("number of storeys / occupants / items", r"storeys?|stories|occupan|persons|people|number of|exits?|at least (one|two|\d)"),
]

# What do we get from a plan today?  (editable judgement; "measured" = the plan reader exports it)
SUPPLY = {
    "width / clear opening": "measured",            # opening widths and room minimum widths
    "floor area": "measured",                       # room areas
    "distance / travel": "partial",                 # route distance exists in the old engine, not in the new facts
    "number of storeys / occupants / items": "partial",     # counts of rooms/openings; storeys, occupants not read
    "slope / gradient": "plan, not measured yet",
    "stair geometry": "partial",                    # tread depth, width and tread lines of detected flights (about 57% of drawn stairs)
    "depth / thickness / diameter / length": "plan, not measured yet",
    "headroom / height": "needs section or schedule",
    "fire resistance": "needs specification or schedule",
    "acoustic": "needs specification or test data",
    "thermal / energy": "needs specification or calculation",
    "ventilation / air": "needs specification or calculation",
    "lighting / daylight": "needs calculation (glazing ratio is partly derivable)",
    "structural load": "needs calculation or structural drawings",
}


# Requirements without a number: what do they ask for, and could a graph of the plan answer them?
QUALITATIVE = [   # first match wins
    ("reference to another document or clause", r"in accordance with|comply with|complies with|compliance with|"
     r"as specified in|referred to in|see (?:section|part|annex)|standard|\bpart [a-z]\b|approved document"),
    ("prohibition", r"not be permitted|not permitted|shall not|must not|should not|may not|prohibited|not allowed|"
     r"no [a-z]+ (?:shall|may|should) be"),
    ("access, route or connection", r"access|route|connect|adjacent|lead|leads|approach|entrance|exit|escape|"
     r"through|between|separat|enclos|compartment|accessible"),
    ("provision / presence", r"provided|provide|installed|install|equipped|fitted|marked|signed|identified|"
     r"located|available|must have|shall have|should have|include"),
    ("quality or judgement", r"adequate|sufficient|suitable|appropriate|reasonable|safe|clear|effective|"
     r"practicable|where necessary|as far as|as gentle|minimi[sz]e|avoid"),
]
GRAPH_FRIENDLY = {"access, route or connection", "provision / presence", "prohibition"}


def classify_qualitative(sentence: str) -> str:
    low = re.sub(r"\s+", " ", sentence.lower())
    for kind, pattern in QUALITATIVE:
        if re.search(pattern, low):
            return kind
    return "other"


def classify(sentence: str, quantity: Quantity) -> str:
    low = sentence.lower()
    window = low[max(0, quantity.span[0] - 90): quantity.span[1] + 60]
    for prop, pattern in PROPERTY_WORDS:
        if re.search(pattern, window):
            return prop
    for prop, pattern in PROPERTY_WORDS:
        if re.search(pattern, low):
            return prop
    return "unclassified"


# ---- the analysis --------------------------------------------------------------------------------


def load_sentences(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [row["content"].strip() for row in csv.DictReader(fh) if row.get("content", "").strip()]


def analyse(sentences: list[str], french: bool = False) -> dict:
    with_q, per_prop, per_unit, status = 0, Counter(), Counter(), Counter()
    qualitative = Counter()
    count_only = 0
    examples: dict[str, list[str]] = {}
    for sentence in sentences:
        qs = quantities(sentence, french)
        if not qs:
            if not COUNT.search(sentence):
                qualitative[classify_qualitative(sentence)] += 1
            if COUNT.search(sentence):
                count_only += 1
                per_prop["number of storeys / occupants / items"] += 1
                status[SUPPLY["number of storeys / occupants / items"]] += 1
            continue
        with_q += 1
        props = {classify(sentence, q) for q in qs}
        for q in qs:
            per_unit[q.unit] += 1
        for prop in props:
            per_prop[prop] += 1
            status[SUPPLY.get(prop, "unclassified")] += 1
            examples.setdefault(prop, [])
            if len(examples[prop]) < 2:
                examples[prop].append(sentence[:200])
    n = len(sentences)
    return {
        "sentences": n, "with_quantity": with_q, "count_only": count_only,
        "no_quantity": n - with_q - count_only,
        "qualitative": qualitative.most_common(),
        "qualitative_graph_friendly": round(sum(c for k, c in qualitative.items() if k in GRAPH_FRIENDLY)
                                            / max(sum(qualitative.values()), 1), 3),
        "by_unit": per_unit.most_common(), "by_property": per_prop.most_common(),
        "by_supply": status.most_common(), "examples": examples,
        "share_measured_or_partial": round((status["measured"] + status["partial"]) / max(sum(status.values()), 1), 3),
        "share_measured": round(status["measured"] / max(sum(status.values()), 1), 3),
    }


def markdown(result: dict, source: str) -> str:
    n = result["sentences"]
    pct = lambda x: f"{x / n:.0%}"  # noqa: E731
    out = ["# Demand analysis: what requirements ask to be measured", "",
           f"Source: {source}. Sentences: {n}. Method: deterministic quantity parser and keyword table, no model.", "",
           f"- with at least one numeric quantity: {result['with_quantity']} ({pct(result['with_quantity'])})",
           f"- count-style requirement without units: {result['count_only']} ({pct(result['count_only'])})",
           f"- no quantity found (qualitative or beyond this parser): {result['no_quantity']} "
           f"({pct(result['no_quantity'])})", "", "## What is asked, and can we measure it?", "",
           "| Quantity of | Sentences | Plan reader today |", "|---|---|---|"]
    for prop, count in result["by_property"]:
        out.append(f"| {prop} | {count} | {SUPPLY.get(prop, 'unclassified')} |")
    out += ["", "## Requirements without a number: what they ask for", "",
            "| Kind | Sentences | Could a plan graph answer it? |", "|---|---|---|"]
    for kind, count in result["qualitative"]:
        verdict = ("often, as a presence, route or relation check" if kind in GRAPH_FRIENDLY
                   else "points elsewhere" if kind.startswith("reference") else "needs a person's judgement"
                   if kind.startswith("quality") else "unknown")
        out.append(f"| {kind} | {count} | {verdict} |")
    out += ["", "## Supply summary (counts quantity groups, a sentence can appear in several)", "",
            "| Status | Groups |", "|---|---|"]
    out += [f"| {s} | {c} |" for s, c in result["by_supply"]]
    out += ["", f"Share of requested quantities that are measured today: {result['share_measured']:.0%}; "
                f"measured or partly: {result['share_measured_or_partial']:.0%}.", "", "## Units seen", ""]
    out += [f"- {u}: {c}" for u, c in result["by_unit"]]
    out += ["", "## Examples", ""]
    for prop, sents in result["examples"].items():
        out += [f"**{prop}**"] + [f"- {s}" for s in sents] + [""]
    out += ["## Caveats", "",
            "- Keyword classification is crude: it can mislabel a quantity. Use the table for ranking, not for exact counts.",
            "- The corpus is England and Finland building regulations in English; it says nothing about other subjects or languages.",
            "- Sentences were chosen by the corpus authors as self-contained rules, so qualitative clauses are under-represented."]
    return "\n".join(out) + "\n"


def run(csv_path: Path, out_dir: Path, french: bool = False) -> dict:
    result = analyse(load_sentences(csv_path), french)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "demand.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    (out_dir / "demand.md").write_text(markdown(result, csv_path.name), encoding="utf-8")
    return result
