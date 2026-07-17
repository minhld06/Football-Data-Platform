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

# Tính project root từ vị trí file này (ingestion/ingest.py -> lùi 1 cấp),
# giống cách crawlers/common/utils.py làm — tránh hardcode path riêng của máy nào.
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


def build_records(raw_dir: Path, source_filter: str = None, date_filter: str = None) -> list[dict]:
    '''Hàm quét thư mục raw_dir, đọc các file JSON thô, tính hash và build thành list các record dict để insert vào DB.'''
    files = discover_files(raw_dir, source_filter=source_filter, date_filter=date_filter)
    logger.info(f"Tìm thấy {len(files)} file cần xử lý")

    records = []
    for f in files:
        try:
            hash_result = read_and_hash(f["path"])
            league_season = parse_league_season(f["path"].name)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Bỏ qua file lỗi {f['path']}: {e}")
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
        }
        records.append(record)

    return records

def parse_args():
    '''Hàm parse các argument từ command line.'''
    parser = argparse.ArgumentParser(
        description="Ingest raw JSON files vào bronze.raw_documents"
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Chỉ ingest 1 nguồn cụ thể, ví dụ: football_data_org (mặc định: quét tất cả)"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Chỉ ingest 1 ngày cụ thể, format YYYY-MM-DD (mặc định: quét tất cả)"
    )
    return parser.parse_args()

def main():
    '''Hàm chính để chạy quá trình ingest.'''
    args = parse_args()

    if args.source or args.date:
        logger.info(f"Chạy với filter: source={args.source}, date={args.date}")
    else:
        logger.info("Chạy quét toàn bộ data/raw/ (không có filter)")

    records = build_records(RAW_DIR, source_filter=args.source, date_filter=args.date)

    inserted_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        with get_connection() as conn:
            for r in records:
                try:
                    is_new = upsert_record(conn, r)
                    conn.commit()
                except (psycopg.DataError, psycopg.IntegrityError) as e:
                    conn.rollback()
                    failed_count += 1
                    logger.error(
                        f"Bỏ qua record lỗi dữ liệu: {r['source']} | {r['entity_type']} | "
                        f"hash={r['content_hash'][:8]}...: {e}"
                    )
                    continue

                if is_new:
                    inserted_count += 1
                    logger.info(f"[MỚI] {r['source']} | {r['entity_type']} | hash={r['content_hash'][:8]}...")
                else:
                    skipped_count += 1
                    logger.info(f"[SKIP - đã tồn tại] {r['source']} | {r['entity_type']} | hash={r['content_hash'][:8]}...")
    except psycopg.OperationalError as e:
        logger.error(f"Không kết nối được database: {e}")
        raise

    logger.info(
        f"Hoàn tất: {inserted_count} record mới, {skipped_count} record bị bỏ qua (trùng), "
        f"{failed_count} record lỗi."
    )


if __name__ == "__main__":
    main()