import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

def discover_files(raw_dir: Path, source_filter: str = None, date_filter: str = None):
    """
    Scans all JSON files under raw_dir following the structure:
    data/raw/{source}/{entity}/{date}/*.json

    Returns a list of dicts containing the path + parsed metadata, plus rel_path/mtime/size_bytes
    used to match against bronze.ingested_files (to avoid re-reading/hashing unchanged files).
    """
    files_found = []

    for file_path in raw_dir.rglob("*.json"):
        # file_path example: data/raw/football-data-org/matches/2026-07-10/epl.json

        # .parts returns a tuple of each path segment
        # ('data', 'raw', 'football-data-org', 'matches', '2026-07-10', 'epl.json')
        parts = file_path.parts

        try:
            # Find the position of "raw" in the path, to get the 3 segments right after it
            raw_index = parts.index(raw_dir.name)
            source = parts[raw_index + 1]
            entity_type = parts[raw_index + 2]
            date_str = parts[raw_index + 3]
        except (ValueError, IndexError):
            logger.warning(f"Skipping file with an invalid path structure: {file_path}")
            continue

        # Apply the filter if the user passed --source / --date
        if source_filter and source != source_filter:
            continue
        if date_filter and date_str != date_filter:
            continue

        stat = file_path.stat()

        files_found.append({
            "path": file_path,
            # Path relative to raw_dir, used as the tracking key — stable
            # whether running directly on the host or inside a Docker container, unlike
            # an absolute path which would change depending on the runtime environment.
            "rel_path": file_path.relative_to(raw_dir).as_posix(),
            "source": source,
            "entity_type": entity_type,
            "date": date_str,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            "size_bytes": stat.st_size,
        })

    return files_found
