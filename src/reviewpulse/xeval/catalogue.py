"""A pool of concepts the synthetic documents can talk about.

Nothing here is special to housing or to any project type. Every item draws its own random catalogue
(several collections with their measured properties, plus building-level facts), so an extractor can only
succeed by reading the catalogue it is given. Concepts marked `test` never appear in dev items: scores on
them measure generalisation to things the drafter was not tuned on.
"""

from __future__ import annotations

from dataclasses import dataclass

LEN_SMALL = (0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.1, 1.2, 1.5)


@dataclass(frozen=True)
class Prop:
    name: str                 # fact name suffix
    unit: str                 # m | m2 | count | 1
    en: str                   # "clear width"
    en_pl: str
    fr: str                   # indefinite: "une largeur de passage"
    fr_pl: str                # plural noun: "largeurs de passage"
    grid: tuple               # plausible thresholds, in the canonical unit
    note: str = ""


@dataclass(frozen=True)
class Concept:
    key: str                  # collection id
    en: tuple[str, str]
    fr: tuple[str, str]
    props: tuple[Prop, ...]
    kinds: tuple = ()         # (id, en singular, en plural, fr singular, fr plural)
    split: str = "dev"


def P(name, unit, en, en_pl, fr, fr_pl, grid, note=""):
    return Prop(name, unit, en, en_pl, fr, fr_pl, tuple(grid), note)


WIDTH = lambda: P("width", "m", "clear width", "clear widths", "une largeur de passage", "largeurs de passage", LEN_SMALL)  # noqa: E731

CONCEPTS: tuple[Concept, ...] = (
    Concept("rooms", ("room", "rooms"), ("pièce", "pièces"), (
        P("area", "m2", "floor area", "floor areas", "une surface", "surfaces", (4, 5, 6, 7, 7.5, 9, 10, 12, 14, 16)),
        P("min_width", "m", "minimum width", "minimum widths", "une largeur minimale", "largeurs minimales",
          (1.2, 1.5, 1.8, 2.0, 2.2, 2.4))),
        (("bedroom", "bedroom", "bedrooms", "chambre", "chambres"),
         ("kitchen", "kitchen", "kitchens", "cuisine", "cuisines"),
         ("bathroom", "bathroom", "bathrooms", "salle de bains", "salles de bains"),
         ("office", "office", "offices", "bureau", "bureaux"),
         ("corridor", "corridor", "corridors", "couloir", "couloirs"))),
    Concept("doors", ("door", "doors"), ("porte", "portes"), (
        WIDTH(), P("height", "m", "clear height", "clear heights", "une hauteur de passage", "hauteurs de passage",
                   (1.9, 2.0, 2.04, 2.1))),
        (("internal", "internal door", "internal doors", "porte intérieure", "portes intérieures"),
         ("external", "external door", "external doors", "porte extérieure", "portes extérieures"),
         ("fire", "fire door", "fire doors", "porte coupe-feu", "portes coupe-feu"))),
    Concept("windows", ("window", "windows"), ("fenêtre", "fenêtres"), (
        P("width", "m", "width", "widths", "une largeur", "largeurs", (0.5, 0.6, 0.8, 1.0, 1.2)),
        P("sill", "m", "sill height", "sill heights", "une hauteur d'allège", "hauteurs d'allège",
          (0.8, 0.9, 1.0, 1.1))),
        (("fixed", "fixed window", "fixed windows", "fenêtre fixe", "fenêtres fixes"),
         ("opening", "opening window", "opening windows", "fenêtre ouvrante", "fenêtres ouvrantes"))),
    Concept("stairs", ("stair", "stairs"), ("escalier", "escaliers"), (
        P("riser", "m", "riser height", "riser heights", "une hauteur de marche", "hauteurs de marche",
          (0.15, 0.16, 0.17, 0.18, 0.19)),
        P("tread", "m", "tread depth", "tread depths", "un giron", "girons", (0.25, 0.26, 0.28, 0.30)),
        P("width", "m", "clear width", "clear widths", "une largeur utile", "largeurs utiles", (0.9, 1.0, 1.2, 1.5))),
        (("internal", "internal stair", "internal stairs", "escalier intérieur", "escaliers intérieurs"),
         ("external", "external stair", "external stairs", "escalier extérieur", "escaliers extérieurs"),
         ("escape", "escape stair", "escape stairs", "escalier de secours", "escaliers de secours"))),
    Concept("ramps", ("ramp", "ramps"), ("rampe", "rampes"), (
        P("slope", "1", "slope", "slopes", "une pente", "pentes", (0.05, 0.06, 0.08, 0.10, 0.12)),
        P("width", "m", "clear width", "clear widths", "une largeur utile", "largeurs utiles", (0.9, 1.2, 1.5)),
        P("length", "m", "length", "lengths", "une longueur", "longueurs", (5, 6, 8, 10, 12))), ()),
    Concept("bays", ("parking bay", "parking bays"), ("place de stationnement", "places de stationnement"), (
        P("width", "m", "width", "widths", "une largeur", "largeurs", (2.3, 2.5, 2.7, 3.3)),
        P("length", "m", "length", "lengths", "une longueur", "longueurs", (4.8, 5.0, 5.5))),
        (("standard", "standard bay", "standard bays", "place standard", "places standard"),
         ("accessible", "accessible bay", "accessible bays", "place accessible", "places accessibles"))),
    Concept("exits", ("exit", "exits"), ("issue", "issues"), (
        P("width", "m", "clear width", "clear widths", "une largeur de passage", "largeurs de passage",
          (0.9, 1.2, 1.4, 1.8)),
        P("capacity", "count", "capacity", "capacities", "une capacité", "capacités", (50, 100, 150, 200),
          "persons")),
        (("final", "final exit", "final exits", "issue finale", "issues finales"),
         ("emergency", "emergency exit", "emergency exits", "issue de secours", "issues de secours"))),
    # held out from dev items entirely
    Concept("lifts", ("lift", "lifts"), ("ascenseur", "ascenseurs"), (
        P("car_area", "m2", "car floor area", "car floor areas", "une surface de cabine", "surfaces de cabine",
          (1.1, 1.4, 2.0, 2.5)),
        P("door_width", "m", "door width", "door widths", "une largeur de porte", "largeurs de porte",
          (0.8, 0.9, 1.0, 1.1))), (), "test"),
    Concept("beams", ("beam", "beams"), ("poutre", "poutres"), (
        P("span", "m", "span", "spans", "une portée", "portées", (3, 4, 5, 6, 8)),
        P("depth", "m", "depth", "depths", "une hauteur", "hauteurs", (0.2, 0.3, 0.4, 0.5))),
        (("timber", "timber beam", "timber beams", "poutre en bois", "poutres en bois"),
         ("steel", "steel beam", "steel beams", "poutre en acier", "poutres en acier")), "test"),
    Concept("ducts", ("duct", "ducts"), ("gaine", "gaines"), (
        P("diameter", "m", "diameter", "diameters", "un diamètre", "diamètres", (0.1, 0.125, 0.16, 0.2, 0.25)),
        P("length", "m", "length", "lengths", "une longueur", "longueurs", (2, 5, 10, 20))),
        (("supply", "supply duct", "supply ducts", "gaine de soufflage", "gaines de soufflage"),
         ("extract", "extract duct", "extract ducts", "gaine d'extraction", "gaines d'extraction")), "test"),
    Concept("guards", ("guardrail", "guardrails"), ("garde-corps", "garde-corps"), (
        P("height", "m", "height", "heights", "une hauteur", "hauteurs", (0.9, 1.0, 1.1, 1.2)),), (), "test"),
    Concept("compartments", ("fire compartment", "fire compartments"), ("compartiment", "compartiments"), (
        P("area", "m2", "floor area", "floor areas", "une surface", "surfaces", (250, 500, 1000, 2000)),
        P("occupants", "count", "occupant load", "occupant loads", "un effectif", "effectifs", (50, 100, 300, 500),
          "persons")), (), "test"),
)


