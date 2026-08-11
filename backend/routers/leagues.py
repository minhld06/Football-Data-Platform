from datetime import date

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
def get_league_standings(league: str, season: str | None = None, as_of: date | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        resolved_season = _resolve_season(cur, league, season)
        if resolved_season is None:
            raise HTTPException(status_code=404, detail=f"League '{league}' not found")

        if as_of is not None:
            # Point-in-time table computed from gold.team_standings_by_matchday
            # (cumulative per-match state), not gold.league_standings (which only
            # ever reflects the latest football_data_org snapshot). Teams with no
            # finished match yet as of `as_of` still appear, with all-zero stats,
            # matching how a real standings table looks before a team's first game.
            # xg/xga/xpts/form aren't available at arbitrary past dates (Understat
            # only supplies its own periodic season-level snapshot, not per-match
            # data) — LeagueStanding leaves those Optional, so they come back null.
            cur.execute(
                """
                WITH teams_in_season AS (
                    SELECT DISTINCT team_id, team_name, team_short_name, team_tla
                    FROM gold.league_standings
                    WHERE league = %(league)s AND season = %(season)s
                ),
                as_of_stats AS (
                    SELECT DISTINCT ON (team_id)
                        team_id, played_games, won, draw, lost, points,
                        goals_for, goals_against, goal_difference
                    FROM gold.team_standings_by_matchday
                    WHERE league = %(league)s AND season = %(season)s AND utc_date <= %(as_of)s
                    ORDER BY team_id, utc_date DESC, source_match_id DESC
                )
                SELECT
                    %(league)s AS league,
                    %(season)s AS season,
                    t.team_id, t.team_name, t.team_short_name, t.team_tla,
                    row_number() OVER (
                        ORDER BY coalesce(s.points, 0) DESC,
                                 coalesce(s.goal_difference, 0) DESC,
                                 coalesce(s.goals_for, 0) DESC
                    ) AS position,
                    coalesce(s.played_games, 0) AS played_games,
                    coalesce(s.won, 0) AS won,
                    coalesce(s.draw, 0) AS draw,
                    coalesce(s.lost, 0) AS lost,
                    coalesce(s.points, 0) AS points,
                    coalesce(s.goals_for, 0) AS goals_for,
                    coalesce(s.goals_against, 0) AS goals_against,
                    coalesce(s.goal_difference, 0) AS goal_difference
                FROM teams_in_season t
                LEFT JOIN as_of_stats s ON s.team_id = t.team_id
                ORDER BY position
                """,
                {"league": league, "season": resolved_season, "as_of": as_of},
            )
            return cur.fetchall()

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
            "SELECT * FROM gold.match_results WHERE league = %s AND season = %s ORDER BY utc_date DESC",
            (league, resolved_season),
        )
        return cur.fetchall()
