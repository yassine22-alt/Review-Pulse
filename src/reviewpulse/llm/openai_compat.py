"""A client for any OpenAI-compatible chat endpoint: Groq, OpenRouter, Cloudflare, Gemini's compatibility layer, Mistral,
vLLM, LM Studio, or a company gateway. One implementation, so a provider is configuration, not code.

What it does that a bare HTTP call does not, because the drafting pipeline depends on it:

  structured output    asks for a JSON schema first ("json_schema", strict); if the provider or model refuses that, falls
                       back to "json_object" with the schema written into the prompt, then to plain text; the answer is
                       parsed leniently (code fences, text around the object). The pipeline validates everything anyway,
                       so a looser mode costs a repair, never a wrong rule.
  rate limits          honours Retry-After on 429, backs off on 5xx and timeouts, and paces requests (`rpm`) so a free tier's
                       per-minute cap is respected instead of hit.
  privacy              `external` says whether the endpoint is outside this machine and local network; callers use it to
                       decide what may be sent. The API key is never written to an error message or a log.
  accounting           every call records tokens and seconds in `last` and `usage`.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


class LLMError(RuntimeError):
    """A failure with a message that is safe to show a user (never contains the API key)."""


def is_external(base_url: str) -> bool:
    """True unless the endpoint is this machine or a private network address."""
    host = (urlparse(base_url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "host.docker.internal") or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_loopback or ip.is_private)
    except ValueError:
        return True


def extract_json(text: str) -> dict:
    """The JSON object in a model's text: whole, inside a code fence, or the first balanced {...} in prose."""
    text = (text or "").strip()
    for candidate in (text, *re.findall(r"```(?:json)?\s*(.*?)```", text, re.S)):
        try:
            value = json.loads(candidate.strip())
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            depth += (text[i] == "{") - (text[i] == "}")
            if depth == 0:
                try:
                    value = json.loads(text[start:i + 1])
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    break
        start = text.find("{", start + 1)
    raise LLMError("the model did not return a JSON object")


def _strict(schema: dict) -> dict | None:
    """The schema in the form strict structured output accepts, or None when it cannot be expressed that way."""
    def fix(node):
        if isinstance(node, dict):
            if "$ref" in node or "anyOf" in node and any(isinstance(a, dict) and "$ref" in a for a in node["anyOf"]):
                raise ValueError("references are not portable")
            out = {k: fix(v) for k, v in node.items() if k not in ("title", "default", "description", "examples")}
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"])
            return out
        if isinstance(node, list):
            return [fix(x) for x in node]
        return node
    try:
        return fix(schema)
    except ValueError:
        return None


def _first_sentence(text: str) -> str:
    import re

    m = re.search(r'"message":"([^"]{0,200})', text)
    return (m.group(1) if m else text[:200]).strip()


