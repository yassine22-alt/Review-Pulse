import pytest

from reviewpulse.xeval.drafters import BoundedOllama


def test_cap_keeps_raw_response_and_next_request_clears_stale_diagnostics(monkeypatch):
    client = BoundedOllama(num_predict=100)
    text = '{"nodes":['
    monkeypatch.setattr(client, "_post", lambda *_: {
        "done_reason": "length", "eval_count": 100, "prompt_eval_count": 25,
        "message": {"content": text}})
    with pytest.raises(RuntimeError, match="cap"):
        client.complete("instruction", "source", {})
    assert client.last["text"] == text
    assert client.last["done"] == "length"

    def fail(*_):
        raise TimeoutError

    monkeypatch.setattr(client, "_post", fail)
    with pytest.raises(TimeoutError):
        client.complete("instruction", "source", {})
    assert client.last == {}
