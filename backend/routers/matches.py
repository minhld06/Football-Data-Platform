from fastapi import APIRouter, HTTPException, Query

from db import get_connection
from schemas import MatchResult

router = APIRouter()


@router.get("/recent", response_model=list[MatchResult])
def list_recent_matches(league: str | None = None, limit: int = Query(default=10, le=50)):
    with get_connection() as conn, conn.cursor() as cur:
        if league:
            cur.execute(
                """
                SELECT * FROM gold.match_results
                WHERE status = 'FINISHED' AND league = %s
                ORDER BY utc_date DESC
                LIMIT %s
                """,
                (league, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM gold.match_results
                WHERE status = 'FINISHED'
                ORDER BY utc_date DESC
                LIMIT %s
                """,
                (limit,),
            )
        return cur.fetchall()


@router.get("/{match_id}", response_model=MatchResult)
def get_match(match_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.match_results WHERE source_match_id = %s", (match_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
        return row