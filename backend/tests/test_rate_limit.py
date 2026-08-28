"""Unit + integration tests for backend/rate_limit.py.

test_requests_within_the_limit_are_not_rejected and
test_request_over_the_limit_is_rejected_with_429 go through the real
POST /api/chat route (TestClient always reports the same client IP, which is
exactly what we want there). The remaining tests call
rate_limit.enforce_chat_rate_limit directly with fabricated per-IP requests,
since that's the only way to exercise per-IP bucketing and window expiry.
"""

from starlette.requests import Request

import chat_engine
import openrouter_client
import rate_limit
import routers.chat as chat_router
from fastapi.testclient import TestClient
from main import app

MODEL = next(iter(chat_engine.ALLOWED_MODELS))


class FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def cursor(self):
        return FakeCursor()

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub_chat_dependencies(monkeypatch):
    monkeypatch.setattr(
        openrouter_client,
        "call_chat_completion",
        lambda *a, **k: {"content": "Hi.", "prompt_tokens": 1, "completion_tokens": 1, "latency_ms": 1},
    )
    monkeypatch.setattr(chat_router, "get_connection", lambda: FakeConnection())
    monkeypatch.setattr(chat_router, "get_chatbot_connection", lambda: FakeConnection())


def _fake_request(ip: str) -> Request:
    return Request({"type": "http", "client": (ip, 12345), "headers": []})


def test_requests_within_the_limit_are_not_rejected(monkeypatch):
    _stub_chat_dependencies(monkeypatch)
    client = TestClient(app)

    for i in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        response = client.post(
            "/api/chat",
            json={"message": "Hello", "conversation_id": f"conv-{i}", "model": MODEL},
        )
        assert response.status_code == 200


def test_request_over_the_limit_is_rejected_with_429(monkeypatch):
    _stub_chat_dependencies(monkeypatch)
    client = TestClient(app)

    for i in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        client.post(
            "/api/chat",
            json={"message": "Hello", "conversation_id": f"conv-{i}", "model": MODEL},
        )

    response = client.post(
        "/api/chat",
        json={"message": "One too many", "conversation_id": "conv-over", "model": MODEL},
    )
    assert response.status_code == 429


def test_limit_is_tracked_per_ip_independently():
    for _ in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        rate_limit.enforce_chat_rate_limit(_fake_request("1.1.1.1"))

    # 1.1.1.1 is now at the limit; a different IP should be unaffected.
    rate_limit.enforce_chat_rate_limit(_fake_request("2.2.2.2"))


def test_old_requests_fall_outside_the_window_and_free_up_capacity(monkeypatch):
    current_time = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: current_time[0])

    for _ in range(rate_limit.MAX_REQUESTS_PER_WINDOW):
        rate_limit.enforce_chat_rate_limit(_fake_request("3.3.3.3"))

    current_time[0] += rate_limit.WINDOW_SECONDS + 1

    # The whole earlier burst has aged out of the window, so this should
    # succeed instead of raising.
    rate_limit.enforce_chat_rate_limit(_fake_request("3.3.3.3"))
