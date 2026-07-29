import pytest
import requests

from football_data_org import client


class FakeResponse:
    """Stand-in for requests.Response — only implements what get_standings/
    get_matches/get_squad actually touch: .text and .json()."""
    def __init__(self, text="not valid json", should_raise=True):
        self.text = text
        self._should_raise = should_raise

    def json(self):
        if self._should_raise:
            raise requests.exceptions.JSONDecodeError("Expecting value", self.text, 0)
        return {}


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    """limiter.wait() sleeps up to min_delay seconds per call — irrelevant to
    the try/except behavior under test, so skip the real wait."""
    monkeypatch.setattr(client.limiter, "wait", lambda: None)


# ---- get_standings ----

def test_get_standings_returns_empty_dict_when_request_fails(monkeypatch):
    monkeypatch.setattr(client, "retry_request", lambda url, headers=None: None)

    result = client.get_standings("PL", "2025")

    assert result == {}


def test_get_standings_returns_empty_dict_on_invalid_json(monkeypatch):
    monkeypatch.setattr(
        client, "retry_request",
        lambda url, headers=None: FakeResponse(text="<html>500 error page</html>")
    )

    result = client.get_standings("PL", "2025")

    assert result == {}


# ---- get_matches ----

def test_get_matches_returns_empty_dict_when_request_fails(monkeypatch):
    monkeypatch.setattr(client, "retry_request", lambda url, headers=None: None)

    result = client.get_matches("PL", "2025")

    assert result == {}


def test_get_matches_returns_empty_dict_on_invalid_json(monkeypatch):
    monkeypatch.setattr(
        client, "retry_request",
        lambda url, headers=None: FakeResponse(text="<html>500 error page</html>")
    )

    result = client.get_matches("PL", "2025")

    assert result == {}


# ---- get_squad ----

def test_get_squad_returns_empty_dict_when_request_fails(monkeypatch):
    monkeypatch.setattr(client, "retry_request", lambda url, headers=None: None)

    result = client.get_squad(team_id=57)

    assert result == {}


def test_get_squad_returns_empty_dict_on_invalid_json(monkeypatch):
    monkeypatch.setattr(
        client, "retry_request",
        lambda url, headers=None: FakeResponse(text="<html>500 error page</html>")
    )

    result = client.get_squad(team_id=57)

    assert result == {}


# ---- extract_team_ids ----

def test_extract_team_ids_returns_ids_from_total_block():
    standings = {
        "standings": [
            {"type": "HOME", "table": [{"team": {"id": 99}}]},
            {"type": "TOTAL", "table": [{"team": {"id": 1}}, {"team": {"id": 2}}]},
        ]
    }

    assert client.extract_team_ids(standings) == [1, 2]


def test_extract_team_ids_skips_rows_without_team_id():
    standings = {
        "standings": [
            {"type": "TOTAL", "table": [{"team": {}}, {"team": {"id": 5}}]},
        ]
    }

    assert client.extract_team_ids(standings) == [5]


def test_extract_team_ids_returns_empty_list_when_no_total_block():
    standings = {
        "standings": [{"type": "HOME", "table": [{"team": {"id": 1}}]}]
    }

    assert client.extract_team_ids(standings) == []
