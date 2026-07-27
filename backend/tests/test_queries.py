from queries import latest_season, format_search_results


def test_latest_season_picks_max_lexical_season():
    assert latest_season(["2023-2024", "2025-2026", "2024-2025"]) == "2025-2026"


def test_latest_season_empty_list_returns_none():
    assert latest_season([]) is None


def test_format_search_results_tags_type_and_shapes_fields():
    teams = [{"team_id": 1, "team_name": "Arsenal", "league": "premier-league"}]
    players = [{"player_id": 10, "player_name": "Bukayo Saka", "team_name": "Arsenal"}]

    results = format_search_results(teams, players)

    assert results == [
        {"type": "team", "id": 1, "name": "Arsenal", "subtitle": "premier-league"},
        {"type": "player", "id": 10, "name": "Bukayo Saka", "subtitle": "Arsenal"},
    ]