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
    
def get_squad(team_id):
    """Fetch a team's current squad. No season param exists for this endpoint —
    it always returns the present-day roster, not a season-specific historical one."""
    url = f"{BASE_URL}/teams/{team_id}"
    limiter.wait()
    response = retry_request(url, headers=HEADERS)
    if not response:
        logger.error(f"Failed to fetch squad for team {team_id}")
        return {}
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError:
        logger.error(f"Response is not valid JSON for {url}: {response.text[:200]}")
        return {}

def extract_team_ids(standings):
    """Parse team ids out of the TOTAL block of a standings response."""
    team_ids = []
    for block in standings.get("standings", []):
        if block.get("type") != "TOTAL":
            continue
        for row in block.get("table", []):
            team_id = row.get("team", {}).get("id")
            if team_id is not None:
                team_ids.append(team_id)
    return team_ids

def crawl_competition(competition_code, season, crawl_squads=True):
    """Crawl one competition and save the results.
    crawl_squads: whether to also crawl each team's squad. Skip for competitions
    where football-data.org's plan doesn't provide squad depth (e.g. Ligue 1
    returns 200 with an empty squad array for every team) to avoid burning
    /teams/{id} quota on data that will always be empty.
    """
    logger.info(f"Starting crawl for {competition_code} season {season}...")

    standings = get_standings(competition_code, season)
    if standings:
        save_raw(standings, "football_data_org", "standings", f"{competition_code}_{season}")
        if crawl_squads:
            for team_id in extract_team_ids(standings):
                squad = get_squad(team_id)
                if squad:
                    save_raw(squad, "football_data_org", "players", f"{competition_code}_{season}_{team_id}")
                else:
                    logger.error(f"Skipping squad save for team {team_id} because no data was fetched")
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
        {"code": "PL", "season": "2025", "crawl_squads": True},   # Premier League - full squad data available
        {"code": "FL1", "season": "2025", "crawl_squads": False}   # Ligue 1 - football-data.org free tier returns empty squad for every team
    ]

    for competition in competitions:
        try:
            crawl_competition(
                competition_code=competition["code"],
                season=competition["season"],
                crawl_squads=competition["crawl_squads"]
            )
        except (OSError, requests.exceptions.RequestException) as e:
            logger.error(
                f"Crawl failed for {competition['code']} season {competition['season']}: {e}"
            )
            continue

    print("Done!")
