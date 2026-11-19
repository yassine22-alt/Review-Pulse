import pytest

from reviewpulse.xeval.edit_burden import distribution, edit_bucket


def test_scope_bounds_count_separately_but_wholesale_logic_replacement_is_rewrite():
    edits = [{"operation": "add_scope_condition", "site": "lower"}, {"operation": "add_scope_condition", "site": "upper"}]
    assert edit_bucket(edits) == "2+"
    assert edit_bucket([{"operation": "rewrite", "site": "root"}]) == "rewrite"
    assert edit_bucket([], complete=False) == "needs_context"
    assert distribution([{"edits": []}, {"edits": edits}])["0"] == [1, 2]


def test_duplicate_edit_sites_cannot_inflate_burden():
    with pytest.raises(ValueError, match="duplicate"):
        edit_bucket([{"operation": "add_unit", "site": "value"}] * 2)
