"""Per-IP request throttling for POST /api/chat.

Each chat request costs an LLM call (and a DB round-trip), so an
unthrottled client can burn through OpenRouter's free-tier limits or spam
`chatbot.chat_logs`. This is a plain in-memory sliding window — it resets on
backend restart and isn't shared across multiple backend replicas, which is
fine for this project's single-instance deployment but would need a shared
store (e.g. Redis) to scale beyond that.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 10

_request_times_by_ip: dict[str, deque[float]] = defaultdict(deque)


def reset() -> None:
    """Test-only hook to clear state between test cases."""
    _request_times_by_ip.clear()


def enforce_chat_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    timestamps = _request_times_by_ip[client_ip]

    while timestamps and now - timestamps[0] > WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail="Too many chat requests — please wait a moment and try again.",
        )

    timestamps.append(now)
