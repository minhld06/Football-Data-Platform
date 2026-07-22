import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import requests
from dotenv import load_dotenv
from crawlers.common.utils import get_logger, RateLimiter, retry_request, save_raw



logger = get_logger(__name__)
limiter = RateLimiter(min_delay=6.0)  # football-data.org limits to 10 req/min
load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
if not API_KEY:
    raise RuntimeError("FOOTBALL_DATA_API_KEY is not set in .env")

BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY}


def get_standings(competition_code="PL", season="2025"):
    """Fetch the standings table. PL = Premier League"""
    url = f"{BASE_URL}/competitions/{competition_code}/standings?season={season}"
    limiter.wait()  # Wait long enough before the request
    response = retry_request(url, headers=HEADERS)
    if not response:
        logger.error(f"Failed to fetch standings for {competition_code}")
        return {}
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error(f"Response is not valid JSON for {url}: {response.text[:200]}")
        return {}

def get_matches(competition_code="PL", season="2025"):
    """Fetch the list of matches"""
    url = f"{BASE_URL}/competitions/{competition_code}/matches?season={season}"
    limiter.wait()
    response = retry_request(url, headers=HEADERS)
    if not response:
        logger.error(f"Failed to fetch matches for {competition_code}")
        return {}
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error(f"Response is not valid JSON for {url}: {response.text[:200]}")
        return {}



def crawl_competition(competition_code, season):
    """Crawl one competition and save the results"""
    logger.info(f"Starting crawl for {competition_code} season {season}...")

    standings = get_standings(competition_code, season)
    if standings:
        save_raw(standings, "football_data_org", "standings", f"{competition_code}_{season}")
    else:
        logger.error(f"Skipping standings save for {competition_code} because no data was fetched")

    matches = get_matches(competition_code, season)
    if matches:
        save_raw(matches, "football_data_org", "matches", f"{competition_code}_{season}")
    else:
        logger.error(f"Skipping matches save for {competition_code} because no data was fetched")

    logger.info(f"Finished {competition_code} season {season}")
    limiter.wait()  # Wait long enough before crawling the next competition


if __name__ == "__main__":
    competitions = [
        {"code": "PL", "season": "2025"},   # Premier League
        {"code": "FL1", "season": "2025"}   # Ligue 1
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
