from pathlib import Path

def discover_files(raw_dir: Path, source_filter: str = None, date_filter: str = None):
    """
    Quét toàn bộ file JSON trong raw_dir theo cấu trúc:
    data/raw/{source}/{entity}/{date}/*.json
    
    Trả về list các dict chứa path + metadata đã tách.
    """
    files_found = []
    
    for file_path in raw_dir.rglob("*.json"):
        # file_path ví dụ: data/raw/football-data-org/matches/2026-07-10/epl.json
        
        # .parts trả về tuple từng phần của đường dẫn
        # ('data', 'raw', 'football-data-org', 'matches', '2026-07-10', 'epl.json')
        parts = file_path.parts
        
        # Tìm vị trí của "raw" trong path, để lấy 3 phần ngay sau nó
        raw_index = parts.index(raw_dir.name)
        
        source = parts[raw_index + 1]
        entity_type = parts[raw_index + 2]
        date_str = parts[raw_index + 3]
        
        # Áp filter nếu người dùng có truyền --source / --date
        if source_filter and source != source_filter:
            continue
        if date_filter and date_str != date_filter:
            continue
        
        files_found.append({
            "path": file_path,
            "source": source,
            "entity_type": entity_type,
            "date": date_str,
        })
    
    return files_found