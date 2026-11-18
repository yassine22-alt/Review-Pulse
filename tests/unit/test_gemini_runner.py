import io
import json
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import pytest

from reviewpulse.llm.gemini import APIUnavailable, GeminiClient
from reviewpulse.llm.result_cache import ResultCache, fingerprint

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
ANSWER = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"ok":true}'}]}}]}


def test_missing_environment_does_not_make_requests(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(APIUnavailable, match="MISSING_ENV_CREDENTIAL") as error:
        GeminiClient()
    assert error.value.attempts == 0


@pytest.mark.parametrize("status", [429, 503])
def test_retry_backoff_redaction_and_circuit(monkeypatch, status):
    monkeypatch.setenv("GEMINI_API_KEY", "temporary-test-credential")
    client = GeminiClient(max_attempts=3)
    sleeps = []
    monkeypatch.setattr("reviewpulse.llm.gemini.time.sleep", sleeps.append)
    calls = []

    def fail(payload):
        calls.append(payload)
        raise urllib.error.HTTPError("https://provider", status, "busy", {},
                                     io.BytesIO(b"temporary-test-credential"))

    monkeypatch.setattr(client, "_request", fail)
    with pytest.raises(APIUnavailable) as error:
        client.complete("system", "source", SCHEMA)
    assert len(calls) == 3 and len(sleeps) == 2
    assert 2 <= sleeps[0] <= 4 and 4 <= sleeps[1] <= 8
    assert "temporary-test-credential" not in str(error.value) + json.dumps(client.events)
    with pytest.raises(APIUnavailable, match="CIRCUIT_OPEN"):
        client.complete("system", "source", SCHEMA)
    assert len(calls) == 3


def test_concurrency_limit_and_schema_payload(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "temporary-test-credential")
    client = GeminiClient(concurrency=1)
    active = maximum = 0
    lock = threading.Lock()

    def respond(payload):
        nonlocal active, maximum
        assert payload["generationConfig"]["responseJsonSchema"] == SCHEMA
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return ANSWER

    monkeypatch.setattr(client, "_request", respond)
    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(lambda _: client.complete("system", "source", SCHEMA), range(4)))
    assert results == [{"ok": True}] * 4 and maximum == 1


def test_cache_resumes_and_invalidates_changed_configuration(tmp_path):
    cache = ResultCache(tmp_path)
    key = fingerprint({"clause": "source", "model": "model", "code": "version"})
    cache.put(key, {"status": "NEEDS_REVIEW", "stage": "units"})
    assert ResultCache(tmp_path).get(key)["stage"] == "units"
    assert cache.get(fingerprint({"clause": "source", "model": "different", "code": "version"})) is None
    cache.put(key, {"status": "API_UNAVAILABLE"})
    assert cache.get(key)["status"] == "NEEDS_REVIEW"
    missing = fingerprint({"clause": "not completed"})
    cache.put(missing, {"status": "API_UNAVAILABLE"})
    assert cache.get(missing) is None
    (tmp_path / f"{key}.json").write_text("[]")
    assert cache.get(key) is None
def test_hosted_schema_bounds_are_removed_without_mutating_validator_schema():
    from reviewpulse.llm.gemini import decoding_schema

    schema = {"type": "array", "maxItems": 64, "minItems": 1,
              "items": {"type": "object", "properties": {"values": {
                  "type": "array", "maxItems": 8, "items": {"type": "number"}}}}}
    converted = decoding_schema(schema)
    assert "maxItems" not in converted and "minItems" not in converted
    assert "maxItems" not in converted["items"]["properties"]["values"]
    assert schema["maxItems"] == 64
    named_property = {"type": "object", "properties": {"maxItems": {"type": "integer"}}}
    assert decoding_schema(named_property) == named_property
