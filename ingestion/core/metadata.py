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
            remainder = stem[len(prefix):]
            # The season is always the first token before the next "_".
            # Anything after that is the timestamp added by save_raw()
            # to avoid overwriting files — it's not part of the season, so drop it.
            season_raw = remainder.split("_")[0]
            return {
                "league": LEAGUE_CODES[code],
                "season": normalize_season(season_raw),
            }

    logger.warning(
        f"Could not detect league from filename: '{filename}'. "
        f"Needs to be added to LEAGUE_CODES. Will be saved with league=NULL."
    )
    return {"league": None, "season": None}


def normalize_season(season_raw: str) -> str:
    """
    Normalizes the season to the YYYY-YYYY format.
    "2025" -> "2025-2026"
    "2025-2026" -> "2025-2026" (unchanged)
    """
    if "-" in season_raw:
        return season_raw
    year = int(season_raw)
    return f"{year}-{year + 1}"
