import json

import pytest

from reviewpulse.llm.recording import record_calls


def test_response_capture_excludes_credentials_and_request_text(tmp_path):
    class Client:
        model = "fixture"
        case_id = "sample"
        _key = "synthetic-never-record-this"
        last = {}

        def complete(self, *_):
            return {"subject": "synthetic subject"}

    client = record_calls(Client(), tmp_path)
    assert client.complete("private instruction", "private request", {"properties": {"subject": {}}})
    text = next(tmp_path.glob("*.json")).read_text()
    assert "synthetic-never-record-this" not in text
    assert "private instruction" not in text and "private request" not in text
    assert json.loads(text)["response"]["subject"] == "synthetic subject"


def test_failed_response_never_reuses_a_previous_draft(tmp_path):
    class Client:
        model = "fixture"
        case_id = "sample"
        last = {"text": "old response"}

        def complete(self, *_):
            raise TimeoutError("must not record exception text")

    client = record_calls(Client(), tmp_path)
    with pytest.raises(TimeoutError):
        client.complete("", "", {})
    saved = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert saved["response"] is None and saved["text"] is None
    assert saved["error_type"] == "TimeoutError"
