"""Planted schedules for the tests and the audit: PDFs drawn with pymupdf from a known table, in English, French or German, with
shuffled and renamed columns, a unit in the header or in the cell, ruled or not, and the truth of every cell kept aside.

Two header pools: `vocab` headers a drawing commonly uses (some of them are in vocabulary.yaml, which is the point of a
vocabulary) and `wild` headers chosen NOT to be in it, to measure what the words cannot place.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

HEADERS = {
    "en": {
        "tag": ["Mark", "Door No.", "Tag", "ID"],
        "width": ["Width", "Door Width", "Clear Width"],
        "height": ["Height", "Door Height"],
        "fire_rating": ["Fire Rating", "Rating", "Fire Resistance"],
        "type": ["Type", "Door Type"],
        "quantity": ["Qty", "Quantity"],
        "sill": ["Sill Height", "Sill"],
        "glazing": ["Glazing", "Glass"],
        "room_name": ["Room Name", "Name"],
        "area": ["Area", "Floor Area"],
        "ceiling_height": ["Ceiling Height", "Clg Ht"],
        "finish_floor": ["Floor Finish", "Flooring"],
        "finish_wall": ["Wall Finish", "Walls"],
        "finish_ceiling": ["Ceiling Finish", "Ceiling"],
        "power": ["Wattage", "Power"],
        "voltage": ["Voltage", "Volts"],
        "manufacturer": ["Manufacturer", "Mfr"],
        "size": ["Size", "Nominal Size"],
    },
    "fr": {
        "tag": ["Repère", "N°", "Numéro"],
        "width": ["Largeur", "Larg."],
        "height": ["Hauteur", "Haut."],
        "fire_rating": ["Résistance au feu", "Coupe-feu"],
        "type": ["Type", "Nature"],
        "quantity": ["Qté", "Nombre"],
        "sill": ["Allège", "Hauteur d'allège"],
        "glazing": ["Vitrage", "Type de vitrage"],
        "room_name": ["Nom de la pièce", "Désignation pièce"],
        "area": ["Surface", "Superficie"],
        "ceiling_height": ["Hauteur sous plafond", "HSP"],
        "finish_floor": ["Revêtement de sol", "Sol"],
        "finish_wall": ["Revêtement mural", "Murs"],
        "finish_ceiling": ["Plafond", "Finition plafond"],
        "power": ["Puissance"],
        "voltage": ["Tension"],
        "manufacturer": ["Fabricant", "Marque"],
        "size": ["Dimensions", "Taille"],
    },
    "de": {
        "tag": ["Pos.", "Nr.", "Kennzeichen"],
        "width": ["Breite", "Türbreite"],
        "height": ["Höhe", "Türhöhe"],
        "fire_rating": ["Feuerwiderstand", "Brandschutzklasse"],
        "type": ["Typ", "Bauart"],
        "quantity": ["Anzahl", "Menge"],
        "sill": ["Brüstung", "Brüstungshöhe"],
        "glazing": ["Verglasung", "Glas"],
        "room_name": ["Raumbezeichnung", "Raumname"],
        "area": ["Fläche", "Grundfläche"],
        "ceiling_height": ["Raumhöhe", "Deckenhöhe"],
        "finish_floor": ["Bodenbelag", "Fußboden"],
        "finish_wall": ["Wandbelag", "Wände"],
        "finish_ceiling": ["Deckenbelag", "Decke"],
        "power": ["Leistung"],
        "voltage": ["Spannung"],
        "manufacturer": ["Hersteller"],
        "size": ["Abmessungen", "Maße"],
    },
}
WILD = {
    "en": {"width": ["Wd", "Opening W"], "height": ["Ht", "Opening H"], "fire_rating": ["UL Label", "Hr Class"],
           "tag": ["Opng", "Unit"], "type": ["Config", "Leaf"], "sill": ["AFF", "Bottom of Glass"]},
    "fr": {"width": ["Passage", "Ouverture L"], "height": ["Ouverture H", "Passage H"], "fire_rating": ["Classement", "Degré CF"],
           "tag": ["Pos", "Elt"], "type": ["Config.", "Vantail"], "sill": ["Appui", "Cote d'appui"]},
    "de": {"width": ["Öffnung B", "NB"], "height": ["Öffnung H", "NH"], "fire_rating": ["Klasse", "Schutzklasse"],
           "tag": ["Element", "Lfd."], "type": ["Ausführung", "Flügel"], "sill": ["Parapet", "Brüstung UK"]},
}
TITLES = {
    "doors": {"en": "DOOR SCHEDULE", "fr": "TABLEAU DES PORTES", "de": "TÜRLISTE"},
    "windows": {"en": "WINDOW SCHEDULE", "fr": "TABLEAU DES FENÊTRES", "de": "FENSTERLISTE"},
    "rooms": {"en": "ROOM SCHEDULE", "fr": "TABLEAU DES LOCAUX", "de": "RAUMBUCH"},
    "finishes": {"en": "FINISH SCHEDULE", "fr": "TABLEAU DES FINITIONS", "de": "OBERFLÄCHENLISTE"},
    "fixtures": {"en": "LIGHTING FIXTURE SCHEDULE", "fr": "TABLEAU DES LUMINAIRES", "de": "LEUCHTENLISTE"},
}
TEXTS = {
    "type": {"en": ["Solid core", "Hollow metal", "Flush wood", "Glazed"], "fr": ["Bois plein", "Acier", "Vitrée", "Alvéolaire"],
             "de": ["Vollholz", "Stahl", "Glas", "Röhrenspan"]},
    "glazing": {"en": ["Double low-e", "Single", "Triple"], "fr": ["Double vitrage", "Simple", "Triple"],
                "de": ["Zweifach", "Einfach", "Dreifach"]},
    "room_name": {"en": ["Bedroom", "Kitchen", "Bath", "Living"], "fr": ["Chambre", "Cuisine", "Salle de bains", "Séjour"],
                  "de": ["Schlafzimmer", "Küche", "Bad", "Wohnen"]},
    "finish_floor": {"en": ["Oak", "Tile", "Carpet"], "fr": ["Parquet chêne", "Carrelage", "Moquette"], "de": ["Eiche", "Fliesen", "Teppich"]},
    "finish_wall": {"en": ["Paint", "Tile", "Wallpaper"], "fr": ["Peinture", "Faïence", "Papier peint"], "de": ["Anstrich", "Fliesen", "Tapete"]},
    "finish_ceiling": {"en": ["Gypsum", "Paint", "ACT"], "fr": ["Plâtre", "Peinture", "Dalles"], "de": ["Gips", "Anstrich", "Platten"]},
    "manufacturer": {"en": ["Acme", "Lumo", "Vertex"], "fr": ["Acme", "Lumo", "Vertex"], "de": ["Acme", "Lumo", "Vertex"]},
}
COLUMNS = {
    "doors": ["tag", "width", "height", "fire_rating", "type", "quantity"],
    "windows": ["tag", "width", "height", "sill", "glazing", "quantity"],
    "rooms": ["tag", "room_name", "area", "ceiling_height"],
    "finishes": ["tag", "room_name", "finish_floor", "finish_wall", "finish_ceiling"],
    "fixtures": ["tag", "power", "voltage", "manufacturer", "quantity"],
}
TAG_PREFIX = {"doors": "D", "windows": "W", "rooms": "", "finishes": "", "fixtures": "L"}


@dataclass
class Planted:
    path: str
    truth: dict = field(default_factory=dict)      # (table index, tag key, meaning) -> value_si, or text
    spec: list[dict] = field(default_factory=list)


def _fmt_len(mm: float, unit: str, lang: str, unit_in_cell: bool) -> str:
    if unit == "in":
        total = round(mm / 25.4)
        return f"{total // 12}'-{total % 12}\""
    v = {"mm": mm, "cm": mm / 10, "m": mm / 1000}[unit]
    s = f"{v:.2f}".rstrip("0").rstrip(".") if unit != "mm" else f"{int(mm)}"
    if unit == "m":
        s = f"{v:.2f}"
    if lang in ("fr", "de"):
        s = s.replace(".", ",")
    return f"{s} {unit}" if unit_in_cell else s


def _fire_cell(minutes: int, lang: str) -> str:
    if minutes == 0:
        return {"en": "NR", "fr": "-", "de": "-"}[lang]
    if lang == "en":
        return f"{minutes // 60} HR" if minutes % 60 == 0 else f"{minutes} MIN"
    if lang == "fr":
        return f"EI {minutes}"
    return f"F{minutes}"


def make_table_spec(kind: str, lang: str, rng: random.Random, n_rows: int = 6, unit: str = "mm", unit_in_cell: bool = False,
                    pool: str = "vocab", ruled: bool = False, shuffle: bool = True, size_column: bool = False,
                    two_line_header: bool = False, drop: int = 0) -> dict:
    cols = list(COLUMNS[kind])
    if size_column and "width" in cols and "height" in cols:
        i = cols.index("width")
        cols.remove("width")
        cols.remove("height")
        cols.insert(i, "size")
    for _ in range(drop):                                   # a column the schedule does not carry
        cand = [c for c in cols if c != "tag" and c != "room_name"]
        if len(cand) > 2:
            cols.remove(rng.choice(cand))
    if shuffle:
        rest = cols[1:]
        rng.shuffle(rest)
        cols = [cols[0]] + rest if rng.random() < 0.7 else rest + [cols[0]]
    return dict(kind=kind, lang=lang, n_rows=n_rows, unit=unit, unit_in_cell=unit_in_cell, pool=pool, ruled=ruled, cols=cols,
                size_column=size_column, two_line_header=two_line_header)


def _header_text(meaning: str, lang: str, pool: str, rng: random.Random, unit: str | None, unit_in_cell: bool, spec_kind: str) -> str:
    names = (WILD.get(lang, {}).get(meaning) if pool == "wild" else None) or HEADERS[lang][meaning]
    h = rng.choice(names)
    if meaning in ("width", "height", "sill", "ceiling_height", "size") and not unit_in_cell and unit != "in":
        h += f" ({unit})"
    if meaning == "area" and not unit_in_cell:
        h += " (m²)"
    if meaning == "power" and not unit_in_cell:
        h += " (W)"
    if meaning == "voltage" and not unit_in_cell:
        h += " (V)"
    return h


def draw_pdf(path: str, specs: list[dict], seed: int = 0) -> Planted:
    """One page, the tables stacked. The truth is {(table index 1.., tag key, meaning): SI value or text}."""
    import pymupdf

    from ..annotate.text_classify import tag_key

    rng = random.Random(seed)
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=1190)
    out = Planted(path)
    y = 60.0
    fs = 9.0
    for ti, spec in enumerate(specs, start=1):
        kind, lang, unit = spec["kind"], spec["lang"], spec["unit"]
        cols = spec["cols"]
        heads = [_header_text(c, lang, spec["pool"], rng, unit, spec["unit_in_cell"], kind) for c in cols]
        if spec["pool"] == "wild" and unit != "in":                                   # the wild pool still states its unit
            heads = [h if "(" in h or c not in ("width", "height", "sill", "size") else f"{h} ({unit})" for c, h in zip(cols, heads, strict=True)]
        rows = []
        for i in range(spec["n_rows"]):
            tagn = (i + 1) if kind != "rooms" and kind != "finishes" else 101 + i
            tag = f"{TAG_PREFIX[kind]}{tagn}" if kind not in ("rooms", "finishes") else f"{tagn}"
            if kind in ("doors", "windows") and rng.random() < 0.5:
                tag = f"{TAG_PREFIX[kind]}-{tagn}"
            tk = tag_key(tag)
            wmm = rng.choice([800, 900, 1000, 1200, 1500]) if kind == "windows" else rng.choice([800, 900, 1000, 1200])
            hmm = rng.choice([1200, 1500]) if kind == "windows" else rng.choice([2000, 2100, 2400])
            vals = {"tag": tag, "width": wmm, "height": hmm, "sill": rng.choice([600, 900, 1000]),
                    "fire_rating": rng.choice([0, 20, 30, 45, 60, 90, 120]), "quantity": rng.randint(1, 9),
                    "area": round(rng.uniform(8, 40), 1), "ceiling_height": rng.choice([2400, 2500, 2700, 3000]),
                    "power": rng.choice([18, 24, 36, 60]), "voltage": rng.choice([12, 24, 120, 230])}
            for m in TEXTS:
                vals[m] = rng.choice(TEXTS[m][lang])
            if kind == "rooms" or kind == "finishes":
                vals["room_name"] = TEXTS["room_name"][lang][i % 4]
            row = []
            for c in cols:
                v = vals.get(c)
                if c in ("width", "height", "sill", "ceiling_height"):
                    cell = _fmt_len(v, unit, lang, spec["unit_in_cell"])
                    true = round(v / 25.4) * 0.0254 if unit == "in" else v / 1000.0
                    out.truth[(ti, tk, c)] = true
                elif c == "size":
                    cell = f"{_fmt_len(wmm, unit, lang, spec['unit_in_cell'])} x {_fmt_len(hmm, unit, lang, spec['unit_in_cell'])}"
                    if unit == "in":
                        out.truth[(ti, tk, "width")] = round(wmm / 25.4) * 0.0254
                        out.truth[(ti, tk, "height")] = round(hmm / 25.4) * 0.0254
                    else:
                        out.truth[(ti, tk, "width")] = wmm / 1000.0
                        out.truth[(ti, tk, "height")] = hmm / 1000.0
                elif c == "fire_rating":
                    cell = _fire_cell(v, lang)
                    out.truth[(ti, tk, c)] = v * 60.0
                elif c == "area":
                    cell = f"{v}".replace(".", ",") if lang != "en" else f"{v}"
                    if spec["unit_in_cell"]:
                        cell += " m²"
                    out.truth[(ti, tk, c)] = v
                elif c == "tag":
                    cell = tag
                elif c in ("quantity", "power", "voltage"):
                    cell = str(v)
                    out.truth[(ti, tk, c)] = float(v) if c == "quantity" else float(v)
                else:
                    cell = v
                    out.truth[(ti, tk, c)] = str(v).lower()
                row.append(cell)
            rows.append(row)
        widths = [max(len(h) if not spec["two_line_header"] else max(len(p) for p in h.split(' ', 1)), *(len(r[j]) for r in rows)) * fs * 0.6 + 14
                  for j, h in enumerate(heads)]
        x0 = 40.0
        title = TITLES[kind][lang]
        page.insert_text((x0, y), title, fontsize=11, fontname="helv")
        y += 16
        pitch = 15.0
        hdr_lines = 2 if spec["two_line_header"] else 1
        xs = [x0]
        for w in widths:
            xs.append(xs[-1] + w)
        for j, h in enumerate(heads):
            parts = h.split(" ", 1) if spec["two_line_header"] and " " in h else [h]
            if hdr_lines == 2 and len(parts) == 1:
                parts = ["", h]
            for k, part in enumerate(parts):
                if part:
                    page.insert_text((xs[j] + 4, y + 10 + k * pitch * 0.9), part, fontsize=fs, fontname="helv")
        y_head = y + hdr_lines * pitch
        for r, row in enumerate(rows):
            for j, cell in enumerate(row):
                page.insert_text((xs[j] + 4, y_head + 10 + r * pitch), str(cell), fontsize=fs, fontname="helv")
        y_end = y_head + len(rows) * pitch + 4
        if spec["ruled"]:
            for k in range(len(rows) + 2):
                yy = y if k == 0 else (y_head if k == 1 else y_head + (k - 1) * pitch)
                page.draw_line((xs[0], yy), (xs[-1], yy), width=0.6)
            for xx in xs:
                page.draw_line((xx, y), (xx, y_end - 4 + 0.0), width=0.6)
        out.spec.append(spec)
        y = y_end + 40
    doc.save(path)
    doc.close()
    return out
