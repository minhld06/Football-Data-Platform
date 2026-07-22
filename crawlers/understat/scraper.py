import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from crawlers.common.utils import get_logger, RateLimiter, save_raw

logger = get_logger(__name__)
limiter = RateLimiter(min_delay=3.0)


BASE_URL = "https://understat.com"

def get_standings(league, season):
    """Scrape the standings table + xG from Understat using Playwright"""
    season_start = season.split("-")[0]
    url = f"{BASE_URL}/league/{league}/{season_start}"

    browser = None
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
        except Exception as e:
            logger.error(f"Playwright error while crawling {url}: {e}")
            return []
        finally:
            if browser:
                browser.close()

    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        # The standings table is always the first table (index 0)
        table = tables[0] if tables else None
        if not table:
            logger.error(f"Table not found for {league} season {season}!")
            return []

        standings = []
        for row in table.find("tbody").find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 11:
                continue

            # Team name is inside an <a> tag
            team_tag = cols[1].find("a")

            # xG has an extra <sup> tag inside — use get_text() to grab everything then split it out
            xg_text = cols[9].find("sup")
            xga_text = cols[10].find("sup")
            xpts_text = cols[11].find("sup") if len(cols) > 11 else None

            standings.append({
                "rank":     cols[0].get_text(strip=True),
                "team":     team_tag.get_text(strip=True) if team_tag else "",
                "played":   cols[2].get_text(strip=True),
                "wins":     cols[3].get_text(strip=True),
                "draws":    cols[4].get_text(strip=True),
                "losses":   cols[5].get_text(strip=True),
                "goals_for":     cols[6].get_text(strip=True),
                "goals_against": cols[7].get_text(strip=True),
                "points":   cols[8].get_text(strip=True),
                # Extract the xG figure — strip the <sup> (+/-) part by splitting it off
                "xG":  cols[9].get_text(strip=True).split("+")[0].split("-")[0] if xg_text else cols[9].get_text(strip=True),
                "xGA": cols[10].get_text(strip=True).split("+")[0].split("-")[0] if xga_text else cols[10].get_text(strip=True),
                "xPTS": cols[11].get_text(strip=True).split("+")[0].split("-")[0] if xpts_text else "",
            })
    except AttributeError as e:
        logger.error(f"HTML structure changed while parsing {league} season {season}: {e}")
        return []

    return standings


def crawl_competition(league, season):
    """Crawl one competition and save the results"""
    logger.info(f"Starting crawl for {league} season {season}...")
    standings = get_standings(league, season)
    if not standings:
        logger.error(f"Skipping file save for {league} season {season} because standings could not be fetched")
        limiter.wait()
        return

    save_raw(standings, "understat", "standings", f"{league}_{season}")
    limiter.wait()
    logger.info(f"Finished {league} season {season}")

if __name__ == "__main__":
    competitions = [
        {"league": "EPL",     "season": "2025-2026"},
        {"league": "Ligue_1", "season": "2025-2026"},
    ]

    for competition in competitions:
        try:
            crawl_competition(
                league=competition["league"],
                season=competition["season"]
            )
        except OSError as e:
            logger.error(f"Crawl failed for {competition['league']} season {competition['season']}: {e}")
            continue

    print("Done!")