@dataclass(frozen=True)
class BuildingFact:
    name: str
    unit: str
    description: str
    grid: tuple
    cond: tuple               # (en, fr) templates for "applies where fact is greater than {v}"
    exempt: tuple             # (en, fr) templates for "except where fact is at most {v}"


BUILDING_FACTS: tuple[BuildingFact, ...] = (
    BuildingFact("storeys", "count", "Number of storeys of the building", (1, 2, 3, 4, 5),
                 ("In buildings with more than {v} storeys, ", "Dans les bâtiments de plus de {v} niveaux, "),
                 ("except in buildings of {v} storeys or fewer", "sauf dans les bâtiments de {v} niveaux ou moins")),
    BuildingFact("occupants", "count", "Number of occupants of the building", (10, 20, 50, 100, 200),
                 ("Where the number of occupants exceeds {v}, ", "Lorsque le nombre d'occupants dépasse {v}, "),
                 ("except where the number of occupants is {v} or fewer",
                  "sauf lorsque le nombre d'occupants est de {v} ou moins")),
    BuildingFact("building_height", "m", "Height of the building", (8, 12, 18, 28, 50),
                 ("In buildings taller than {v}, ", "Dans les bâtiments de plus de {v} de hauteur, "),
                 ("except in buildings no taller than {v}", "sauf dans les bâtiments d'au plus {v} de hauteur")),
    BuildingFact("gross_area", "m2", "Total floor area of the building", (100, 300, 1000, 2500),
                 ("In buildings with a floor area greater than {v}, ", "Dans les bâtiments de plus de {v} de surface, "),
                 ("except in buildings of {v} or less", "sauf dans les bâtiments de {v} ou moins")),
)


def fact_name(concept: Concept, prop: Prop) -> str:
    return f"{concept.key}_{prop.name}"


def kind_name(concept: Concept) -> str:
    return f"{concept.key}_kind"


def pools(split: str) -> list[Concept]:
    """`dev` draws from dev concepts only; `test` draws from all, always including a held-out concept."""
    return [c for c in CONCEPTS if split == "test" or c.split == "dev"]