def _seconds(text: str) -> float:
    """"577ms", "1.5s", "2m3.2s" -> seconds."""
    import re

    units = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return sum(float(n) * units[u] for n, u in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", text))


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str | None, model: str, *, provider: str = "custom",
                 structured: str = "auto", timeout_s: float = 120.0, max_retries: int = 4, rpm: float | None = None,
                 temperature: float = 0.0, max_tokens: int = 3000, seed: int | None = 42, headers: dict | None = None,
                 reasoning_effort: str | None = None):
        if not model:
            raise LLMError("a model name is required (set REVIEWPULSE_LLM_MODEL)")
        self.base_url = base_url.rstrip("/")
        self.model, self.provider = model, provider
        self.external = is_external(self.base_url)
        self.structured = structured                       # auto | json_schema | json_object | text
        self.timeout_s, self.max_retries = timeout_s, max_retries
        self.temperature, self.max_tokens, self.seed = temperature, max_tokens, seed
        self.reasoning_effort = reasoning_effort
        self._key = api_key
        self._headers = headers or {}
        self._min_interval = 60.0 / rpm if rpm else 0.0
        self._lock, self._next_at = threading.Lock(), 0.0
        self._mode: str | None = None if structured == "auto" else structured
        self.last: dict = {}
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0, "errors": 0, "waited_s": 0.0}
        self._tokens_left: float | None = None             # what the provider says is left of this minute's token allowance
        self._tokens_reset = 0.0                           # when it is full again (monotonic seconds)

    # -- transport --------------------------------------------------------------------------------------------------
    def _pace(self) -> None:
        if not self._min_interval:
            return
        with self._lock:
            wait = self._next_at - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._next_at = time.monotonic() + self._min_interval

    def _wait_for_tokens(self, data: bytes) -> None:
        """Free tiers cap tokens per minute, not only requests. The provider reports what is left in its response headers
        (x-ratelimit-remaining-tokens, x-ratelimit-reset-tokens); a call that would not fit waits for the reset instead of being sent,
        refused with a 429 and retried, which spends the same minute twice."""
        if self._tokens_left is None:
            return
        need = len(data) / 3.0 + 200
        wait = self._tokens_reset - time.monotonic()
        if self._tokens_left < need and wait > 0:
            time.sleep(min(wait + 0.25, 65.0))
            self.usage["waited_s"] += min(wait + 0.25, 65.0)
            self._tokens_left = None

    def _learn_limits(self, headers) -> None:
        try:
            left = headers.get("x-ratelimit-remaining-tokens")
            reset = headers.get("x-ratelimit-reset-tokens")
            if left is not None and reset is not None:
                self._tokens_left, self._tokens_reset = float(left), time.monotonic() + _seconds(reset)
        except (ValueError, TypeError):
            self._tokens_left = None

    def _post(self, body: dict) -> dict:
        # some providers sit behind a firewall that refuses the default signature of a script client (Groq: error 1010), so the
        # client says plainly what it is; nothing about the user or the project goes into it
        headers = {"Content-Type": "application/json", "User-Agent": "reviewpulse-client/1.0", **self._headers}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        data = json.dumps(body).encode()
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            self._pace()
            self._wait_for_tokens(data)
            req = urllib.request.Request(self.base_url + "/chat/completions", data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    self._learn_limits(r.headers)
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as exc:
                text = exc.read().decode("utf-8", "replace")[:600]
                if exc.code == 400 and "reasoning_effort" in text.lower() and "reasoning_effort" in body:
                    body = {k: v for k, v in body.items() if k != "reasoning_effort"}
                    self.reasoning_effort, data = None, json.dumps(body).encode()
                    continue
                if exc.code == 400 and "seed" in text.lower() and "seed" in body:
                    body = {k: v for k, v in body.items() if k != "seed"}      # a provider that does not take a seed: never again
                    self.seed, data = None, json.dumps(body).encode()
                    continue
                if exc.code in (401, 403):
                    blocked = " (blocked before reaching the provider: the request signature was refused)" if "1010" in text else ""
                    raise LLMError(f"{self.provider}: the API key was rejected ({exc.code}){blocked}") from None
                if exc.code == 429 and ("per day" in text.lower() or "(tpd)" in text.lower() or "(rpd)" in text.lower()):
                    self.usage["daily_exhausted"] = True
                    raise LLMError(f"{self.provider}: the daily allowance of this model is used up ({_first_sentence(text)})") from None
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    retry_after = exc.headers.get("retry-after") if exc.headers else None
                    time.sleep(min(60.0, float(retry_after)) if retry_after and retry_after.replace(".", "").isdigit()
                               else min(60.0, delay))
                    delay *= 2
                    continue
                raise LLMError(f"{self.provider}: HTTP {exc.code}: {text}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if attempt < self.max_retries:
                    time.sleep(min(30.0, delay))
                    delay *= 2
                    continue
                raise LLMError(f"{self.provider} is not reachable ({type(exc).__name__})") from None
        raise LLMError(f"{self.provider}: no answer after {self.max_retries + 1} attempts")

    # -- the call ---------------------------------------------------------------------------------------------------
    def _body(self, system: str, user: str | list, schema: dict, mode: str) -> dict:
        body: dict = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.seed is not None:
            body["seed"] = self.seed
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        if mode == "json_schema":
            strict = _strict(schema)
            if strict is None:
                raise LLMError("schema not expressible")
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "answer", "strict": True, "schema": strict}}
        elif mode == "json_object":
            body["response_format"] = {"type": "json_object"}
            body["messages"][0]["content"] = (system + "\n\nAnswer with one JSON object that follows this JSON schema:\n"
                                              + json.dumps(schema))
        else:
            body["messages"][0]["content"] = (system + "\n\nAnswer with one JSON object that follows this JSON schema, "
                                              "and nothing else:\n" + json.dumps(schema))
        return body

    def complete(self, system: str, user: str, json_schema: dict, images: tuple[bytes, ...] = ()) -> dict:
        """`images`: PNG pictures sent with the question, to a model that can read them. Pictures of drawings are never sent
        outside this machine and its private network: consent to use a hosted model covers the checklist's words only."""
        if images:
            if self.external:
                raise LLMError(f"{self.provider}: pictures of drawings are not sent to a service outside this network")
            user = [*({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(i).decode()}}
                      for i in images), {"type": "text", "text": user}]
        try:
            return self._complete(system, user, json_schema)
        except LLMError as exc:
            self.usage["errors"] += 1
            self.usage["last_error"] = str(exc)[:300]
            raise

    def _complete(self, system: str, user: str, json_schema: dict) -> dict:
        modes = [self._mode] if self._mode else ["json_schema", "json_object", "text"]
        last_error: Exception | None = None
        t0 = time.time()
        for mode in modes:
            try:
                out = self._post(self._body(system, user, json_schema, mode))
            except LLMError as exc:
                last_error = exc
                refusal = "HTTP 400" in str(exc) or "HTTP 422" in str(exc) or "not expressible" in str(exc)
                if refusal and self.structured == "auto" and mode != modes[-1]:
                    continue                       # this provider or model does not take that mode: try a looser one
                raise
            self._mode = mode if self.structured == "auto" else self._mode
            choice = (out.get("choices") or [{}])[0]
            if choice.get("finish_reason") == "length":
                raise LLMError(f"{self.provider}: the answer was cut off at {self.max_tokens} tokens")
            usage = out.get("usage") or {}
            self.last = {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                         "seconds": round(time.time() - t0, 2), "mode": mode, "model": out.get("model", self.model)}
            self.usage["calls"] += 1
            self.usage["prompt_tokens"] += usage.get("prompt_tokens") or 0
            self.usage["completion_tokens"] += usage.get("completion_tokens") or 0
            self.usage["seconds"] += time.time() - t0
            return extract_json((choice.get("message") or {}).get("content", ""))
        raise last_error or LLMError(f"{self.provider}: no answer")
