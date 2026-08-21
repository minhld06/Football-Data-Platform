from queries import latest_season, format_search_results, merge_search_results, resolve_team_mentions


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


def test_merge_search_results_dedupes_keeping_best_priority():
    alias_hits = [{"team_id": 66, "team_name": "Manchester United FC", "priority": 1}]
    substring_hits = [
        {"team_id": 66, "team_name": "Manchester United FC", "priority": 2},
        {"team_id": 65, "team_name": "Manchester City FC", "priority": 2},
    ]
    fuzzy_hits = []

    result = merge_search_results([alias_hits, substring_hits, fuzzy_hits], "team_id", "team_name")

    assert result == [
        {"team_id": 66, "team_name": "Manchester United FC", "priority": 1},
        {"team_id": 65, "team_name": "Manchester City FC", "priority": 2},
    ]


def test_merge_search_results_sorts_by_priority_then_name():
    tier1 = [{"team_id": 1, "team_name": "Bravo FC", "priority": 1}]
    tier2 = [{"team_id": 2, "team_name": "Alpha FC", "priority": 1}]
    tier3 = [{"team_id": 3, "team_name": "Zulu FC", "priority": 3}]

    result = merge_search_results([tier1, tier2, tier3], "team_id", "team_name")

    assert [r["team_id"] for r in result] == [2, 1, 3]


def test_merge_search_results_truncates_to_limit():
    tier1 = [{"team_id": i, "team_name": f"Team {i}", "priority": 1} for i in range(15)]

    result = merge_search_results([tier1, [], []], "team_id", "team_name", limit=10)

    assert len(result) == 10


def test_resolve_team_mentions_matches_known_nickname():
    alias_rows = [{"alias": "pháo thủ", "team_id": 57, "team_name": "Arsenal FC"}]

    result = resolve_team_mentions("Pháo thủ đang đứng thứ mấy?", alias_rows)

    assert result == [{"team_id": 57, "team_name": "Arsenal FC", "alias": "pháo thủ"}]


def test_resolve_team_mentions_ignores_alias_found_inside_unrelated_word():
    alias_rows = [{"alias": "mu", "team_id": 66, "team_name": "Manchester United FC"}]

    result = resolve_team_mentions("Tôi muốn xem trận đấu chiều nay", alias_rows)

    assert result == []


def test_resolve_team_mentions_dedupes_same_team_matched_via_two_aliases():
    alias_rows = [
        {"alias": "mu", "team_id": 66, "team_name": "Manchester United FC"},
        {"alias": "man united", "team_id": 66, "team_name": "Manchester United FC"},
    ]

    result = resolve_team_mentions("MU vs Man United tonight", alias_rows)

    assert len(result) == 1
    assert result[0]["team_id"] == 66


def test_resolve_team_mentions_prefers_longer_alias_on_overlap():
    alias_rows = [
        {"alias": "man", "team_id": 999, "team_name": "Fake Man FC"},
        {"alias": "man city", "team_id": 65, "team_name": "Manchester City FC"},
    ]

    result = resolve_team_mentions("Man City won today", alias_rows)

    assert result == [{"team_id": 65, "team_name": "Manchester City FC", "alias": "man city"}]


def test_resolve_team_mentions_returns_empty_when_no_alias_matches():
    alias_rows = [{"alias": "gunners", "team_id": 57, "team_name": "Arsenal FC"}]

    result = resolve_team_mentions("What's the weather today?", alias_rows)

    assert result == []