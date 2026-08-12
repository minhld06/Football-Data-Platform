import os
import time

import httpx

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

_model_catalog_cache: dict[str, dict] | None = None


class OpenRouterError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterError("OPENROUTER_API_KEY is not set in .env")
    return key


def call_chat_completion(model: str, messages: list[dict], timeout: float = 30.0) -> dict:
    """Calls OpenRouter's OpenAI-compatible chat completion endpoint.

    Returns {"content", "prompt_tokens", "completion_tokens", "latency_ms"}.
    """
    started = time.monotonic()
    response = httpx.post(
        OPENROUTER_CHAT_URL,
        headers={"Authorization": f"Bearer {_api_key()}"},
        json={"model": model, "messages": messages},
        timeout=timeout,
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    if response.status_code != 200:
        raise OpenRouterError(f"OpenRouter request failed ({response.status_code}): {response.text}")

    body = response.json()
    usage = body.get("usage", {})
    return {
        "content": body["choices"][0]["message"]["content"],
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "latency_ms": latency_ms,
    }


def get_model_catalog() -> dict[str, dict]:
    """Fetches OpenRouter's model catalog (context window + pricing), cached in-memory for the process lifetime."""
    global _model_catalog_cache
    if _model_catalog_cache is not None:
        return _model_catalog_cache

    response = httpx.get(OPENROUTER_MODELS_URL, timeout=10.0)
    response.raise_for_status()

    catalog = {}
    for entry in response.json().get("data", []):
        pricing = entry.get("pricing", {})
        catalog[entry["id"]] = {
            "context_window": entry.get("context_length"),
            "prompt_price_per_million": float(pricing.get("prompt", 0)) * 1_000_000,
            "completion_price_per_million": float(pricing.get("completion", 0)) * 1_000_000,
        }

    _model_catalog_cache = catalog
    return catalog