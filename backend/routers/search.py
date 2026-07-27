from fastapi import APIRouter, Query

from db import get_connection
from queries import format_search_results
from schemas import SearchResult

router = APIRouter()


@router.get("", response_model=list[SearchResult])
def search(q: str = Query(min_length=2)):
    like_pattern = f"%{q}%"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT team_id, team_name, league FROM gold.team_profile WHERE team_name ILIKE %s ORDER BY team_name LIMIT 10",
            (like_pattern,),
        )
        teams = cur.fetchall()

        cur.execute(
            "SELECT player_id, player_name, team_name FROM gold.player_profile WHERE player_name ILIKE %s ORDER BY player_name LIMIT 10",
            (like_pattern,),
        )
        players = cur.fetchall()

    return format_search_results(teams, players)