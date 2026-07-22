import logging

logger = logging.getLogger(__name__)


def find_gaps(counts: list[dict], expected: dict) -> list[dict]:
    """
    counts: list of dicts {"source", "entity_type", "league", "season", "count"}
            (the result of GROUP BY source, entity_type, league, season on bronze.raw_documents).
    expected: EXPECTED_COMBOS — {source: {entity_type: [league, ...]}}.

    For each league, the season that "should exist" is derived dynamically as the union of every
    season seen for that league across any source/entity_type (seasons are not hardcoded).

    Returns a list of gaps: each gap is a dict {"source", "entity_type", "league", "season"}
    for a combo present in `expected` but with no record in `counts`,
    while that season has appeared for at least one other source for the same league.
    """
    seasons_by_league: dict[str, set] = {}
    for row in counts:
        if row["league"] is None or row["season"] is None:
            continue
        seasons_by_league.setdefault(row["league"], set()).add(row["season"])

    present = {
        (row["source"], row["entity_type"], row["league"], row["season"])
        for row in counts
    }

    gaps = []
    for source, entity_types in expected.items():
        for entity_type, leagues in entity_types.items():
            for league in leagues:
                for season in seasons_by_league.get(league, set()):
                    if (source, entity_type, league, season) not in present:
                        gaps.append({
                            "source": source,
                            "entity_type": entity_type,
                            "league": league,
                            "season": season,
                        })
    return gaps


def find_unexpected_combos(counts: list[dict], expected: dict) -> list[dict]:
    """
    Returns combos (source, entity_type, league, season) that have records in
    `counts` but where (source, entity_type, league) is not in `expected` —
    e.g. a crawler was extended to a new league but EXPECTED_COMBOS wasn't
    updated yet. Not an error (not counted as a gap), just logged at INFO level.
    """
    unexpected = []
    for row in counts:
        source, entity_type, league = row["source"], row["entity_type"], row["league"]
        expected_leagues = expected.get(source, {}).get(entity_type, [])
        if league not in expected_leagues:
            unexpected.append({
                "source": source,
                "entity_type": entity_type,
                "league": league,
                "season": row["season"],
            })
    return unexpected
