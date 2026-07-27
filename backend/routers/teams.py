from fastapi import APIRouter, HTTPException

from db import get_connection
from schemas import TeamProfile, MatchResult, TeamForm

router = APIRouter()


@router.get("/{team_id}", response_model=TeamProfile)
def get_team(team_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.team_profile WHERE team_id = %s", (team_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
        return row


@router.get("/{team_id}/matches", response_model=list[MatchResult])
def get_team_matches(team_id: int, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        if season:
            cur.execute(
                """
                SELECT * FROM gold.match_results
                WHERE (home_team_id = %s OR away_team_id = %s) AND season = %s
                ORDER BY utc_date DESC
                """,
                (team_id, team_id, season),
            )
        else:
            cur.execute(
                """
                SELECT * FROM gold.match_results
                WHERE home_team_id = %s OR away_team_id = %s
                ORDER BY utc_date DESC
                """,
                (team_id, team_id),
            )
        return cur.fetchall()


@router.get("/{team_id}/form", response_model=TeamForm)
def get_team_form(team_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM gold.team_form_last_5_matches WHERE team_id = %s ORDER BY season DESC LIMIT 1",
            (team_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"No form data for team {team_id}")
        return row