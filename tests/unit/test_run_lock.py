import pytest

from reviewpulse.llm.result_cache import exclusive_run


def test_same_report_cannot_be_resumed_by_two_workers_and_lock_releases(tmp_path):
    path = tmp_path / "run.json"
    with exclusive_run(path):
        with pytest.raises(RuntimeError, match="running worker"), exclusive_run(path):
            pytest.fail("second worker entered")
    with exclusive_run(path):
        pass
