import pytest
import requests

from understat import scraper


class FakeJsonResponse:
    """Stand-in for requests.Response used by get_player_stats."""
    def __init__(self, text="not valid json", should_raise=True):
        self.text = text
        self._should_raise = should_raise

    def json(self):
        if self._should_raise:
            raise requests.exceptions.JSONDecodeError("Expecting value", self.text, 0)
        return {}


class FakeChromium:
    def launch(self):
        raise RuntimeError("simulated Playwright crash")


class FakePlaywrightContext:
    """Stand-in for the object sync_playwright() gives you, just enough to
    make browser = p.chromium.launch() raise inside the `with` block."""
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def chromium(self):
        return FakeChromium()


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(scraper.limiter, "wait", lambda: None)


# ---- _fetch_league_page_html: except Exception (broad, covers Playwright errors) ----

def test_fetch_league_page_html_returns_none_on_playwright_error(monkeypatch):
    monkeypatch.setattr(scraper, "sync_playwright", lambda: FakePlaywrightContext())

    result = scraper._fetch_league_page_html("EPL", "2025-2026")

    assert result is None


# ---- _parse_standings_table: except AttributeError (HTML structure changed) ----

def test_parse_standings_table_returns_empty_list_when_no_tbody():
    html = "<html><body><table><thead><tr><th>Rank</th></tr></thead></table></body></html>"

    result = scraper._parse_standings_table(html, "EPL", "2025-2026")

    assert result == []


def test_parse_standings_table_returns_empty_list_when_no_table():
    html = "<html><body><p>no table here</p></body></html>"

    result = scraper._parse_standings_table(html, "EPL", "2025-2026")

    assert result == []


# ---- get_player_stats: except requests.exceptions.JSONDecodeError ----

def test_get_player_stats_returns_empty_list_when_request_fails(monkeypatch):
    monkeypatch.setattr(scraper, "retry_request", lambda url, headers=None, timeout=10: None)

    result = scraper.get_player_stats("EPL", "2025-2026")

    assert result == []


def test_get_player_stats_returns_empty_list_on_invalid_json(monkeypatch):
    monkeypatch.setattr(
        scraper, "retry_request",
        lambda url, headers=None, timeout=10: FakeJsonResponse(text="<html>500 error page</html>")
    )

    result = scraper.get_player_stats("EPL", "2025-2026")

    assert result == []
