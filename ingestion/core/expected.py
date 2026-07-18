# Khai báo tĩnh: nguồn nào crawl entity_type/league nào (season-agnostic —
# season đổi theo thời gian nên không hardcode ở đây). Cập nhật thủ công
# khi thêm nguồn hoặc giải đấu mới, giống LEAGUE_CODES trong metadata.py.

EXPECTED_COMBOS = {
    "football_data_org": {
        "matches": ["premier-league", "ligue-1"],
        "standings": ["premier-league", "ligue-1"],
    },
    "statbunker": {
        "standings": ["premier-league"],
    },
    "understat": {
        "standings": ["premier-league", "ligue-1"],
    },
}
