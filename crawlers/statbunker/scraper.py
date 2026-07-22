import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import requests
from bs4 import BeautifulSoup
from crawlers.common.utils import get_logger, RateLimiter, retry_request, save_raw

logger = get_logger(__name__)
limiter = RateLimiter(min_delay=3.0)  # statbunker has no specific rate limit, use 3s

BASE_URL = "https://www.statbunker.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


# comp_id is specific to each season — must be found manually on statbunker
COMPETITION_IDS = {
    "PL_2025-2026": "776",
}

def get_standings(comp_id):
    """Scrape the standings table from statbunker"""
    url = f"{BASE_URL}/competitions/LeagueTable?comp_id={comp_id}"

    response = retry_request(url, headers=HEADERS, timeout=30)
    if not response:
        logger.error(f"Failed to fetch standings for comp_id={comp_id}")
        return []
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"class": "table"})
    if not table:
        logger.error(f"Table not found for comp_id={comp_id}")
        return []

    tbody = table.find("tbody")
    if not tbody:
        logger.error(f"Table has no tbody for comp_id={comp_id}")
        return []

    standings = []
    for row in tbody.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 10:
            continue

        # Team name is inside a <p> tag within the 2nd column
        team_tag = cols[1].find("p")
        if not team_tag:
            continue

        standings.append({
            "rank":           cols[0].get_text(strip=True),
            "team":           team_tag.get_text(strip=True),
            "played":         cols[2].get_text(strip=True),
            "wins":           cols[3].get_text(strip=True),
            "draws":          cols[4].get_text(strip=True),
            "losses":         cols[5].get_text(strip=True),
            "goals_for":      cols[6].get_text(strip=True),
            "goals_against":  cols[7].get_text(strip=True),
            "goal_diff":      cols[8].get_text(strip=True),
            "points":         cols[9].get_text(strip=True),
        })

    return standings


def crawl_competition(competition_code, season):
    logger.info(f"Starting crawl for {competition_code} season {season}...")
    key = f"{competition_code}_{season}"
    comp_id = COMPETITION_IDS.get(key)
    if not comp_id:
        logger.error(f"comp_id not found for {key}")
        return

    standings = get_standings(comp_id)
    if not standings:
        logger.error(f"Skipping file save for {key} because standings could not be fetched")
        limiter.wait()
        return

    save_raw(standings, "statbunker", "standings", f"{competition_code}_{season}")

    logger.info(f"Finished {competition_code} season {season}")
    limiter.wait()

if __name__ == "__main__":
    competitions = [
        {"code": "PL", "season": "2025-2026"},
    ]

    for competition in competitions:
        try:
            crawl_competition(
                competition_code=competition["code"],
                season=competition["season"]
            )
        except (OSError, requests.exceptions.RequestException) as e:
            logger.error(
                f"Crawl failed for {competition['code']} season {competition['season']}: {e}"
            )
            continue

    print("Done!")
