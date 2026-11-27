"""Where the local model server is.

On Windows the name "localhost" resolves to the IPv6 address first, while a local model server (Ollama by default) listens on
the IPv4 one only: every request waits about two seconds for the first address to fail before the second is tried. Measured
here: 2.10 s a call by name against 0.05 s by address, for work the server did in 0.05 s. So the name is replaced by the
IPv4 address before anything connects. An address a person set on purpose, any other host, is left as it is."""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

DEFAULT = "http://127.0.0.1:11434"
# "0.0.0.0" is how a server is told to listen everywhere; it is not an address a client can rely on connecting to
BY_NAME = {"localhost", "0.0.0.0"}


def direct(url: str) -> str:
    """The same URL with "localhost" (or "0.0.0.0") written as 127.0.0.1; everything else unchanged."""
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in BY_NAME:
        return url
    login, at, place = parts.netloc.rpartition("@")
    port = place.rpartition(":")[2] if ":" in place else ""
    return urlunsplit(parts._replace(netloc=f"{login}{at}127.0.0.1{':' + port if port else ''}"))


def ollama_host(host: str | None = None) -> str:
    """The address of the Ollama server: given, else OLLAMA_HOST, else this machine. A bare "host:port" gets "http://"."""
    value = (host or os.environ.get("OLLAMA_HOST") or DEFAULT).strip().rstrip("/")
    if "://" not in value:
        value = "http://" + value
    return direct(value)
