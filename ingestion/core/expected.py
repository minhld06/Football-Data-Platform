# Static declaration: which source crawls which entity_type/league (season-agnostic —
# seasons change over time so they aren't hardcoded here). Update manually
# when adding a new source or league, same as LEAGUE_CODES in metadata.py.

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
