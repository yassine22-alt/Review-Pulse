import json

import pytest

from reviewpulse.schema import BuildingModel, Finding, SchemaVersionError, load, save


def test_building_model_round_trip(tmp_path):
    import handmade

    m = handmade.build()
    p = save(m, tmp_path / "b.json")
    back = load(BuildingModel, p)
    # JSON is the contract: free-form attrs come back as JSON types (tuples -> lists)
    assert back.model_dump(mode="json") == m.model_dump(mode="json")
    p2 = save(back, tmp_path / "b2.json")
    assert p2.read_text() == p.read_text()


def test_finding_round_trip(tmp_path):
    from reviewpulse.schema import load_findings, save_findings

    f = Finding(rule_id="C-D1", verdict="FAIL", severity="major", subject_ids=["d1"], message="m", tier="T1",
                evidence={"polygons": [[(0, 0), (1, 0), (1, 1)]]})
    save_findings([f], tmp_path / "f.json")
    assert load_findings(tmp_path / "f.json")[0].rule_id == "C-D1"


def test_unknown_major_version_is_refused(tmp_path):
    import handmade

    d = json.loads(handmade.build().model_dump_json())
    d["schema_version"] = "9.0"
    p = tmp_path / "b.json"
    p.write_text(json.dumps(d))
    with pytest.raises(SchemaVersionError):
        load(BuildingModel, p)
