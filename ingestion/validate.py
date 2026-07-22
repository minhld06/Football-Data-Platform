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
    logger.info("=== Record counts by source/entity_type/league/season ===")
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
        logger.error(f"Could not connect to the database: {e}")
        raise

    if not counts:
        logger.warning("bronze.raw_documents is empty — nothing to validate.")
        return 0

    print_counts_table(counts)

    unexpected = find_unexpected_combos(counts, EXPECTED_COMBOS)
    for u in unexpected:
        logger.info(
            f"[UNEXPECTED] {u['source']} | {u['entity_type']} | {u['league']} | {u['season']} "
            f"— not in EXPECTED_COMBOS, core/expected.py may need updating"
        )

    gaps = find_gaps(counts, EXPECTED_COMBOS)
    if gaps:
        logger.error(f"Found {len(gaps)} gap(s):")
        for g in gaps:
            logger.error(
                f"[GAP] {g['source']} is missing {g['entity_type']} for {g['league']} "
                f"season {g['season']} (other sources already have data for this season)"
            )
        return 1

    logger.info("No gaps found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
