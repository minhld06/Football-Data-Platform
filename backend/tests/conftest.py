import pytest

import rate_limit


@pytest.fixture(autouse=True)
def _reset_chat_rate_limit():
    """Every test file posts to /api/chat through a shared TestClient host,
    so without this the per-IP counter in rate_limit.py would carry over
    between tests and make later tests fail depending on run order/count."""
    rate_limit.reset()
    yield
    rate_limit.reset()
