import time

import pytest

from reviewpulse.llm.gemini import APIUnavailable, GeminiClient
from scripts.run_development_drafting import RequestGate


def test_request_gate_paces_attempts_and_counts_failed_requests(monkeypatch):
    clock, attempts = [0.0], []
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    class Client:
        unavailable = False

        def _request(self, payload):
            attempts.append(clock[0])
            if len(attempts) == 1:
                raise TimeoutError
            return {"ok": True}

    client = Client()
    gate = RequestGate(client, APIUnavailable, budget=2, interval=13)
    with pytest.raises(TimeoutError):
        gate({})
    clock[0] = 2.0  # Retry backoff is part of the spacing, not an extra 13 seconds.
    assert gate({}) == {"ok": True}
    assert attempts == [0.0, 13.0]
    with pytest.raises(APIUnavailable) as error:
        gate({})
    assert error.value.reason == "REQUEST_BUDGET_EXHAUSTED"
    assert client.unavailable and len(attempts) == 2
    client.unavailable = False  # Starting a new retry cycle must not reset the allowance.
    with pytest.raises(APIUnavailable, match="REQUEST_BUDGET_EXHAUSTED"):
        gate({})
    assert len(attempts) == 2


def test_budget_exhaustion_is_not_a_fabricated_http_failure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "temporary-test-credential")
    client = GeminiClient()
    monkeypatch.setattr(client, "_request", lambda _: {
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"ok":true}'}]}}]})
    client._request = RequestGate(client, APIUnavailable, budget=1)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    assert client.complete("instruction", "source", schema) == {"ok": True}
    with pytest.raises(APIUnavailable, match="REQUEST_BUDGET_EXHAUSTED"):
        client.complete("instruction", "source", schema)
    assert client.unavailable
    assert [event["http_status"] for event in client.events] == [200]
