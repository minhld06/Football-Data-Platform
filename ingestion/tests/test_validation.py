from core.validation import find_gaps, find_unexpected_combos

EXPECTED = {
    "football_data_org": {"matches": ["premier-league", "ligue-1"], "standings": ["premier-league", "ligue-1"]},
    "statbunker":         {"standings": ["premier-league"]},
    "understat":          {"standings": ["premier-league", "ligue-1"]},
}


def _row(source, entity_type, league, season, count=1):
    return {"source": source, "entity_type": entity_type, "league": league, "season": season, "count": count}


def test_no_gap_when_every_expected_combo_has_every_season():
    counts = [
        _row("football_data_org", "standings", "premier-league", "2025-2026"),
        _row("football_data_org", "matches", "premier-league", "2025-2026"),
        _row("football_data_org", "standings", "ligue-1", "2025-2026"),
        _row("football_data_org", "matches", "ligue-1", "2025-2026"),
        _row("statbunker", "standings", "premier-league", "2025-2026"),
        _row("understat", "standings", "premier-league", "2025-2026"),
        _row("understat", "standings", "ligue-1", "2025-2026"),
    ]

    gaps = find_gaps(counts, EXPECTED)

    assert gaps == []


def test_gap_when_source_missing_season_other_sources_have():
    counts = [
        _row("football_data_org", "standings", "premier-league", "2025-2026"),
        _row("football_data_org", "standings", "premier-league", "2026-2027"),
        _row("statbunker", "standings", "premier-league", "2025-2026"),
        # statbunker thiếu bản ghi cho season 2026-2027, dù football_data_org đã có
    ]

    gaps = find_gaps(counts, EXPECTED)

    assert {
        "source": "statbunker", "entity_type": "standings",
        "league": "premier-league", "season": "2026-2027",
    } in gaps


def test_no_gap_for_source_not_expected_to_have_league():
    # statbunker vốn không expected có ligue-1 -> không được coi là gap
    # dù ligue-1 xuất hiện ở nguồn khác.
    counts = [
        _row("football_data_org", "standings", "ligue-1", "2025-2026"),
    ]

    gaps = find_gaps(counts, EXPECTED)

    assert all(g["source"] != "statbunker" for g in gaps)


def test_combo_outside_expected_is_not_a_gap_but_is_flagged_unexpected():
    counts = [
        _row("football_data_org", "standings", "bundesliga", "2025-2026"),
    ]

    gaps = find_gaps(counts, EXPECTED)
    unexpected = find_unexpected_combos(counts, EXPECTED)

    assert gaps == []
    assert {
        "source": "football_data_org", "entity_type": "standings",
        "league": "bundesliga", "season": "2025-2026",
    } in unexpected
