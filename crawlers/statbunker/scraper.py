import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import json
from bs4 import BeautifulSoup
from crawlers.common.utils import get_logger, RateLimiter, retry_request

logger = get_logger(__name__)
limiter = RateLimiter(min_delay=3.0)  # statbunker không có rate limit cụ thể, dùng 3s

BASE_URL = "https://www.statbunker.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


# comp_id riêng cho từng mùa — phải tìm thủ công trên statbunker
COMPETITION_IDS = {
    "PL_2025-2026": "776",
}

def get_standings(comp_id):
    """Scrape bảng xếp hạng từ statbunker"""
    url = f"{BASE_URL}/competitions/LeagueTable?comp_id={comp_id}"
    
    response = retry_request(url, headers=HEADERS, timeout=30)
    if not response:
        logger.error(f"Không lấy được standings cho comp_id={comp_id}")
        return []
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"class": "table"})
    if not table:
        print("Không tìm thấy bảng!")
        return []

    standings = []
    for row in table.find("tbody").find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 9:
            continue

        # Tên đội nằm trong thẻ <p> bên trong cột thứ 2
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

def save_raw(data, source, entity, competition_code, season):
    """Lưu dữ liệu thô theo cấu trúc nhất quán"""
    path = f"data/raw/{source}/{entity}/{competition_code}_{season}.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Đã lưu: {path}")

def crawl_competition(competition_code, season):
    logger.info(f"Bắt đầu crawl {competition_code} mùa {season}...")
    key = f"{competition_code}_{season}"
    comp_id = COMPETITION_IDS.get(key)
    if not comp_id:
        logger.error(f"Không tìm thấy comp_id cho {key}")
        return

    standings = get_standings(comp_id)
    save_raw(standings, "statbunker", "standings", competition_code, season)
    logger.info(f"Hoàn thành {competition_code} mùa {season}")
    limiter.wait()

if __name__ == "__main__":
    competitions = [
        {"code": "PL", "season": "2025-2026"},
    ]

    for competition in competitions:
        crawl_competition(
            competition_code=competition["code"],
            season=competition["season"]
        )

    print("Xong!")