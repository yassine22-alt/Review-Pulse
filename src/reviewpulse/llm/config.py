"""Which model reads the clauses: configuration, provider presets, and the rule about what may leave the machine.

Two roles:
  primary     reads every clause. Default: the local Ollama model (nothing leaves the machine).
  fallback    an optional hosted model that is asked ONLY about a clause the primary could not turn into a checked rule, and
              ONLY for a project whose reviewer allowed it. Its answer goes through exactly the same checks as any other.

Environment (a `.env` file in the working folder is read too; real environment variables win):

  REVIEWPULSE_LLM=ollama | openai | claude | none            primary backend ("openai" = any OpenAI-compatible endpoint)
  REVIEWPULSE_LLM_REASONING_EFFORT=low|medium|high|off         default low for gpt-oss models (fewer hidden tokens)
  REVIEWPULSE_LLM_MODEL=...                                    model name for the primary
  REVIEWPULSE_FALLBACK=openai                                  turn the hosted fallback on
  REVIEWPULSE_FALLBACK_PROVIDER=groq | openrouter | gemini | mistral | cloudflare | custom
  REVIEWPULSE_FALLBACK_BASE_URL=...                            for custom (or to override a preset)
  REVIEWPULSE_FALLBACK_API_KEY=...                             the key; never logged, never sent anywhere else
  REVIEWPULSE_FALLBACK_MODEL=...                               the hosted model
  REVIEWPULSE_FALLBACK_RPM=...                                 requests per minute to stay under (preset default)
  (the same names with REVIEWPULSE_LLM_ instead of REVIEWPULSE_FALLBACK_ configure an "openai" primary)
  REVIEWPULSE_LLM_CACHE=path | off                             answer cache (default data/llm_cache.sqlite)
"""

from __future__ import annotations

import os
from pathlib import Path

from .cache import CachedClient
from .openai_compat import OpenAICompatClient

# Endpoints are the providers' documented OpenAI-compatible URLs. The data notes summarise what each provider's own pages say
# (read in November 2026); terms change, so a reviewer must read the provider's current terms before allowing a document out.
PRESETS: dict[str, dict] = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b", "rpm": 30,
             "free_tier": "yes, no card",
             "data": "Groq says it does not retain inference inputs and outputs by default and does not train on them, "
                     "on the free tier too; troubleshooting logs may be kept up to 30 days."},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": None, "rpm": 20, "free_tier": "yes, models ending :free",
                   "data": "OpenRouter says it does not log prompts by default and avoids providers that do, unless the "
                           "training toggle in your privacy settings is on."},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": None, "rpm": 10,
               "free_tier": "yes, outside the EEA, Switzerland and the UK",
               "data": "On Google's free tier prompts and answers may be used to improve Google products and may be read by "
                       "people. Not suitable for a confidential document."},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "model": None, "rpm": 30, "free_tier": "monthly credit",
                "data": "In free mode Mistral may use inputs and outputs for training unless you opt out in its admin panel."},
    "cloudflare": {"base_url": None, "model": None, "rpm": 30, "free_tier": "yes, daily allowance",
                   "data": "Cloudflare says it does not use your content to train models. Base URL: "
                           "https://api.cloudflare.com/client/v4/accounts/<account id>/ai/v1"},
}


def read_dotenv(path: str | Path = ".env") -> dict[str, str]:
    out: dict[str, str] = {}
    p = Path(path)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def setting(name: str, default: str | None = None) -> str | None:
    """One setting: the real environment first, then the .env file in the working folder, then the default."""
    return os.environ.get(name) or read_dotenv().get(name) or default


def _get(env: dict, *names: str) -> str | None:
    for n in names:
        if env.get(n):
            return env[n]
    return None


def _openai_from(env: dict, prefix: str) -> OpenAICompatClient | None:
    provider = (_get(env, f"{prefix}_PROVIDER") or "custom").lower()
    preset = PRESETS.get(provider, {})
    base = _get(env, f"{prefix}_BASE_URL") or preset.get("base_url")
    model = _get(env, f"{prefix}_MODEL") or preset.get("model")
    key = _get(env, f"{prefix}_API_KEY")
    if not base or not model:
        return None
    rpm = _get(env, f"{prefix}_RPM")
    # a reasoning model (gpt-oss) thinks at length by default, and a free tier counts those tokens; the questions put to it are
    # multiple choices, so the lowest effort is asked unless the setting says otherwise
    effort = _get(env, f"{prefix}_REASONING_EFFORT") or ("low" if "gpt-oss" in model.lower() else None)
    if effort and effort.lower() in ("off", "none"):
        effort = None
    return OpenAICompatClient(base, key, model, provider=provider, rpm=float(rpm) if rpm else preset.get("rpm"),
                              reasoning_effort=effort)


def _wrap(client, env: dict):
    cache = env.get("REVIEWPULSE_LLM_CACHE", "data/llm_cache.sqlite")
    if client is None or cache.lower() == "off":
        return client
    return CachedClient(client, cache, mode=env.get("REVIEWPULSE_LLM_CACHE_MODE", "readwrite"))


def primary_from_env(env: dict | None = None):
    """The primary client for an OpenAI-compatible backend, or None (the local backends are built elsewhere)."""
    env = {**read_dotenv(), **(env if env is not None else os.environ)}
    return _wrap(_openai_from(env, "REVIEWPULSE_LLM"), env)


def fallback_from_env(env: dict | None = None):
    """The hosted fallback client, or None when it is not configured."""
    env = {**read_dotenv(), **(env if env is not None else os.environ)}
    if (env.get("REVIEWPULSE_FALLBACK") or "").lower() not in ("openai", "hosted", "1", "true"):
        return None
    return _wrap(_openai_from(env, "REVIEWPULSE_FALLBACK"), env)


def describe(client) -> dict:
    """What the screens may show about a client: no key, no URL path."""
    if client is None:
        return {"available": False}
    provider = getattr(client, "provider", type(client).__name__.replace("Client", "").lower())
    note = PRESETS.get(provider, {}).get("data")
    return {"available": True, "provider": provider, "model": getattr(client, "model", ""),
            "external": bool(getattr(client, "external", False)), "data_note": note}
