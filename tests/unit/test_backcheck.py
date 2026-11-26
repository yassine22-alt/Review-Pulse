"""The back check: an unchanged set has no changes, and planted resubmissions get the status their edit calls for."""

import pymupdf

from reviewpulse.backcheck import back_check
from reviewpulse.backcheck.model import RESOLVED
from reviewpulse.backcheck.synthpairs import make_cases


def _stacked_lines(path):
    """Real CAD exports draw the same line many times in one place."""
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    for _ in range(12):
        page.draw_line((100, 200), (220, 200))
        page.draw_rect(pymupdf.Rect(300, 100, 300.2, 104))
    for k in range(30):
        page.insert_text((60, 40 + 11 * k), f"GENERAL NOTE {k} VERIFY ON SITE", fontsize=8)
    doc.save(path)
    doc.close()


def test_a_set_against_itself_has_no_changes(tmp_path):
    pdf = tmp_path / "stacked.pdf"
    _stacked_lines(pdf)
    res = back_check(pdf, pdf, [])
    assert res.regions == []
    assert res.new_issues == []


def test_planted_resubmissions_get_the_expected_status(tmp_path):
    wrong, false_resolved = [], []
    for case in make_cases(tmp_path, seeds=(12,)):
        res = back_check(case.old, case.new, case.comments)
        for v in res.verdicts:
            want = case.expect.get(v.comment.id)
            if want and v.status != want:
                wrong.append((case.name, v.comment.id, want, v.status))
                if v.status == RESOLVED:
                    false_resolved.append((case.name, v.comment.id))
    assert false_resolved == []
    assert wrong == []
