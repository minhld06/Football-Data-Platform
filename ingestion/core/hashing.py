import json
import hashlib
from pathlib import Path

def read_and_hash(file_path: Path) -> dict:
    """
    Đọc file JSON, trả về raw_payload và content_hash tương ứng.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        raw_payload = json.load(f)
    
    # Chuyển payload thành chuỗi JSON chuẩn hóa (sort_keys) để hash ổn định
    normalized = json.dumps(raw_payload, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    return {
        "raw_payload": raw_payload,
        "content_hash": content_hash,
    }