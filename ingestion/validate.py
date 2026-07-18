import logging
import os
from pathlib import Path

import psycopg

from core.db import get_connection, fetch_counts
from core.expected import EXPECTED_COMBOS
from core.validation import find_gaps, find_unexpected_combos

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = Path(os.environ.get("LOG_DIR", str(_PROJECT_ROOT / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "validation.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


def print_counts_table(counts: list[dict]) -> None:
    logger.info("=== Số bản ghi theo source/entity_type/league/season ===")
    for row in counts:
        logger.info(
            f"{row['source']:<20} {row['entity_type']:<10} "
            f"{row['league'] or '-':<16} {row['season'] or '-':<10} {row['count']}"
        )


def main() -> int:
    try:
        with get_connection() as conn:
            counts = fetch_counts(conn)
    except psycopg.OperationalError as e:
        logger.error(f"Không kết nối được database: {e}")
        raise

    if not counts:
        logger.warning("bronze.raw_documents đang rỗng — chưa có gì để validate.")
        return 0

    print_counts_table(counts)

    unexpected = find_unexpected_combos(counts, EXPECTED_COMBOS)
    for u in unexpected:
        logger.info(
            f"[NGOÀI KỲ VỌNG] {u['source']} | {u['entity_type']} | {u['league']} | {u['season']} "
            f"— không có trong EXPECTED_COMBOS, có thể cần cập nhật core/expected.py"
        )

    gaps = find_gaps(counts, EXPECTED_COMBOS)
    if gaps:
        logger.error(f"Phát hiện {len(gaps)} gap:")
        for g in gaps:
            logger.error(
                f"[GAP] {g['source']} thiếu {g['entity_type']} cho {g['league']} "
                f"season {g['season']} (nguồn khác đã có dữ liệu season này)"
            )
        return 1

    logger.info("Không phát hiện gap nào.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
