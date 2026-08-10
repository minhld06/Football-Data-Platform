from fastapi import APIRouter, Query

from db import get_connection
from queries import format_search_results, merge_search_results
from schemas import SearchResult

router = APIRouter()

FUZZY_SIMILARITY_THRESHOLD = 0.3


@router.get("", response_model=list[SearchResult])
def search(q: str = Query(min_length=2)):
    normalized = q.strip().lower()
    like_pattern = f"%{q}%"

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT tp.team_id, tp.team_name, tp.league, 1 AS priority
            FROM gold.search_aliases sa
            JOIN gold.team_profile tp ON tp.team_id = sa.entity_id
            WHERE sa.entity_type = 'team' AND sa.alias = %s
            """,
            (normalized,),
        )
        alias_teams = cur.fetchall()

        cur.execute(
            """
            SELECT team_id, team_name, league, 2 AS priority
            FROM gold.team_profile
            WHERE unaccent(team_name) ILIKE unaccent(%s)
            ORDER BY team_name
            LIMIT 10
            """,
            (like_pattern,),
        )
        substring_teams = cur.fetchall()

        fuzzy_teams = []
        if len(alias_teams) + len(substring_teams) < 10:
            cur.execute(
                """
                SELECT team_id, team_name, league, 3 AS priority
                FROM gold.team_profile
                WHERE similarity(lower(unaccent(team_name)), lower(unaccent(%s))) > %s
                ORDER BY similarity(lower(unaccent(team_name)), lower(unaccent(%s))) DESC
                LIMIT 10
                """,
                (q, FUZZY_SIMILARITY_THRESHOLD, q),
            )
            fuzzy_teams = cur.fetchall()

        cur.execute(
            """
            SELECT pp.player_id, pp.player_name, pp.team_name, 1 AS priority
            FROM gold.search_aliases sa
            JOIN gold.player_profile pp ON pp.player_id = sa.entity_id
            WHERE sa.entity_type = 'player' AND sa.alias = %s
            """,
            (normalized,),
        )
        alias_players = cur.fetchall()

        cur.execute(
            """
            SELECT player_id, player_name, team_name, 2 AS priority
            FROM gold.player_profile
            WHERE unaccent(player_name) ILIKE unaccent(%s)
            ORDER BY player_name
            LIMIT 10
            """,
            (like_pattern,),
        )
        substring_players = cur.fetchall()

        fuzzy_players = []
        if len(alias_players) + len(substring_players) < 10:
            cur.execute(
                """
                SELECT player_id, player_name, team_name, 3 AS priority
                FROM gold.player_profile
                WHERE similarity(lower(unaccent(player_name)), lower(unaccent(%s))) > %s
                ORDER BY similarity(lower(unaccent(player_name)), lower(unaccent(%s))) DESC
                LIMIT 10
                """,
                (q, FUZZY_SIMILARITY_THRESHOLD, q),
            )
            fuzzy_players = cur.fetchall()

    teams = merge_search_results(
        [alias_teams, substring_teams, fuzzy_teams], "team_id", "team_name"
    )
    players = merge_search_results(
        [alias_players, substring_players, fuzzy_players], "player_id", "player_name"
    )

    return format_search_results(teams, players)
