def latest_season(seasons: list[str]) -> str | None:
    """Picks the most recent season from a list of 'YYYY-YYYY' strings.
    String comparison works because the format is zero-padded and lexically
    sortable (e.g. '2025-2026' > '2024-2025')."""
    return max(seasons) if seasons else None


def format_search_results(teams: list[dict], players: list[dict]) -> list[dict]:
    results = []
    for t in teams:
        results.append({
            "type": "team",
            "id": t["team_id"],
            "name": t["team_name"],
            "subtitle": t["league"],
        })
    for p in players:
        results.append({
            "type": "player",
            "id": p["player_id"],
            "name": p["player_name"],
            "subtitle": p["team_name"],
        })
    return results