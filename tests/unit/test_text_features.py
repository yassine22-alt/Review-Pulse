"""Text-context features of the primitive classifier: known distances and counts on a tiny sheet."""

import numpy as np
import pytest

from reviewpulse.perception.learned.features import FEATURES, TEXT_FAR_M, sheet_features
from reviewpulse.schema import BuildingModel, Primitive, Prov, Scale, Sheet, TextItem

P = Prov(source="vector", stage="test")


def _line(id_, a, b):
    return Primitive(id=id_, kind="line", pts=[a, b], prov=P)


def _text(id_, text, kind, box):
    return TextItem(id=id_, text=text, bbox=box, kind=kind, prov=P)


def test_text_context_features():
    sheet = Sheet(id="t", source_file="t", mode="vector", coord_unit="drawing_unit", width=30, height=30,
                  scale=Scale(metres_per_unit=1.0, method="user", confidence=1.0),
                  primitives=[_line("near_dim", (0, 0), (4, 0)), _line("near_tag", (10, 0), (11, 0)),
                              _line("far", (25, 25), (29, 25)), _line("in_box", (0.2, 10.5), (1.8, 10.5))],
                  texts=[_text("d", "3,40", "dimension", (1.0, 0.3, 2.0, 0.6)),
                         _text("g", "P4", "tag", (10.2, 0.5, 10.6, 0.8)),
                         _text("n", "NOTE", "note", (0.0, 10.0, 2.0, 11.0))])
    ids, X = sheet_features(BuildingModel(sheet=sheet))
    f = {i: dict(zip(FEATURES, row)) for i, row in zip(ids, X)}
    assert f["near_dim"]["txt_dist_m"] == pytest.approx(0.3) and f["near_dim"]["txt_dim_1m"] == 1
    assert f["near_tag"]["txt_tag_1m"] == 1 and f["near_tag"]["txt_dim_1m"] == 0
    assert f["far"]["txt_dist_m"] == TEXT_FAR_M and all(f["far"][k] == 0 for k in ("txt_dim_1m", "txt_tag_1m"))
    assert f["in_box"]["txt_inside"] == 1 and f["in_box"]["txt_note_1m"] == 1


def test_no_text_gives_neutral_values():
    sheet = Sheet(id="t", source_file="t", mode="vector", coord_unit="drawing_unit", width=10, height=10,
                  scale=Scale(metres_per_unit=1.0, method="user", confidence=1.0),
                  primitives=[_line("a", (0, 0), (4, 0))])
    _ids, X = sheet_features(BuildingModel(sheet=sheet))
    row = dict(zip(FEATURES, X[0]))
    assert row["txt_dist_m"] == TEXT_FAR_M and np.isclose(sum(row[k] for k in FEATURES if k.startswith("txt_")), TEXT_FAR_M)
