import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
from crawlers.common.utils import get_logger, RateLimiter, retry_request, save_raw

logger = get_logger(__name__)
limiter = RateLimiter(min_delay=6.0)  # football-data.org giới hạn 10 req/phút
load_dotenv()

API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": API_KEY}


def get_standings(competition_code="PL", season="2025"):
    """Lấy bảng xếp hạng. PL = Premier League"""
    url = f"{BASE_URL}/competitions/{competition_code}/standings?season={season}"
    limiter.wait()  # Chờ đủ thời gian trước khi request
    response = retry_request(url, headers=HEADERS)
    if not response:
        logger.error(f"Không lấy được standings cho {competition_code}")
        return {}
    return response.json()

def get_matches(competition_code="PL", season="2025"):
    """Lấy danh sách trận đấu"""
    url = f"{BASE_URL}/competitions/{competition_code}/matches?season={season}"
    limiter.wait()
    response = retry_request(url, headers=HEADERS)
    if not response:
        logger.error(f"Không lấy được matches cho {competition_code}")
        return {}
    return response.json()



def crawl_competition(competition_code, season):
    """Crawl một giải đấu và lưu lại"""
    logger.info(f"Bắt đầu crawl {competition_code} mùa {season}...")
    
    standings = get_standings(competition_code, season)
    save_raw(standings, "football_data_org", "standings", f"{competition_code}_{season}")

    matches = get_matches(competition_code, season)
    save_raw(matches, "football_data_org", "matches", f"{competition_code}_{season}")

    logger.info(f"Hoàn thành {competition_code} mùa {season}")
    limiter.wait()  # Chờ đủ thời gian trước khi crawl giải đấu tiếp theo


if __name__ == "__main__":
    competitions = [
        {"code": "PL", "season": "2025"},   # Premier League
        {"code": "FL1", "season": "2025"}   # Ligue 1
    ]

    for competition in competitions:
        crawl_competition(
            competition_code=competition["code"],
            season=competition["season"]
        )

    print("Xong!")