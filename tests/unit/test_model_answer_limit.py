"""A model answer that never ends is cut off and said so; a failing server is not called unreachable."""

import io
import urllib.error
from types import SimpleNamespace

import pytest

from reviewpulse.rules.draft import MAX_ANSWER_TOKENS, OllamaClient
from reviewpulse.xeval.status import clause_status


def test_every_request_limits_the_answer_and_a_cut_off_answer_is_an_error(monkeypatch):
    sent = []

    def post(self, path, body):
        sent.append(body)
        return {"done_reason": "length", "message": {"content": '{"require": "a or a or a or'}}

    monkeypatch.setattr(OllamaClient, "_post", post)
    with pytest.raises(RuntimeError, match="answer did not end") as err:
        OllamaClient().complete("s", "u", {})
    assert sent[0]["options"]["num_predict"] == MAX_ANSWER_TOKENS
    status, reason = clause_status(SimpleNamespace(program=None, raw={}, detail=str(err.value), stage="call"))
    assert status == "UNRESOLVED" and "ran on without ending" in reason and "could not be reached" not in reason


def test_a_server_error_is_not_reported_as_an_unreachable_server(monkeypatch):
    def fail(*_a, **_k):
        raise urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO())

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(RuntimeError) as err:
        OllamaClient().complete("s", "u", {})
    assert "failed on this request" in str(err.value) and "not reachable" not in str(err.value)
