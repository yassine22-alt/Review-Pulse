import pytest

from scripts.grade_blind_sample import agreement


def test_empty_grades_are_not_perfect_agreement():
    assert agreement([]) == {"exact": [0, 0], "kappa": None}


def test_nominal_agreement_has_explicit_denominator_and_no_fake_kappa_for_constant_labels():
    assert agreement([("correct", "correct")]) == {"exact": [1, 1], "kappa": None}
    result = agreement([("correct", "correct"), ("wrong", "correct")])
    assert result["exact"] == [1, 2] and result["kappa"] == pytest.approx(0)


@pytest.mark.parametrize("value,expected", [("correct",False),("partly correct",True),("wrong",False)])
def test_returned_grade_spaces_and_per_column_denominators(tmp_path,value,expected):
    import csv

    from scripts.grade_blind_sample import SLOTS, grade_sheet
    reference={"blind_id":"R1","source":"Example target.","model_output":"proposal",
               "assistant":{slot:"partly_correct" for slot in SLOTS},"whole_rule_grade":"correct"}
    row={"blind_id":"R1","source_clause":"Example target.","model_output":"proposal",
         **{slot+"_grade":"cannot_grade" for slot in (*SLOTS,"whole_rule")},
         "subject_grade":value,"notes":"Independent test","instructions_and_rubric":"Grade source meaning."}
    path=tmp_path/"returned.csv"
    with path.open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    report=grade_sheet(path,{"rows":[reference]})
    assert report["per_slot_agreement"]["subject"]["exact"]==[int(expected),1]
    assert report["completed_cells"]==[7,7]
    assert report["whole_rule_agreement"]["exact"]==[0,0]
