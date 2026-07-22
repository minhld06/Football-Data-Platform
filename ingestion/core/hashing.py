import json
import hashlib
from pathlib import Path

def read_and_hash(file_path: Path) -> dict:
    """
    Reads a JSON file and returns its raw_payload and corresponding content_hash.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        raw_payload = json.load(f)

    # Convert the payload to a normalized JSON string (sort_keys) for a stable hash
    normalized = json.dumps(raw_payload, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    return {
        "raw_payload": raw_payload,
        "content_hash": content_hash,
    }