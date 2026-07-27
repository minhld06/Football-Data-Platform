from fastapi import APIRouter, HTTPException

from db import get_connection
from schemas import MatchResult

router = APIRouter()


@router.get("/{match_id}", response_model=MatchResult)
def get_match(match_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM gold.match_results WHERE source_match_id = %s", (match_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
        return row