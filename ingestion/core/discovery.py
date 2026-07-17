import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

def discover_files(raw_dir: Path, source_filter: str = None, date_filter: str = None):
    """
    Quét toàn bộ file JSON trong raw_dir theo cấu trúc:
    data/raw/{source}/{entity}/{date}/*.json

    Trả về list các dict chứa path + metadata đã tách, kèm rel_path/mtime/size_bytes
    dùng để so khớp với bronze.ingested_files (tránh phải đọc/hash lại file không đổi).
    """
    files_found = []

    for file_path in raw_dir.rglob("*.json"):
        # file_path ví dụ: data/raw/football-data-org/matches/2026-07-10/epl.json

        # .parts trả về tuple từng phần của đường dẫn
        # ('data', 'raw', 'football-data-org', 'matches', '2026-07-10', 'epl.json')
        parts = file_path.parts

        try:
            # Tìm vị trí của "raw" trong path, để lấy 3 phần ngay sau nó
            raw_index = parts.index(raw_dir.name)
            source = parts[raw_index + 1]
            entity_type = parts[raw_index + 2]
            date_str = parts[raw_index + 3]
        except (ValueError, IndexError):
            logger.warning(f"Bỏ qua file có cấu trúc đường dẫn không hợp lệ: {file_path}")
            continue

        # Áp filter nếu người dùng có truyền --source / --date
        if source_filter and source != source_filter:
            continue
        if date_filter and date_str != date_filter:
            continue

        stat = file_path.stat()

        files_found.append({
            "path": file_path,
            # Path tương đối so với raw_dir, dùng làm khóa tracking — ổn định
            # dù chạy trực tiếp trên host hay trong container Docker, khác với
            # absolute path sẽ đổi theo môi trường chạy.
            "rel_path": file_path.relative_to(raw_dir).as_posix(),
            "source": source,
            "entity_type": entity_type,
            "date": date_str,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            "size_bytes": stat.st_size,
        })

    return files_found