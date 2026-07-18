import logging

logger = logging.getLogger(__name__)


def find_gaps(counts: list[dict], expected: dict) -> list[dict]:
    """
    counts: list các dict {"source", "entity_type", "league", "season", "count"}
            (kết quả GROUP BY source, entity_type, league, season trên bronze.raw_documents).
    expected: EXPECTED_COMBOS — {source: {entity_type: [league, ...]}}.

    Với mỗi league, season "đáng lẽ phải có" được suy ra động = union mọi season
    đã thấy ở bất kỳ nguồn/entity_type nào cho league đó (không hardcode season).

    Trả về list gap: mỗi gap là 1 dict {"source", "entity_type", "league", "season"}
    ứng với 1 combo có trong `expected` nhưng không có bản ghi nào trong `counts`,
    trong khi season đó đã xuất hiện ở ít nhất 1 nguồn khác cho cùng league.
    """
    seasons_by_league: dict[str, set] = {}
    for row in counts:
        if row["league"] is None or row["season"] is None:
            continue
        seasons_by_league.setdefault(row["league"], set()).add(row["season"])

    present = {
        (row["source"], row["entity_type"], row["league"], row["season"])
        for row in counts
    }

    gaps = []
    for source, entity_types in expected.items():
        for entity_type, leagues in entity_types.items():
            for league in leagues:
                for season in seasons_by_league.get(league, set()):
                    if (source, entity_type, league, season) not in present:
                        gaps.append({
                            "source": source,
                            "entity_type": entity_type,
                            "league": league,
                            "season": season,
                        })
    return gaps


def find_unexpected_combos(counts: list[dict], expected: dict) -> list[dict]:
    """
    Trả về các combo (source, entity_type, league, season) đã có bản ghi trong
    `counts` nhưng (source, entity_type, league) không nằm trong `expected` —
    ví dụ crawler được mở rộng thêm giải đấu mới nhưng EXPECTED_COMBOS chưa cập
    nhật. Không phải lỗi (không tính là gap), chỉ để log mức INFO.
    """
    unexpected = []
    for row in counts:
        source, entity_type, league = row["source"], row["entity_type"], row["league"]
        expected_leagues = expected.get(source, {}).get(entity_type, [])
        if league not in expected_leagues:
            unexpected.append({
                "source": source,
                "entity_type": entity_type,
                "league": league,
                "season": row["season"],
            })
    return unexpected
