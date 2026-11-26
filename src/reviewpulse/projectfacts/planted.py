"""Generated cover and code analysis sheets with a known truth, for measuring the reader without labels.

Labels are drawn from the cue words of the field file in the language of the sheet, in a shuffled order; values are written the
way the language writes them. Layouts: `colon` (one text line "LABEL: value"), `cells` (label cell, value cell to its right),
`stacked` (header cell above its value). `ruled` adds table rules to the page; the reader never looks at them, which the
test shows by getting the same answer. Units are in the value cell or in the header of the area table."""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np

from ..drawingset.pagedata import Line, PageData

LABELS = {                       # a label per language and field, chosen among the cues of fields.yaml
    "en": {"number_of_storeys": ["Number of stories", "Stories", "Number of storeys"], "sprinklered": ["Sprinklers", "Sprinkler system", "Fire sprinklers"],
           "building_class": ["Use", "Occupancy", "Building use"], "construction_type": ["Construction type", "Type of construction"],
           "code_edition": ["Applicable code", "Governing code"], "jurisdiction": ["Jurisdiction", "Municipality"],
           "building_height": ["Building height", "Height of building"], "gross_floor_area": ["Gross area", "Total floor area"]},
    "fr": {"number_of_storeys": ["Nombre d'etages", "Nombre de niveaux"], "sprinklered": ["Sprinklers", "Extinction automatique"],
           "building_class": ["Usage", "Destination"], "construction_type": ["Type de construction", "Mode de construction"],
           "code_edition": ["Code applicable", "Reglementation"], "jurisdiction": ["Commune", "Municipalite"],
           "building_height": ["Hauteur du batiment", "Hauteur totale"], "gross_floor_area": ["Surface totale", "Surface de plancher"]},
    "de": {"number_of_storeys": ["Anzahl Geschosse", "Vollgeschosse"], "sprinklered": ["Sprinkleranlage", "Sprinkler"],
           "building_class": ["Nutzung", "Gebäudenutzung"], "construction_type": ["Bauart", "Bauweise"],
           "code_edition": ["Anwendbare Vorschriften", "Bauordnung"], "jurisdiction": ["Gemeinde", "Baubehörde"],
           "building_height": ["Gebäudehöhe", "Firsthöhe"], "gross_floor_area": ["Bruttogeschossfläche", "Gesamtfläche"]},
}
WORDS = {                        # a value per language
    "yes": {"en": "Yes", "fr": "Oui", "de": "Ja"}, "no": {"en": "No", "fr": "Non", "de": "Nein"},
    "single_family_dwelling": {"en": "Single family dwelling", "fr": "Maison individuelle", "de": "Einfamilienhaus"},
    "office": {"en": "Office", "fr": "Bureaux", "de": "Büro"},
    "wood_frame": {"en": "Wood frame", "fr": "Ossature bois", "de": "Holzbau"},
    "masonry": {"en": "Masonry", "fr": "Maçonnerie", "de": "Mauerwerk"},
    "editions": {"en": "2018 International Building Code", "fr": "Code de la construction 2020", "de": "Bauordnung 2019"},
    "places": {"en": "City of Springfield", "fr": "Commune de Morges", "de": "Gemeinde Cleebronn"},
}
LEVELS = {"en": ["Ground floor", "First floor", "Second floor"], "fr": ["Rez-de-chaussée", "1er étage", "2e étage"],
          "de": ["Erdgeschoss", "1. Obergeschoss", "2. Obergeschoss"]}


@dataclass
class Truth:
    values: dict[str, object]                    # field -> canonical value (building level)
    levels: dict[str, float]                     # level label -> area m2


def _num(x: float, lang: str, unit: str) -> str:
    if unit == "ft2":
        return f"{x:,.0f}"
    s = f"{x:,.1f}" if x % 1 else f"{x:,.0f}"
    if lang == "en":
        return s
    return s.replace(",", " ").replace(".", ",") if lang == "fr" else s.replace(",", "x").replace(".", ",").replace("x", ".")


