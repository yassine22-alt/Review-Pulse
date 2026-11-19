"""Providers differ in small ways: some refuse a script's default signature, some refuse a `seed`. The client copes with both."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from reviewpulse.llm.openai_compat import OpenAICompatClient

SCHEMA = {"type": "object", "properties": {"choice": {"type": "string", "enum": ["a", "b"]}}, "required": ["choice"]}


def _serve(seen: list):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.headers.get("User-Agent"), "seed" in body))
            if "seed" in body:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": {"message": "Unknown name \\"seed\\": Cannot find field."}}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": '{"choice": "b"}'}}], "usage": {}}).encode())

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_a_provider_that_refuses_the_seed_is_asked_again_without_it_and_the_client_names_itself():
    seen: list = []
    server = _serve(seen)
    try:
        client = OpenAICompatClient(f"http://127.0.0.1:{server.server_port}/v1", "k", "m", provider="x", structured="json_object")
        assert client.complete("pick b", "{}", SCHEMA) == {"choice": "b"}
        assert client.complete("pick b", "{}", SCHEMA) == {"choice": "b"}
    finally:
        server.shutdown()
    assert seen[0][1] is True and seen[1][1] is False          # one refusal, then no seed, and never again
    assert len(seen) == 3
    assert all(ua == "reviewpulse-client/1.0" for ua, _ in seen)


def test_the_client_waits_for_the_provider_token_allowance_instead_of_sending_a_call_that_would_be_refused():
    import time

    stamps: list = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            stamps.append(time.monotonic())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("x-ratelimit-remaining-tokens", "10")          # almost nothing left of this minute
            self.send_header("x-ratelimit-reset-tokens", "800ms")
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": '{"choice": "b"}'}}], "usage": {}}).encode())

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = OpenAICompatClient(f"http://127.0.0.1:{server.server_port}/v1", "k", "m", provider="x", structured="json_object", seed=None)
        client.complete("a", "{}", SCHEMA)
        client.complete("b", "{}", SCHEMA)
    finally:
        server.shutdown()
    assert stamps[1] - stamps[0] >= 0.7 and client.usage["waited_s"] > 0.7 and client.usage["errors"] == 0


def test_a_daily_allowance_that_is_used_up_fails_at_once_and_says_so():
    import time

    import pytest

    from reviewpulse.llm.openai_compat import LLMError

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Rate limit reached on tokens per day (TPD): Limit 200000, Used 199274. Try again in 2m."}}')

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = OpenAICompatClient(f"http://127.0.0.1:{server.server_port}/v1", "k", "m", provider="x", structured="json_object")
        t = time.monotonic()
        with pytest.raises(LLMError, match="daily allowance"):
            client.complete("a", "{}", SCHEMA)
    finally:
        server.shutdown()
    assert time.monotonic() - t < 3 and client.usage["daily_exhausted"] and client.usage["errors"] == 1


def test_environment_credentials_and_retry_errors_are_not_recorded(monkeypatch):
    import io
    import urllib.error

    import pytest

    from reviewpulse.llm.openai_compat import APIUnavailable

    monkeypatch.delenv("DRAFT_TEST_KEY", raising=False)
    with pytest.raises(APIUnavailable, match="MISSING_ENV_CREDENTIAL"):
        OpenAICompatClient.from_env("https://provider/v1", "DRAFT_TEST_KEY", "model")
    monkeypatch.setenv("DRAFT_TEST_KEY", "private-test-value")
    client = OpenAICompatClient.from_env("https://provider/v1", "DRAFT_TEST_KEY", "model",
                                         structured="json_object", max_retries=2, seed=None)
    sleeps = []
    monkeypatch.setattr("reviewpulse.llm.openai_compat.time.sleep", sleeps.append)
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("https://provider", 503, "busy", {}, io.BytesIO(b"private-test-value"))
    monkeypatch.setattr("reviewpulse.llm.openai_compat.urllib.request.urlopen", fail)
    with pytest.raises(APIUnavailable) as error:
        client.complete("source", "{}", SCHEMA)
    assert error.value.attempts == 3 and len(sleeps) == 2
    assert 2 <= sleeps[0] <= 4 and 4 <= sleeps[1] <= 8
    assert "private-test-value" not in str(error.value) + json.dumps(client.events) + json.dumps(client.usage)


def test_pacing_reserves_output_tokens_as_well_as_prompt_tokens(monkeypatch):
    clock = [110.0]
    waits = []
    client = OpenAICompatClient("https://provider/v1", None, "model", tpm=1000, max_tokens=400)
    client._token_history = [(100.0, 800)]
    monkeypatch.setattr("reviewpulse.llm.openai_compat.time.monotonic", lambda: clock[0])

    def advance(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr("reviewpulse.llm.openai_compat.time.sleep", advance)
    client._wait_for_tokens(b"{}")
    assert len(waits) == 1 and 50 <= waits[0] < 51
