from reviewpulse.xeval.expression_normalization import normalize_expressions


def catalogue():
    return {"whole": "building", "building": ["clear_width", "enabled"],
            "collections": {"items": {"facts": ["width"]}}}


def test_only_unambiguous_global_qualification_and_surface_comparators_are_changed():
    raw = {"require": "clear_width ≥ 0.8 m and enabled eq true", "unless": None}
    result, trace = normalize_expressions(raw, catalogue())
    assert result["require"] == "building.clear_width >= 0.8 m and building.enabled == true"
    assert raw["require"].startswith("clear_width")
    assert trace[0]["before"] == raw["require"]
    assert trace[0]["after"] == result["require"]
    assert normalize_expressions(result, catalogue()) == (result, [])


def test_literals_unknown_fact_names_missing_scope_and_collection_binding_stay_opaque():
    raw = {"require": 'width >= 2 and other_width >= 1 and building.note == "clear_width ≥ enabled"'}
    assert normalize_expressions(raw, catalogue()) == (raw, [])


def test_does_not_invent_quantifiers_or_change_bound_variable_to_global_entity():
    raw = {"require": "forall items enabled: enabled.width >= 1 m"}
    assert normalize_expressions(raw, catalogue()) == (raw, [])


def test_only_a_complete_outer_code_fence_is_removed():
    raw = {"require": "```expression\nbuilding.clear_width <= 1 m\n```"}
    result, trace = normalize_expressions(raw, catalogue())
    assert result["require"] == "building.clear_width <= 1 m"
    assert trace[0]["operations"] == ["outer_code_fence"]
    incomplete = {"require": "```expression\nbuilding.clear_width <= 1 m"}
    assert normalize_expressions(incomplete, catalogue()) == (incomplete, [])
