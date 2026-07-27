from fastapi import APIRouter, HTTPException

from db import get_connection
from queries import latest_season
from schemas import LeagueSummary, TeamSummary, LeagueStanding, MatchResult

router = APIRouter()


def _resolve_season(cur, league: str, season: str | None) -> str | None:
    if season:
        return season
    cur.execute(
        "SELECT DISTINCT season FROM gold.league_standings WHERE league = %s",
        (league,),
    )
    seasons = [row["season"] for row in cur.fetchall()]
    return latest_season(seasons)


@router.get("", response_model=list[LeagueSummary])
def list_leagues():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT league, array_agg(DISTINCT season ORDER BY season DESC) AS seasons
            FROM gold.league_standings
            GROUP BY league
            ORDER BY league
            """
        )
        return cur.fetchall()


@router.get("/{league}/teams", response_model=list[TeamSummary])
def list_league_teams(league: str, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        resolved_season = _resolve_season(cur, league, season)
        if resolved_season is None:
            raise HTTPException(status_code=404, detail=f"League '{league}' not found")

        cur.execute(
            """
            SELECT DISTINCT team_id, team_name, team_short_name, team_tla
            FROM gold.league_standings
            WHERE league = %s AND season = %s
            ORDER BY team_name
            """,
            (league, resolved_season),
        )
        return cur.fetchall()


@router.get("/{league}/standings", response_model=list[LeagueStanding])
def get_league_standings(league: str, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        resolved_season = _resolve_season(cur, league, season)
        if resolved_season is None:
            raise HTTPException(status_code=404, detail=f"League '{league}' not found")

        cur.execute(
            "SELECT * FROM gold.league_standings WHERE league = %s AND season = %s ORDER BY position",
            (league, resolved_season),
        )
        return cur.fetchall()

@router.get("/{league}/matches", response_model=list[MatchResult])
def list_league_matches(league: str, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        resolved_season = _resolve_season(cur, league, season)
        if resolved_season is None:
            raise HTTPException(status_code=404, detail=f"League '{league}' not found")

        cur.execute(
            "SELECT * FROM gold.match_results WHERE league = %s AND season = %s ORDER BY utc_date",
            (league, resolved_season),
        )
        return cur.fetchall()
