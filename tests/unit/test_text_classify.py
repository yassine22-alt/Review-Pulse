import pytest

from reviewpulse.annotate.text_classify import classify, match_room, tag_key

CASES = [
    # text, kind, value, unit, norm
    ("12,50 m²", "area", 12.5, "m2", None),
    ("9.2 m2", "area", 9.2, "m2", None),
    ("3,60", "dimension", 3.6, "m", None),
    ("3600", "dimension", 3600, "mm", None),
    ("360", "dimension", 360, None, None),
    ("90 cm", "dimension", 90, "cm", None),
    ("P1", "tag", None, None, "P1"),
    ("F 12", "tag", None, None, "F12"),
    ("d-3", "tag", None, None, "D3"),
    ("CHAMBRE 2", "room_label", None, None, "bedroom"),
    ("Chambre l", "room_label", None, None, "bedroom"),
    ("Ch.", "room_label", None, None, "bedroom"),
    ("Séjour", "room_label", None, None, "living"),
    ("Séjour/Salon", "room_label", None, None, "living"),
    ("SALLE DE BAIN", "room_label", None, None, "bathroom"),
    ("S.D.B", "room_label", None, None, "bathroom"),
    ("Salle d'eau", "room_label", None, None, "bathroom"),
    ("W.C.", "room_label", None, None, "wc"),
    ("Toilettes", "room_label", None, None, "wc"),
    ("CUISINE", "room_label", None, None, "kitchen"),
    ("Kitchen", "room_label", None, None, "kitchen"),
    ("Dégagement", "room_label", None, None, "corridor"),
    ("HALL", "room_label", None, None, "corridor"),
    ("Entrée", "room_label", None, None, "entry"),
    ("GARAGE", "room_label", None, None, "garage"),
    ("Cellier", "room_label", None, None, "storage"),
    ("Escalier", "room_label", None, None, "stairs"),
    ("Terrasse", "room_label", None, None, "terrace"),
    ("BUREAU", "room_label", None, None, "office"),
    ("Living room", "room_label", None, None, "living"),
    ("Bedroom 3", "room_label", None, None, "bedroom"),
    ("ECHELLE 1:100", "title_block", None, None, "scale"),
    ("Date : 24/10/2026", "title_block", None, None, "date"),
    ("Indice B", "title_block", None, None, "revision"),
    ("PLAN DU REZ-DE-CHAUSSEE", "title_block", None, None, "title"),
    ("Voir détail 3", "note", None, None, None),
    ("Attention: poutre", "note", None, None, None),
    ("", "note", None, None, None),
]


@pytest.mark.parametrize("text,kind,value,unit,norm", CASES)
def test_classify(text, kind, value, unit, norm):
    c = classify(text)
    assert c.kind == kind
    if value is not None:
        assert c.value == pytest.approx(value)
    assert c.unit == unit
    if norm is not None:
        assert c.norm == norm


def test_unknown_strings_are_notes():
    assert classify("lorem ipsum dolor").kind == "note"
    assert match_room("nothing here") is None


@pytest.mark.parametrize("raw,key", [("P-1", "P1"), ("p1", "P1"), ("P 01", "P1"), ("F12", "F12")])
def test_tag_key(raw, key):
    assert tag_key(raw) == key