def make_cover(lang: str = "en", *, storeys: int = 2, sprinklered: bool = False, use: str = "single_family_dwelling",
               construction: str = "wood_frame", height_m: float = 8.5, area_m2: float = 190.0, layout: str = "colon",
               ruled: bool = False, unit_in: str = "cell", imperial: bool = False, level_areas: tuple[float, ...] = (95.0, 80.0, 15.0),
               seed: int = 0, drop: tuple[str, ...] = ()) -> tuple[PageData, Truth]:
    rng = random.Random(seed)
    rows: list[tuple[str, str, object]] = []        # (label, value text, truth)
    L = LABELS[lang]
    vals: dict[str, object] = {}

    def add(field: str, text: str, truth: object):
        if field in drop:
            return
        rows.append((rng.choice(L[field]), text, truth))
        vals[field] = truth

    add("number_of_storeys", str(storeys), storeys)
    add("sprinklered", WORDS["yes" if sprinklered else "no"][lang], sprinklered)
    add("building_class", WORDS[use][lang], use)
    add("construction_type", WORDS[construction][lang], construction)
    add("code_edition", WORDS["editions"][lang], WORDS["editions"][lang])
    add("jurisdiction", WORDS["places"][lang], WORDS["places"][lang])
    if imperial:
        add("building_height", f"{height_m / 0.3048:.1f} ft", round(height_m, 4))
        unit = "ft2"
        shown = area_m2 / 0.09290304
    else:
        add("building_height", f"{_num(height_m, lang, 'm')} m", round(height_m, 4))
        unit = "m2"
        shown = area_m2
    sym = "SF" if unit == "ft2" else "m²"
    add("gross_floor_area", f"{_num(shown, lang, unit)} {sym}" if unit_in == "cell" else _num(shown, lang, unit), round(area_m2, 4))
    if unit_in == "header" and "gross_floor_area" not in drop:
        rows = [(f"{lab} ({sym})" if lab in L["gross_floor_area"] else lab, v, t) for lab, v, t in rows]
    rng.shuffle(rows)
    pg = PageData(0, 1200.0, 900.0)
    rects = []
    y = 100.0
    for lab, text, _ in rows:
        if layout == "colon":
            pg.lines.append(Line(f"{lab.upper() if rng.random() < .5 else lab}: {text}", 60, y, 60 + 7 * (len(lab) + len(text) + 2), y + 10, 10))
        elif layout == "cells":
            pg.lines.append(Line(lab, 60, y, 60 + 7 * len(lab), y + 10, 10))
            pg.lines.append(Line(text, 360, y, 360 + 7 * len(text), y + 10, 10))
        else:                                        # stacked
            pg.lines.append(Line(lab, 60, y, 60 + 7 * len(lab), y + 10, 10))
            y += 14
            pg.lines.append(Line(text, 60, y, 60 + 7 * len(text), y + 10, 10))
        if ruled:
            rects += [(40, y - 4, 700, y - 3), (40, y + 12, 700, y + 13), (350, y - 4, 351, y + 13)]
        y += 28
    # the area by level: a table, level names at the left, values in the column of the header
    levels: dict[str, float] = {}
    unitw = "SF" if imperial else "m²"
    pg.lines.append(Line(f"Area ({unitw})" if unit_in == "header" else "Area", 360, y + 20, 440, y + 30, 10))
    y += 44
    for name, a in zip(LEVELS[lang], level_areas, strict=False):
        if f"level:{name}" in drop:
            continue
        val = a / 0.09290304 if imperial else a
        cell = _num(val, lang, "ft2" if imperial else "m2")
        cell = cell if unit_in == "header" else f"{cell} {unitw}"
        pg.lines.append(Line(name, 60, y, 60 + 7 * len(name), y + 10, 10))
        pg.lines.append(Line(cell, 360, y, 360 + 7 * len(cell), y + 10, 10))
        levels[name] = round(a, 4)
        if ruled:
            rects += [(40, y - 4, 700, y - 3), (350, y - 4, 351, y + 13)]
        y += 20
    if rects:
        pg.rects = np.array(rects, dtype=float)
    return pg, Truth(vals, levels)
