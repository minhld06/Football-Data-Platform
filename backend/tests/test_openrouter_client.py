import pytest

import openrouter_client


class FakeResponse:
    def __init__(self, status_code, payload, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_call_chat_completion_parses_content_and_usage(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "```sql\nSELECT 1\n```"}}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 7},
            },
        )

    monkeypatch.setattr(openrouter_client.httpx, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    result = openrouter_client.call_chat_completion("openai/gpt-4o-mini", [{"role": "user", "content": "hi"}])

    assert result["content"] == "```sql\nSELECT 1\n```"
    assert result["prompt_tokens"] == 42
    assert result["completion_tokens"] == 7
    assert result["latency_ms"] >= 0


def test_call_chat_completion_raises_on_error_status(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return FakeResponse(500, {}, text="internal error")

    monkeypatch.setattr(openrouter_client.httpx, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    with pytest.raises(openrouter_client.OpenRouterError):
        openrouter_client.call_chat_completion("openai/gpt-4o-mini", [{"role": "user", "content": "hi"}])


def test_call_chat_completion_retries_on_429_then_succeeds(monkeypatch):
    responses = [
        FakeResponse(429, {}, text="rate limited", headers={"Retry-After": "3"}),
        FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "Arsenal is top of the league."}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            },
        ),
    ]

    def fake_post(url, headers, json, timeout):
        return responses.pop(0)

    sleep_calls = []
    monkeypatch.setattr(openrouter_client.httpx, "post", fake_post)
    monkeypatch.setattr(openrouter_client.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    result = openrouter_client.call_chat_completion("openai/gpt-4o-mini", [{"role": "user", "content": "hi"}])

    assert result["content"] == "Arsenal is top of the league."
    assert sleep_calls == [3.0]


def test_call_chat_completion_gives_up_after_max_retries(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return FakeResponse(429, {}, text="rate limited", headers={"Retry-After": "1"})

    sleep_calls = []
    monkeypatch.setattr(openrouter_client.httpx, "post", fake_post)
    monkeypatch.setattr(openrouter_client.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    with pytest.raises(openrouter_client.OpenRouterError):
        openrouter_client.call_chat_completion("openai/gpt-4o-mini", [{"role": "user", "content": "hi"}])

    assert len(sleep_calls) == openrouter_client.MAX_RATE_LIMIT_RETRIES


def test_call_chat_completion_does_not_retry_on_non_429_error(monkeypatch):
    def fake_post(url, headers, json, timeout):
        return FakeResponse(500, {}, text="internal error")

    sleep_calls = []
    monkeypatch.setattr(openrouter_client.httpx, "post", fake_post)
    monkeypatch.setattr(openrouter_client.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    with pytest.raises(openrouter_client.OpenRouterError):
        openrouter_client.call_chat_completion("openai/gpt-4o-mini", [{"role": "user", "content": "hi"}])

    assert sleep_calls == []


def test_call_chat_completion_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError):
        openrouter_client.call_chat_completion("openai/gpt-4o-mini", [{"role": "user", "content": "hi"}])


def test_get_model_catalog_parses_pricing(monkeypatch):
    openrouter_client._model_catalog_cache = None

    def fake_get(url, timeout):
        return FakeResponse(
            200,
            {
                "data": [
                    {
                        "id": "openai/gpt-4o-mini",
                        "context_length": 128000,
                        "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
                    }
                ]
            },
        )

    monkeypatch.setattr(openrouter_client.httpx, "get", fake_get)

    catalog = openrouter_client.get_model_catalog()

    assert catalog["openai/gpt-4o-mini"]["context_window"] == 128000
    assert catalog["openai/gpt-4o-mini"]["prompt_price_per_million"] == pytest.approx(0.15)
    assert catalog["openai/gpt-4o-mini"]["completion_price_per_million"] == pytest.approx(0.6)

    openrouter_client._model_catalog_cache = None