from fastapi import APIRouter, HTTPException, Query

from db import get_connection
from schemas import PlayerProfile, PlayerPerformance

router = APIRouter()


@router.get("/top-scorers", response_model=list[PlayerPerformance])
def list_top_scorers(
    league: str | None = None,
    team_id: int | None = None,
    limit: int = Query(default=10, le=50),
):
    with get_connection() as conn, conn.cursor() as cur:
        # conditions are static strings built from trusted branches below;
        # only the values passed in `params` are interpolated into the query
        conditions = ["goals > 0"]
        params: list = []
        if league:
            conditions.append("league = %s")
            params.append(league)
        if team_id:
            conditions.append("team_id = %s")
            params.append(team_id)
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM gold.player_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY goals DESC
            LIMIT %s
            """,
            params,
        )
        return cur.fetchall()


@router.get("/top-assists", response_model=list[PlayerPerformance])
def list_top_assists(
    league: str | None = None,
    team_id: int | None = None,
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
        params.append(limit)
        cur.execute(
            f"""
            SELECT * FROM gold.player_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY assists DESC
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
def get_player_performance(player_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.player_performance WHERE player_id = %s", (player_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Player {player_id} not found")
        return row