from fastapi import APIRouter, HTTPException, Query

from db import get_connection
from schemas import PlayerProfile, PlayerPerformance

router = APIRouter()


def _latest_season(cur) -> str:
    # backend/db.py's get_connection() uses psycopg's dict_row row_factory,
    # so fetchone() returns a dict-like row here.
    cur.execute("SELECT max(season) FROM gold.player_performance")
    return cur.fetchone()["max"]


@router.get("/top-scorers", response_model=list[PlayerPerformance])
def list_top_scorers(
    league: str | None = None,
    team_id: int | None = None,
    season: str | None = None,
    limit: int = Query(default=10, le=50),
):
    with get_connection() as conn, conn.cursor() as cur:
        conditions = ["goals > 0"]
        params: list = []
        if league:
            conditions.append("league = %s")
            params.append(league)
        if team_id:
            conditions.append("team_id = %s")
            params.append(team_id)
        conditions.append("season = %s")
        params.append(season or _latest_season(cur))
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM gold.player_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY goals DESC, player_name
            LIMIT %s
            """,
            params,
        )
        return cur.fetchall()


@router.get("/top-assists", response_model=list[PlayerPerformance])
def list_top_assists(
    league: str | None = None,
    team_id: int | None = None,
    season: str | None = None,
    limit: int = Query(default=10, le=50),
):
    with get_connection() as conn, conn.cursor() as cur:
        conditions = ["assists > 0"]
        params: list = []
        if league:
            conditions.append("league = %s")
            params.append(league)
        if team_id:
            conditions.append("team_id = %s")
            params.append(team_id)
        conditions.append("season = %s")
        params.append(season or _latest_season(cur))
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM gold.player_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY assists DESC, player_name
            LIMIT %s
            """,
            params,
        )
        return cur.fetchall()


@router.get("/{player_id}", response_model=PlayerProfile)
def get_player(player_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.player_profile WHERE player_id = %s", (player_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
        return row


@router.get("/{player_id}/performance", response_model=PlayerPerformance)
def get_player_performance(player_id: int, season: str | None = None):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM gold.player_performance WHERE player_id = %s AND season = %s",
            (player_id, season or _latest_season(cur)),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
        return row
