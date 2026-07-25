import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import requests
from bs4 import BeautifulSoup
from crawlers.common.utils import get_logger, RateLimiter, retry_request, save_raw, RAW_DATA_DIR
from urllib.parse import urlparse, parse_qs 
from datetime import date

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

        # Team name is inside a <p> tag within the 2nd column; the <a> wrapping
        # it links to that club's own pages and carries club_id in its href —
        # this is the only place club_id is exposed, there's no separate lookup.
        team_tag = cols[1].find("p")
        if not team_tag:
            continue

        team_link = cols[1].find("a")
        club_id = None
        if team_link and team_link.get("href"):
            query = parse_qs(urlparse(team_link["href"]).query)
            club_id = query.get("club_id", [None])[0]

        standings.append({
            "rank":           cols[0].get_text(strip=True),
            "team":           team_tag.get_text(strip=True),
            "club_id":        club_id,
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

def get_top_scorers(comp_id, club_id):
    """Scrape one club's top goal scorers. statbunker has no competition-wide
    top-scorers page — this must be called once per club_id."""
    url = f"{BASE_URL}/competitions/TopGoalScorers?comp_id={comp_id}&club_id={club_id}"

    limiter.wait()
    response = retry_request(url, headers=HEADERS, timeout=30)
    if not response:
        logger.error(f"Failed to fetch top scorers for comp_id={comp_id} club_id={club_id}")
        return []
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"class": "table"})
    if not table:
        logger.error(f"Top scorers table not found for comp_id={comp_id} club_id={club_id}")
        return []

    tbody = table.find("tbody")
    if not tbody:
        logger.error(f"Top scorers table has no tbody for comp_id={comp_id} club_id={club_id}")
        return []

    player_stats = []
    for row in tbody.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 8:
            continue

        # Player name is inside a <p> tag within the 1st column, same structure
        # as the team name on the standings page.
        player_tag = cols[0].find("p")
        if not player_tag:
            continue

        player_stats.append({
            "player":  player_tag.get_text(strip=True),
            "goals":   cols[1].get_text(strip=True),
            "fh":      cols[2].get_text(strip=True),
            "sh":      cols[3].get_text(strip=True),
            "fs":      cols[4].get_text(strip=True),
            "ls":      cols[5].get_text(strip=True),
            "h":       cols[6].get_text(strip=True),
            "a":       cols[7].get_text(strip=True),
        })

    return player_stats

def _has_player_stats_today(competition_code, season, club_id):
    """Check whether this club's top scorers were already saved today — lets
    crawl_competition() skip clubs it already has instead of re-fetching (and
    creating a byte-identical duplicate file) on every retry run."""
    today = date.today().isoformat()
    folder = RAW_DATA_DIR / "statbunker" / "player_stats" / today
    pattern = f"{competition_code}_{season}_{club_id}_*.json"
    return folder.exists() and any(folder.glob(pattern))

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

    for team in standings:
        club_id = team.get("club_id")
        if not club_id:
            logger.error(f"Skipping top scorers for {team['team']} ({key}) — no club_id found")
            continue

        if _has_player_stats_today(competition_code, season, club_id):
            logger.info(f"Already have today's top scorers for {team['team']} ({key}) — skipping")
            continue

        player_stats = get_top_scorers(comp_id, club_id)
        if not player_stats:
            logger.error(f"Skipping top scorers save for {team['team']} ({key}) because no data was fetched")
            continue

        # The top-scorers page is pre-scoped to one club and has no team column —
        # stamp the team name we already know from the loop onto every row.
        for player in player_stats:
            player["team"] = team["team"]

        save_raw(player_stats, "statbunker", "player_stats", f"{competition_code}_{season}_{club_id}")

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
