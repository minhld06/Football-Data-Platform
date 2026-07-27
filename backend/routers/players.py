from fastapi import APIRouter, HTTPException, Query

from db import get_connection
from schemas import PlayerProfile, PlayerPerformance

router = APIRouter()


@router.get("/top-scorers", response_model=list[PlayerPerformance])
def list_top_scorers(league: str | None = None, limit: int = Query(default=10, le=50)):
    with get_connection() as conn, conn.cursor() as cur:
        if league:
            cur.execute(
                """
                SELECT * FROM gold.player_performance
                WHERE league = %s
                ORDER BY goals DESC NULLS LAST
                LIMIT %s
                """,
                (league, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM gold.player_performance
                ORDER BY goals DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
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