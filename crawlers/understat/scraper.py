import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import json
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from crawlers.common.utils import get_logger, RateLimiter

logger = get_logger(__name__)
limiter = RateLimiter(min_delay=3.0)


BASE_URL = "https://understat.com"

def get_standings(league, season):
    """Scrape bảng xếp hạng + xG từ Understat dùng Playwright"""
    season_start = season.split("-")[0]
    url = f"{BASE_URL}/league/{league}/{season_start}"

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
        except Exception as e:
            logger.error(f"Playwright lỗi khi crawl {url}: {e}")
            return []
        finally:
            browser.close()
            
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    # Bảng xếp hạng luôn là bảng đầu tiên (index 0)
    table = tables[0] if tables else None
    if not table:
        logger.error(f"Không tìm thấy bảng cho {league} mùa {season}!")
        return []

    standings = []
    for row in table.find("tbody").find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 9:
            continue

        # Tên đội nằm trong thẻ <a>
        team_tag = cols[1].find("a")

        # xG có thêm thẻ <sup> bên trong — dùng get_text() lấy hết rồi tách
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
            # Lấy chỉ số xG — bỏ phần <sup> (+/-) bằng cách decompose
            "xG":  cols[9].get_text(strip=True).split("+")[0].split("-")[0] if xg_text else cols[9].get_text(strip=True),
            "xGA": cols[10].get_text(strip=True).split("+")[0].split("-")[0] if xga_text else cols[10].get_text(strip=True),
            "xPTS": cols[11].get_text(strip=True).split("+")[0].split("-")[0] if xpts_text else "",
        })

    return standings

def save_raw(data, source, entity, league, season):
    """Lưu dữ liệu thô theo cấu trúc nhất quán"""
    path = f"data/raw/{source}/{entity}/{league}_{season}.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Đã lưu: {path}")

def crawl_competition(league, season):
    """Crawl một giải đấu và lưu lại"""
    logger.info(f"Bắt đầu crawl {league} mùa {season}...")
    standings = get_standings(league, season)
    save_raw(standings, "understat", "standings", league, season)
    limiter.wait()
    logger.info(f"Hoàn thành {league} mùa {season}")

if __name__ == "__main__":
    competitions = [
        {"league": "EPL",     "season": "2025-2026"},
        {"league": "Ligue_1", "season": "2025-2026"},
    ]

    for competition in competitions:
        crawl_competition(
            league=competition["league"],
            season=competition["season"]
        )

    print("Xong!")