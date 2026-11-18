"""Gemini structured requests with bounded retries and environment-only credentials."""
from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .openai_compat import APIUnavailable as APIUnavailable
from .openai_compat import LLMError


def decoding_schema(schema: Any) -> Any:
    """Avoid counted-array state expansion; application validators keep the limits.

    https://aistudio.google.com/docs/structured-output#simplifying-complex-schemas
    """
    if isinstance(schema, dict):
        types = schema.get("type")
        array = types == "array" or isinstance(types, list) and "array" in types
        return {key: decoding_schema(value) for key, value in schema.items()
                if not (array and key in ("maxItems", "minItems"))}
    if isinstance(schema, list):
        return [decoding_schema(value) for value in schema]
    return schema


class GeminiClient:
    external = True
    provider = "gemini"

    def __init__(self, model: str = "gemini-3.8-flash", *, max_attempts: int = 3,
                 concurrency: int = 1, max_tokens: int = 8192, timeout_s: float = 90,
                 base_delay: float = 2, max_delay: float = 60, env_var: str = "GEMINI_API_KEY"):
        self._key = os.environ.get(env_var)
        if not self._key:
            raise APIUnavailable("MISSING_ENV_CREDENTIAL", None, 0)
        if min(max_attempts, concurrency, max_tokens) < 1:
            raise ValueError("attempts, concurrency and token budget must be positive")
        self.model, self.max_attempts, self.max_tokens = model, max_attempts, max_tokens
        self.timeout_s, self.base_delay, self.max_delay = timeout_s, base_delay, max_delay
        self._semaphore = threading.BoundedSemaphore(concurrency)
        self.events: list[dict] = []
        self.unavailable = False
        self.last: dict = {}

    def _request(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            data=json.dumps(payload).encode(),
            headers={"x-goog-api-key": self._key, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.load(response)

    def complete(self, system: str, user: str, json_schema: dict) -> dict:
        self.last = {}
        if self.unavailable:
            raise APIUnavailable("CIRCUIT_OPEN", None, 0)
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": self.max_tokens,
                                 "responseMimeType": "application/json", "responseJsonSchema": decoding_schema(json_schema)},
        }
        with self._semaphore:
            if self.unavailable:
                raise APIUnavailable("CIRCUIT_OPEN", None, 0)
            for attempt in range(self.max_attempts):
                status, reason, retry_after = None, "NETWORK_ERROR", 0.0
                start = time.monotonic()
                try:
                    output = self._request(payload)
                except urllib.error.HTTPError as error:
                    status, reason = error.code, f"HTTP_{error.code}"
                    # Error bodies may echo credentials or source text. They are never retained.
                    error.read()
                    header = error.headers.get("Retry-After", "") if error.headers else ""
                    retry_after = float(header) if header.replace(".", "", 1).isdigit() else 0.0
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    pass
                else:
                    self.events.append({"attempt": attempt + 1, "http_status": 200,
                                        "seconds": round(time.monotonic() - start, 3)})
                    candidate = (output.get("candidates") or [{}])[0]
                    text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", [])
                                   if not part.get("thought"))
                    self.last = {"model": output.get("modelVersion", self.model),
                                 "usage": output.get("usageMetadata", {}), "text": text}
                    if candidate.get("finishReason") != "STOP":
                        raise LLMError(f"generation finish: {candidate.get('finishReason', 'missing')}")
                    return json.loads(text)
                self.events.append({"attempt": attempt + 1, "http_status": status,
                                    "reason": reason, "seconds": round(time.monotonic() - start, 3)})
                retryable = status in (None, 429, 503, 500, 502, 504)
                if not retryable or attempt + 1 == self.max_attempts:
                    self.unavailable = True
                    raise APIUnavailable(reason, status, attempt + 1)
                backoff = self.base_delay * 2 ** attempt
                time.sleep(min(self.max_delay, max(retry_after, backoff + random.uniform(0, backoff))))
        raise APIUnavailable("NO_RESPONSE", None, self.max_attempts)
