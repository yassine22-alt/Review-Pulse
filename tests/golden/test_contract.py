"""The extraction contract holds on real pipeline output: every element's attrs follow ELEMENT_ATTRS
and every file round-trips through the schema (docs/extraction_schema.md)."""

from pathlib import Path

import pytest

from reviewpulse.eval.cli import _model_from
from reviewpulse.schema import BuildingModel, check_attrs


@pytest.mark.parametrize("fmt", ["dxf", "pdf"])
def test_attrs_contract_template_plan(synth_dir, fmt):
    from reviewpulse.synth.make_plan import make_plan

    p = make_plan(synth_dir, seed=31, png=False, name="contract31")
    m = _model_from(p[fmt])
    assert m.elements and m.rooms
    assert check_attrs(m) == []
    assert BuildingModel.model_validate_json(m.model_dump_json()).model_dump_json() == m.model_dump_json()


@pytest.mark.parametrize("seed", [3, 8])
def test_attrs_contract_random_plan(synth_dir, seed):
    from reviewpulse.synth.random_plan import random_plan

    p = random_plan(synth_dir, seed=seed)
    for fmt in ("dxf", "pdf"):
        assert check_attrs(_model_from(p[fmt])) == []


@pytest.mark.parametrize("fmt", ["dxf", "pdf"])
def test_provenance_is_never_shared(synth_dir, fmt):
    """Evidence is written per object (rule tags, classifier calls): two objects sharing one Prov would
    overwrite each other's. Seed 5005 draws walls as polylines, which the PDF reader splits into lines."""
    from reviewpulse.synth.random_plan import random_plan

    m = _model_from(random_plan(synth_dir, seed=5005)[fmt])
    objs = m.sheet.primitives + m.sheet.texts + m.elements + m.rooms + m.edges
    assert len({id(o.prov) for o in objs}) == len(objs)
    assert len({id(o.prov.evidence) for o in objs}) == len(objs)


@pytest.mark.parametrize("mode", ["rules", "rebuild"])
def test_room_polygons_are_valid(synth_dir, mode, monkeypatch):
    """Stored room outlines (rounded coordinates) stay simple polygons: seed 5043 in the rebuild mode
    gave a self-intersecting room when each vertex was rounded on its own."""
    from shapely.geometry import Polygon

    if mode != "rules":
        from reviewpulse.perception.learned.classifier import available

        if not available():
            pytest.skip("no trained primitive model")
        monkeypatch.setenv("REVIEWPULSE_LEARNED", "1")
        monkeypatch.setenv("REVIEWPULSE_LEARNED_MODE", mode)
    from reviewpulse.synth.random_plan import random_plan

    m = _model_from(random_plan(synth_dir, seed=5043)["dxf"])
    assert m.rooms and all(Polygon(r.polygon, r.holes).is_valid for r in m.rooms)


def test_attrs_contract_learned_pass(synth_dir):
    from reviewpulse.perception.learned.classifier import available

    if not available():
        pytest.skip("no trained primitive model")
    from reviewpulse.annotate.text_classify import classify_items
    from reviewpulse.ingest.dxf_reader import extract_dxf
    from reviewpulse.pipeline import build_model
    from reviewpulse.synth.make_plan import make_plan

    p = make_plan(synth_dir, seed=32, png=False, name="contract32")
    sheet = extract_dxf(Path(p["dxf"]), "contract32")
    classify_items(sheet.texts)
    m = build_model(sheet, learned=True)
    assert check_attrs(m) == []


def test_learned_pass_is_the_default_when_a_model_is_installed(synth_dir, monkeypatch):
    from reviewpulse.perception.learned.classifier import available

    if not available():
        pytest.skip("no trained primitive model")
    from reviewpulse.synth.random_plan import random_plan

    p = random_plan(synth_dir, seed=8)["pdf"]
    monkeypatch.delenv("REVIEWPULSE_LEARNED", raising=False)
    on = _model_from(p)
    monkeypatch.setenv("REVIEWPULSE_LEARNED", "0")
    off = _model_from(p)
    assert "learned primitive classifier applied (second pass)" in on.sheet.warnings
    assert not any("learned primitive classifier" in w for w in off.sheet.warnings)
    assert len(on.rooms) == len(off.rooms)
