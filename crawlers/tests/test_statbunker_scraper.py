import pytest

from statbunker import scraper


class FakeHtmlResponse:
    """Stand-in for requests.Response — scraper.py only ever reads .text."""
    def __init__(self, html):
        self.text = html


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(scraper.limiter, "wait", lambda: None)


# NOTE: scraper.py has no try/except at all — get_standings/get_top_scorers
# rely on "if not X: return []" guards instead (retry_request failing, or
# BeautifulSoup not finding the expected tags). These tests cover that
# defensive-return behavior, since there's no exception handling here to test.

# ---- get_standings ----

def test_get_standings_returns_empty_list_when_request_fails(monkeypatch):
    monkeypatch.setattr(scraper, "retry_request", lambda url, headers=None, timeout=10: None)

    result = scraper.get_standings(comp_id="776")

    assert result == []


def test_get_standings_returns_empty_list_when_table_not_found(monkeypatch):
    html = "<html><body><p>no table here</p></body></html>"
    monkeypatch.setattr(scraper, "retry_request", lambda url, headers=None, timeout=10: FakeHtmlResponse(html))

    result = scraper.get_standings(comp_id="776")

    assert result == []


def test_get_standings_returns_empty_list_when_no_tbody(monkeypatch):
    html = '<html><body><table class="table"><thead><tr><th>Rank</th></tr></thead></table></body></html>'
    monkeypatch.setattr(scraper, "retry_request", lambda url, headers=None, timeout=10: FakeHtmlResponse(html))

    result = scraper.get_standings(comp_id="776")

    assert result == []


# ---- get_top_scorers ----

def test_get_top_scorers_returns_empty_list_when_request_fails(monkeypatch):
    monkeypatch.setattr(scraper, "retry_request", lambda url, headers=None, timeout=10: None)

    result = scraper.get_top_scorers(comp_id="776", club_id="123")

    assert result == []


def test_get_top_scorers_returns_empty_list_when_table_not_found(monkeypatch):
    html = "<html><body><p>no table here</p></body></html>"
    monkeypatch.setattr(scraper, "retry_request", lambda url, headers=None, timeout=10: FakeHtmlResponse(html))

    result = scraper.get_top_scorers(comp_id="776", club_id="123")

    assert result == []
