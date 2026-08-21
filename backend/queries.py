import re


def resolve_team_mentions(message: str, alias_rows: list[dict]) -> list[dict]:
    """Scans free-form text for known team aliases/nicknames (e.g. "Pháo thủ",
    "The Kop", "MU") and resolves them to canonical teams.

    Each alias is matched on a word boundary rather than a bare substring, so a
    short alias like "mu" doesn't false-positive inside an unrelated word (e.g.
    the Vietnamese "muốn"). Two further cases are handled before returning:
    - Same text region matched by two aliases of different length (e.g. if both
      "man" and "man city" were aliases, "Man City" would only match the more
      specific "man city") — the longer match wins, shorter overlapping
      matches are dropped.
    - Same team mentioned twice via two different aliases in different parts
      of the message (e.g. "MU vs Man United") — results are deduped by
      team_id, keeping only the first occurrence.
    """
    normalized = message.lower()

    hits = []
    for row in alias_rows:
        alias = row["alias"].lower()
        pattern = r"\b" + re.escape(alias) + r"\b"
        for match in re.finditer(pattern, normalized):
            hits.append((match.start(), match.end(), row))

    hits.sort(key=lambda h: h[1] - h[0], reverse=True)

    accepted: list[tuple[int, int, dict]] = []
    for start, end, row in hits:
        overlaps_accepted = any(
            start < a_end and end > a_start for a_start, a_end, _ in accepted
        )
        if not overlaps_accepted:
            accepted.append((start, end, row))

    accepted.sort(key=lambda h: h[0])

    seen_team_ids: set[int] = set()
    resolved = []
    for _, _, row in accepted:
        team_id = row["team_id"]
        if team_id in seen_team_ids:
            continue
        seen_team_ids.add(team_id)
        resolved.append({"team_id": team_id, "team_name": row["team_name"], "alias": row["alias"]})

    return resolved


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