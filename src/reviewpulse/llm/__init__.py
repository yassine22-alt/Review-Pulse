"""Model access: a provider-neutral client, an answer cache, and the configuration that decides what may leave the machine."""

from .cache import CachedClient
from .config import PRESETS, describe, fallback_from_env, primary_from_env, setting
from .openai_compat import LLMError, OpenAICompatClient, extract_json, is_external

__all__ = ["CachedClient", "LLMError", "OpenAICompatClient", "PRESETS", "describe", "extract_json", "fallback_from_env",
           "is_external", "primary_from_env", "setting"]
