import os
import logging
from pathlib import Path
import argparse

from core.discovery import discover_files
from core.hashing import read_and_hash
from core.metadata import parse_league_season
from core.db import get_connection, upsert_record

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)

RAW_DIR = Path(os.environ.get("RAW_DATA_DIR", r"G:\Football Data Platform\data\raw"))


def build_records(raw_dir: Path, source_filter: str = None, date_filter: str = None) -> list[dict]:
    '''Hàm quét thư mục raw_dir, đọc các file JSON thô, tính hash và build thành list các record dict để insert vào DB.'''
    files = discover_files(raw_dir, source_filter=source_filter, date_filter=date_filter)
    logger.info(f"Tìm thấy {len(files)} file cần xử lý")

    records = []
    for f in files:
        hash_result = read_and_hash(f["path"])
        league_season = parse_league_season(f["path"].name)

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

    with get_connection() as conn:
        for r in records:
            is_new = upsert_record(conn, r)
            conn.commit()

            if is_new:
                inserted_count += 1
                logger.info(f"[MỚI] {r['source']} | {r['entity_type']} | hash={r['content_hash'][:8]}...")
            else:
                skipped_count += 1
                logger.info(f"[SKIP - đã tồn tại] {r['source']} | {r['entity_type']} | hash={r['content_hash'][:8]}...")

    logger.info(f"Hoàn tất: {inserted_count} record mới, {skipped_count} record bị bỏ qua (trùng).")


if __name__ == "__main__":
    main()