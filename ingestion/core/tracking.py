import logging

logger = logging.getLogger(__name__)


def filter_pending_files(files: list[dict], tracked: dict, full_rehash: bool = False) -> list[dict]:
    """
    Lọc ra các file cần đọc/hash: file chưa từng thấy trong bronze.ingested_files,
    hoặc mtime/size khác với lần ingest thành công gần nhất.

    tracked: dict {rel_path: (mtime, size_bytes)} load từ bronze.ingested_files.
    full_rehash=True: bỏ qua tracking hoàn toàn, trả về mọi file (dùng khi nghi ngờ
    raw bị sửa tay mà mtime/size không đổi).
    """
    if full_rehash:
        return files

    pending = []
    for f in files:
        seen = tracked.get(f["rel_path"])
        if seen is not None and seen == (f["mtime"], f["size_bytes"]):
            continue
        pending.append(f)
    return pending
