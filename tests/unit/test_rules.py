import pytest

from reviewpulse.rules.registry import REGISTRY, resolve
from reviewpulse.rules.schema import Rule, RuleError, dump_rule, load_rule


def test_every_registered_function_is_implemented():
    for name in REGISTRY:
        assert callable(resolve(name)), name


def test_starter_pack_loads_and_is_approved(pack):
    """Every starter rule is approved, except templates: drafts that name no source document and
    wait to be approved from a project's own regulation (C-T6: not a rule for dwellings)."""
    assert len(pack) >= 20
    templates = [r for r in pack if r.status == "draft"]
    assert all(r.source.doc.startswith("none (template)") for r in templates)
    assert all(r.status == "approved" for r in pack if r not in templates)


def test_metric_functions_imply_scale(pack):
    for r in pack:
        if REGISTRY[r.check.fn].needs_scale:
            assert "scale" in r.needs, r.id


BASE = {"id": "X-1", "title": "t", "family": "C", "class": "threshold", "applies_to": {"room_type": ["bedroom"]},
        "check": {"fn": "area_m2", "op": ">=", "value": 9, "unit": "m2"}, "severity": "major", "needs": [],
        "source": {"doc": "d"}, "message": "m"}


def test_unknown_room_type_is_rejected():
    with pytest.raises(ValueError, match="unknown room type"):
        Rule.model_validate({**BASE, "applies_to": {"room_type": ["dungeon"]}})


def test_unknown_function_is_rejected():
    with pytest.raises(ValueError, match="registry"):
        Rule.model_validate({**BASE, "check": {"fn": "ask_llm"}})


def test_rule_yaml_round_trip(tmp_path):
    r = Rule.model_validate(BASE)
    p = tmp_path / "r.yaml"
    p.write_text(dump_rule(r))
    again = load_rule(p)[0]
    assert again == r
    assert dump_rule(again) == dump_rule(r)


def test_bad_file_names_rule_in_error(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("id: BAD\ntitle: x\n")
    with pytest.raises(RuleError, match="BAD"):
        load_rule(p)
