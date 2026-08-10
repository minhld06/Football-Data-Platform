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


def merge_search_results(
    hits_by_tier: list[list[dict]], id_key: str, name_key: str, limit: int = 10
) -> list[dict]:
    """Dedupe rows across match tiers (each row already tagged with an int
    'priority', lower = better) by id_key, keeping each entity's
    best-priority row, then sort by (priority, name_key) and truncate."""
    best: dict[int, dict] = {}
    for tier in hits_by_tier:
        for row in tier:
            key = row[id_key]
            if key not in best or row["priority"] < best[key]["priority"]:
                best[key] = row
    ordered = sorted(best.values(), key=lambda r: (r["priority"], r[name_key]))
    return ordered[:limit]