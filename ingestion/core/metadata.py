import logging

logger = logging.getLogger(__name__)


LEAGUE_CODES = {
    "PL": "premier-league",
    "EPL": "premier-league",
    "FL1": "ligue-1",
    "Ligue_1": "ligue-1",
}

def parse_league_season(filename: str) -> dict:
    stem = filename.replace(".json", "")
    sorted_codes = sorted(LEAGUE_CODES.keys(), key=len, reverse=True)
    
    for code in sorted_codes:
        prefix = code + "_"
        if stem.startswith(prefix):
            season_raw = stem[len(prefix):]
            return {
                "league": LEAGUE_CODES[code],
                "season": normalize_season(season_raw),
            }
    
    # Không match được -> LOG CẢNH BÁO NGAY, không để trôi êm
    logger.warning(
        f"Không nhận diện được league từ filename: '{filename}'. "
        f"Cần thêm vào LEAGUE_CODES. Sẽ lưu với league=NULL."
    )
    return {"league": None, "season": None}


def normalize_season(season_raw: str) -> str:
    """
    Chuẩn hóa season về format YYYY-YYYY.
    "2025" -> "2025-2026"
    "2025-2026" -> "2025-2026" (giữ nguyên)
    """
    if "-" in season_raw:
        return season_raw
    year = int(season_raw)
    return f"{year}-{year + 1}"