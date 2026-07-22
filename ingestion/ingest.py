import os
import json
import logging
from pathlib import Path
import argparse

import psycopg

from core.discovery import discover_files
from core.hashing import read_and_hash
from core.metadata import parse_league_season
from core.db import get_connection, upsert_record
from core.tracking import load_tracked_files, mark_ingested, filter_pending_files

# Compute the project root from this file's location (ingestion/ingest.py -> go up 1 level),
# the same way crawlers/common/utils.py does — avoids hardcoding a machine-specific path.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = Path(os.environ.get("RAW_DATA_DIR", str(_PROJECT_ROOT / "data" / "raw")))
LOG_DIR = Path(os.environ.get("LOG_DIR", str(_PROJECT_ROOT / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "ingestion.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)


def build_records(raw_dir: Path, source_filter: str = None, date_filter: str = None,
                   tracked_files: dict = None, full_rehash: bool = False) -> list[dict]:
    '''Scans raw_dir, filters to new/changed files, reads + hashes them, and builds the list of record dicts to insert into the DB.'''
    files = discover_files(raw_dir, source_filter=source_filter, date_filter=date_filter)
    logger.info(f"Found {len(files)} files matching the filter")

    pending_files = filter_pending_files(files, tracked_files or {}, full_rehash=full_rehash)
    logger.info(f"{len(pending_files)} files need reading/hashing (skipping {len(files) - len(pending_files)} unchanged files from the previous ingest)")

    records = []
    for f in pending_files:
        try:
            hash_result = read_and_hash(f["path"])
            league_season = parse_league_season(f["path"].name)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Skipping bad file {f['path']}: {e}")
            continue

        record = {
            "source": f["source"],
            "entity_type": f["entity_type"],
            "entity_id": None,
            "payload": hash_result["raw_payload"],
            "content_hash": hash_result["content_hash"],
            "source_url": None,
            "league": league_season["league"],
            "season": league_season["season"],
            "rel_path": f["rel_path"],
            "mtime": f["mtime"],
            "size_bytes": f["size_bytes"],
        }
        records.append(record)

    return records

def parse_args():
    '''Parses command-line arguments.'''
    parser = argparse.ArgumentParser(
        description="Ingest raw JSON files into bronze.raw_documents"
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Ingest only a specific source, e.g. football_data_org (default: scan all)"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Ingest only a specific date, format YYYY-MM-DD (default: scan all)"
    )
    parser.add_argument(
        "--full-rehash",
        action="store_true",
        help="Bypass bronze.ingested_files and re-read/hash every file matching the filter (use when raw files may have been hand-edited without changing mtime/size)"
    )
    return parser.parse_args()

def main():
    '''Main function that runs the ingest process.'''
    args = parse_args()

    if args.source or args.date:
        logger.info(f"Running with filter: source={args.source}, date={args.date}")
    else:
        logger.info("Scanning all of data/raw/ (no filter)")
    if args.full_rehash:
        logger.info("--full-rehash: bypassing bronze.ingested_files, re-hashing every file matching the filter")

    inserted_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        with get_connection() as conn:
            tracked_files = load_tracked_files(conn, source_filter=args.source)
            records = build_records(
                RAW_DIR,
                source_filter=args.source,
                date_filter=args.date,
                tracked_files=tracked_files,
                full_rehash=args.full_rehash,
            )

            for r in records:
                try:
                    is_new = upsert_record(conn, r)
                    mark_ingested(conn, r["rel_path"], r["source"], r["entity_type"], r["mtime"], r["size_bytes"])
                    conn.commit()
                except (psycopg.DataError, psycopg.IntegrityError) as e:
                    conn.rollback()
                    failed_count += 1
                    logger.error(
                        f"Skipping record due to data error: {r['source']} | {r['entity_type']} | "
                        f"hash={r['content_hash'][:8]}...: {e}"
                    )
                    continue

                if is_new:
                    inserted_count += 1
                    logger.info(f"[NEW] {r['source']} | {r['entity_type']} | hash={r['content_hash'][:8]}...")
                else:
                    skipped_count += 1
                    logger.info(f"[SKIP - already exists] {r['source']} | {r['entity_type']} | hash={r['content_hash'][:8]}...")
    except psycopg.OperationalError as e:
        logger.error(f"Could not connect to the database: {e}")
        raise

    logger.info(
        f"Done: {inserted_count} new records, {skipped_count} records skipped (duplicates), "
        f"{failed_count} records failed."
    )


if __name__ == "__main__":
    main()
