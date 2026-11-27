"""A local model server is addressed by number: by name, Windows waits about two seconds on every call (measured)."""

import pytest

from reviewpulse.llm.local import direct, ollama_host
from reviewpulse.llm.openai_compat import OpenAICompatClient


@pytest.mark.parametrize(("given", "used"), [
    ("http://localhost:11434", "http://127.0.0.1:11434"),
    ("http://LocalHost:11434/v1", "http://127.0.0.1:11434/v1"),
    ("http://0.0.0.0:11434", "http://127.0.0.1:11434"),
    ("http://user:pw@localhost:8000/v1", "http://user:pw@127.0.0.1:8000/v1"),
    ("http://localhost", "http://127.0.0.1"),
    ("http://gpu-box.local:11434", "http://gpu-box.local:11434"),
    ("http://[::1]:11434", "http://[::1]:11434"),                       # set on purpose: left alone
    ("https://api.example.com/v1", "https://api.example.com/v1"),
    ("http://localhost.example.com", "http://localhost.example.com"),
])
def test_only_the_name_of_this_machine_is_rewritten(given, used):
    assert direct(given) == used


def test_the_ollama_address_comes_from_the_argument_the_setting_or_this_machine(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert ollama_host() == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "localhost:11500/")
    assert ollama_host() == "http://127.0.0.1:11500"
    assert ollama_host("http://10.0.0.4:11434") == "http://10.0.0.4:11434"


def test_the_compatible_client_connects_by_number_and_stays_local():
    client = OpenAICompatClient("http://localhost:11434/v1", None, "m")
    assert client.base_url == "http://127.0.0.1:11434/v1" and not client.external
